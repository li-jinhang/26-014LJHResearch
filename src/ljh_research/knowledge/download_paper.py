#!/usr/bin/env python3
"""Download a paper PDF from a URL, verify it, and optionally ingest it into ljh research."""

from __future__ import annotations

import argparse
import locale
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from ljh_research.knowledge.cli_output import configure_utf8
from ljh_research.workspace_contract import resolve_project_root
from ljh_research.knowledge.layout import research_root

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 60
INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def is_direct_pdf(url: str) -> bool:
    return url.lower().rstrip("/").endswith(".pdf")


def normalize_url(url: str) -> str:
    """Rewrite DOI and arXiv URLs to a direct, fetchable form."""
    url = url.strip()
    if url.startswith("doi:"):
        return "https://doi.org/" + url[4:].lstrip("/")
    arxiv = re.search(
        r"(?:arxiv\.org|export\.arxiv\.org)/(?:abs|pdf)/([0-9]{4}\.[0-9]+(?:v[0-9]+)?)",
        url,
    )
    if arxiv:
        return f"https://arxiv.org/pdf/{arxiv.group(1)}"
    return url


def resolve_final_url(url: str, timeout: int) -> str:
    """Follow redirects (e.g., DOI/landing pages) and keep the final PDF URL when obvious."""
    if is_direct_pdf(url) or "arxiv.org/pdf/" in url:
        return url
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final = response.geturl()
            response.read(4096)
    except (urllib.error.URLError, OSError):
        return url
    if final != url and (final.lower().rstrip("/").endswith(".pdf") or "arxiv.org/pdf/" in final):
        return final
    return url



ARXIV_PDF_RE = re.compile(r"https?://(?:export\.)?arxiv\.org/pdf/([0-9]{4}\.[0-9]+)(?:v[0-9]+)?")


def download_with_fallback(url: str, dest_dir: Path, timeout: int) -> Path:
    """Download a PDF, retrying arXiv v1 when the plain-id URL is withdrawn/404."""
    candidates = [url]
    match = ARXIV_PDF_RE.search(url)
    if match and not re.search(r"v[0-9]+$", match.group(0)):
        paper_id = match.group(1)
        candidates.append("https://arxiv.org/pdf/%sv1" % paper_id)
        candidates.append("https://export.arxiv.org/pdf/%sv1" % paper_id)
    last_error = None
    for candidate in candidates:
        try:
            return download(candidate, dest_dir, timeout)
        except SystemExit as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise SystemExit("error=download failed for %s: no candidate URLs" % url)


def download(url: str, dest_dir: Path, timeout: int) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(suffix=".part", dir=str(dest_dir))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            with open(tmp, "wb") as out:
                shutil.copyfileobj(response, out, length=256 * 1024)
        if tmp.read_bytes()[:5] != b"%PDF-":
            raise SystemExit(
                f"error=not a valid PDF (bad magic bytes) from {url}; "
                "try an arXiv or author-page copy"
            )
        return tmp
    except SystemExit:
        tmp.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, OSError) as exc:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"error=download failed for {url}: {exc}") from exc


def inspect_pdf(path: Path) -> tuple[int | None, str | None]:
    """Return (page count, metadata title); both None when no reader is available."""
    for module_name in ("pypdf", "PyPDF2"):
        try:
            module = __import__(module_name, fromlist=["PdfReader"])
            reader = module.PdfReader(str(path))
            title = None
            metadata = getattr(reader, "metadata", None)
            if metadata is not None:
                title = getattr(metadata, "title", None)
            return len(reader.pages), title
        except (ImportError, OSError, ValueError):
            continue
    return None, None


def normalized_text(value: str) -> str:
    return re.sub(r"\W+", "", value.lower())


def title_matches(expected: str, actual: str | None) -> bool:
    if not expected or not actual:
        return True
    left = normalized_text(expected)
    right = normalized_text(actual)
    return bool(left and right and (left == right or left in right or right in left))


def safe_filename(value: str) -> str:
    name = INVALID_CHARS.sub("-", value)
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"-+", "-", name).strip(" .-")
    return (name[:150].rstrip("-") or "paper")


def build_filename(title: str | None, venue: str | None, year: str | None) -> str:
    if title:
        base = safe_filename(title)
        if venue:
            base = f"{base}-{venue}"
            if year:
                base = f"{base}{year}"
    else:
        base = "paper"
    return base + ".pdf"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 100):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    return path.with_name(f"{path.stem}-{path.stat().st_mtime_ns}{path.suffix}")


def find_existing(project_root: Path, query: str) -> bool:
    result = subprocess.run(
        [
            sys.executable,
            "-m", "ljh_research.knowledge.search_source_file",
            "--project-root",
            str(project_root),
            "--query",
            query,
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding=locale.getpreferredencoding(False),
        errors="replace",
    )
    return "found=true" in result.stdout


def run_import(
    project_root: Path,
    source: Path,
    title: str,
    method: str,
    topic_relative: str,
    source_url: str | None,
) -> None:
    command = [
        sys.executable,
        "-m", "ljh_research.knowledge.import_paper",
        "--project-root",
        str(project_root),
        "--source",
        str(source),
        "--title",
        title,
        "--method",
        method,
        "--topic-root-relative",
        topic_relative,
    ]
    if source_url:
        command += ["--source-url", source_url]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding=locale.getpreferredencoding(False),
        errors="replace",
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        raise SystemExit(f"error=import_paper.py failed with exit code {result.returncode}")


def main() -> int:
    configure_utf8()
    parser = argparse.ArgumentParser(
        description="Download a paper PDF, verify it, and optionally ingest it into ljh research."
    )
    parser.add_argument("--url", required=True, help="PDF link, arXiv page, DOI, or landing page URL.")
    parser.add_argument("--title", help="Expected paper title for the filename and cross-check.")
    parser.add_argument("--venue", help="Venue abbreviation for the filename (e.g., AAAI).")
    parser.add_argument("--year", help="Publication year for the filename (e.g., 2026).")
    parser.add_argument("--method", help="Main method/model name; required with --project-root to auto-ingest.")
    parser.add_argument("--topic-root-relative", help="0知识库/<domain>/<topic> for auto-ingest.")
    parser.add_argument("--project-root", help="Project root for ljh research; enables dedup + import chain.")
    parser.add_argument("--source-url", help="Original official URL for provenance; defaults to the download URL.")
    parser.add_argument("--out-dir", help="Download directory. Defaults to <project-root>/ljh research docs/_downloads or cwd.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Network timeout in seconds.")
    args = parser.parse_args()

    project_root = Path(args.project_root).expanduser().resolve() if args.project_root else None
    if project_root:
        if not args.method:
            raise SystemExit(
                "--method is required with --project-root (import_paper.py needs it); "
                "supply --method or drop --project-root to download only"
            )
        if not args.topic_root_relative:
            raise SystemExit(
                "--topic-root-relative is required with --project-root to know where to import"
            )

    if project_root:
        query = args.title or args.url
        if find_existing(project_root, query):
            print("exists=true")
            print(f"query={query}")
            print("skipped=duplicate found via search_source_file.py")
            return 0

    url = normalize_url(args.url)
    download_url = resolve_final_url(url, args.timeout)
    out_dir = (
        Path(args.out_dir).expanduser().resolve()
        if args.out_dir
        else (research_root(project_root) / "_downloads" if project_root else Path.cwd())
    )
    downloaded = download_with_fallback(download_url, out_dir, args.timeout)
    pages, pdf_title = inspect_pdf(downloaded)
    matched = title_matches(args.title or "", pdf_title)
    dest = unique_path(out_dir / build_filename(args.title, args.venue, args.year))
    shutil.move(str(downloaded), str(dest))

    print("exists=false")
    print(f"url={args.url}")
    print(f"download_url={download_url}")
    print(f"file={dest}")
    print(f"size={dest.stat().st_size}")
    print(f"pages={pages if pages is not None else 'unknown'}")
    print(f"pdf_title={pdf_title or ''}")
    print(f"title_match={str(matched).lower()}")
    if args.venue:
        print(f"venue={args.venue}")
    if args.year:
        print(f"year={args.year}")

    if project_root:
        title_for_import = args.title or pdf_title or dest.stem
        run_import(
            project_root,
            dest,
            title_for_import,
            args.method,
            args.topic_root_relative,
            args.source_url or args.url,
        )
        print("imported=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
