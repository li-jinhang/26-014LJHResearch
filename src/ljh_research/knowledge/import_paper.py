#!/usr/bin/env python3
"""Import a paper through topic-level source, extraction, knowledge, and concept layers."""

from __future__ import annotations

import argparse
import atexit
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

from ljh_research.knowledge.cli_output import configure_utf8
from ljh_research.workspace_contract import require_owned_workspace, resolve_project_root
from ljh_research.knowledge.topic_structure import (
    topic_dir as knowledge_topic_dir,
    validate_topic_relative,
    ensure_topic_layers,
    detect_nested_topic,
    ensure_readme,
    append_index_line,
    default_paper_id,
    paper_topic_dir,
    paper_topic_relative,
)
from ljh_research.knowledge.layout import KNOWLEDGE_DIR, research_root
from ljh_research.knowledge.template_loader import render_template


SOURCE_LIBRARY = "源文件库"
EXTRACTED_CONTENT = "提取内容"
KNOWLEDGE_LIBRARY = "知识库"
CONCEPT_LIBRARY = "概念库"


class ImportTransaction:
    """Rollback files and directories created by one paper import on failure.

    Importing spans two processes because the source index is maintained by
    ``add_source_file.py``.  A process-exit rollback hook therefore keeps the
    operation all-or-nothing for both ordinary exceptions and subprocess
    failures, while a successful import explicitly commits the transaction.
    """

    def __init__(self, root: Path, paths: list[Path]):
        self.root = root.resolve()
        self._files: dict[Path, bytes | None] = {}
        self._directories: dict[Path, bool] = {}
        self._committed = False
        self._registered = False
        for path in paths:
            self._track(path)

    def _track_directory_parents(self, path: Path) -> None:
        current = path.resolve()
        chain: list[Path] = []
        while True:
            chain.append(current)
            if current == self.root or current.parent == current:
                break
            current = current.parent
        for directory in chain:
            if self.root not in directory.parents and directory != self.root:
                continue
            self._directories.setdefault(directory, directory.is_dir())

    def _track(self, path: Path) -> None:
        original_path = path
        path = path.resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise SystemExit(
                f"import target escapes ljh research through a symlink: {original_path}"
            ) from exc
        self._track_directory_parents(path.parent)
        if path.is_dir():
            self._directories.setdefault(path, True)
        elif path.is_file():
            self._files.setdefault(path, path.read_bytes())
        else:
            self._files.setdefault(path, None)

    def begin(self) -> None:
        if not self._registered:
            atexit.register(self._rollback_at_exit)
            self._registered = True

    def commit(self) -> None:
        self._committed = True
        if self._registered:
            atexit.unregister(self._rollback_at_exit)
            self._registered = False

    def _rollback_at_exit(self) -> None:
        if not self._committed:
            self.rollback()

    def rollback(self) -> None:
        for path, original in self._files.items():
            if original is None:
                if path.is_file() or path.is_symlink():
                    path.unlink(missing_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(original)
        for directory, existed in sorted(
            self._directories.items(), key=lambda item: len(item[0].parts), reverse=True
        ):
            if existed or not directory.is_dir():
                continue
            try:
                directory.rmdir()
            except OSError:
                # Never remove unrelated files that appeared concurrently.
                pass


def safe_name(value: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", value).strip(" .")
    return name or "未命名论文"


def extract_text(source: Path) -> tuple[str, str | None]:
    if source.suffix.lower() in {".md", ".txt", ".rst"}:
        try:
            return source.read_text(encoding="utf-8"), None
        except UnicodeDecodeError:
            return source.read_text(encoding="utf-8-sig", errors="replace"), None
    if source.suffix.lower() != ".pdf":
        return "", f"不支持自动文本提取的文件类型：{source.suffix or '无扩展名'}"

    for module_name in ("pypdf", "PyPDF2"):
        try:
            module = __import__(module_name, fromlist=["PdfReader"])
            reader = module.PdfReader(str(source))
            pages = [
                f"## 第 {number} 页\n\n{page.extract_text() or ''}".rstrip()
                for number, page in enumerate(reader.pages, start=1)
            ]
            text = "\n\n".join(pages).strip()
            if text:
                return text, None
        except (ImportError, OSError, ValueError):
            continue
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(source), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            return result.stdout.strip(), None
    except (OSError, subprocess.CalledProcessError):
        pass
    return "", (
        "未找到可用的 PDF 文本提取器（pypdf、PyPDF2 或 pdftotext）。"
        "请先安装其一（如：pip install pypdf），再使用 --force-extract 重新提取。"
    )


def write_if_missing(path: Path, text: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def run_add_source_file(
    project_root: Path,
    source: Path,
    title: str,
    source_library_relative: Path,
    note: str,
    source_url: str | None = None,
) -> None:
    command = [
        sys.executable,
        "-m", "ljh_research.knowledge.add_source_file",
        "--project-root",
        str(project_root),
        "--source",
        str(source),
        "--title",
        title,
        "--library-relative",
        str(source_library_relative),
        "--note",
        note,
    ]
    if source_url:
        command += ["--original-url", source_url]
    subprocess.run(command, check=True)


SECTION_TITLES = (
    ("01-论文问题与总体架构", "论文问题与总体架构"),
    ("02-方法与模型", "方法与模型"),
    ("03-关键机制与细节", "关键机制与细节"),
    ("04-实验设置与结论", "实验设置与结论"),
    ("05-对本项目的启发", "对本项目的启发"),
)


def build_knowledge_readme(
    title: str,
    method: str,
    paper_id: str,
    source_name: str,
    concept_name: str,
    knowledge_topic_relative: Path,
    paper_topic_rel: Path,
) -> str:
    framework = "\n".join(
        f"- [[{section}|{section_title}]]" for section, section_title in SECTION_TITLES
    )
    return render_template(
        "papers/paper-knowledge.md",
        PAPER_ID=paper_id,
        PAPER_ID_JSON=json.dumps(paper_id, ensure_ascii=False),
        TITLE=title,
        TITLE_JSON=json.dumps(title, ensure_ascii=False),
        METHOD=method,
        METHOD_JSON=json.dumps(method, ensure_ascii=False),
        SOURCE_NAME=source_name,
        PAPER_TOPIC_REL=paper_topic_rel.as_posix(),
        KNOWLEDGE_TOPIC_REL=knowledge_topic_relative.as_posix(),
        CONCEPT_NAME=concept_name,
        FRAMEWORK=framework,
    )


def legacy_main() -> int:
    configure_utf8()
    parser = argparse.ArgumentParser(description="Import one paper through all ljh research knowledge layers.")
    parser.add_argument("--project-root", help="Project root. Defaults to the current directory.")
    parser.add_argument("--source", required=True, help="Paper source file, normally a PDF.")
    parser.add_argument("--title", required=True, help="Verified paper title.")
    parser.add_argument("--method", required=True, help="Main method or model name.")
    parser.add_argument("--topic-root-relative", required=True, help="0知识库/<domain>/<topic>")
    parser.add_argument("--paper-id", help="Stable paper note directory name. Defaults to NN-<method>论文.")
    parser.add_argument("--source-url", help="Original official URL of the paper for provenance.")
    parser.add_argument(
        "--force-extract",
        action="store_true",
        help="Delete an existing placeholder extraction file and re-extract the PDF.",
    )
    args = parser.parse_args()

    project_root = resolve_project_root(args.project_root)
    require_owned_workspace(project_root)
    source = Path(args.source).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Source file does not exist: {source}")
    topic_relative = validate_topic_relative(args.topic_root_relative)
    topic_dir = knowledge_topic_dir(project_root, topic_relative)
    nested = detect_nested_topic(topic_dir)
    if nested:
        raise SystemExit(
            "nested topic detected under "
            f"{topic_relative}: {[str(p.name) for p in nested]}. "
            "Import into the existing topic layers instead of creating nested topics."
        )
    method = safe_name(args.method)
    concept_name = re.sub(r"\s+", "", method)
    title = args.title.strip()
    if not title:
        raise SystemExit("--title must not be empty")
    paper_id = safe_name(args.paper_id or default_paper_id(topic_dir, method))

    paper_topic_rel = paper_topic_relative(topic_relative)
    paper_topic = paper_topic_dir(project_root, topic_relative)
    source_library_relative = paper_topic_rel / SOURCE_LIBRARY
    source_library_dir = research_root(project_root) / source_library_relative
    extracted_path = paper_topic / EXTRACTED_CONTENT / f"{paper_id}.md"
    paper_index = topic_dir / KNOWLEDGE_LIBRARY / paper_id / "README.md"

    concept_path = topic_dir / CONCEPT_LIBRARY / f"{concept_name}.md"
    transaction_paths = [
        source_library_dir / source.name,
        source_library_dir / "README.md",
        extracted_path,
        paper_index,
        concept_path,
        topic_dir / "README.md",
        paper_topic / "README.md",
        topic_dir / KNOWLEDGE_LIBRARY / "README.md",
        paper_topic / EXTRACTED_CONTENT / "README.md",
        topic_dir / CONCEPT_LIBRARY / "README.md",
    ]
    transaction_paths.extend(
        topic_dir / KNOWLEDGE_LIBRARY / paper_id / f"{section}.md"
        for section, _ in SECTION_TITLES
    )
    transaction = ImportTransaction(research_root(project_root), transaction_paths)
    transaction.begin()
    ensure_topic_layers(project_root, topic_relative)

    run_add_source_file(
        project_root,
        source,
        title,
        source_library_relative,
        f"[[{topic_relative.as_posix()}/{KNOWLEDGE_LIBRARY}/{paper_id}/README|{method} 论文]]",
        args.source_url,
    )
    copied_source = source_library_dir / source.name
    if args.force_extract and extracted_path.exists():
        extracted_path.unlink()
    extracted_text, warning = extract_text(copied_source if copied_source.is_file() else source)
    extracted_body = extracted_text or "（等待通过 PDF 阅读或 OCR 工作流补充可读文本。）"
    extraction_status = f"- 提取状态：{warning}\n" if warning else ""
    extraction_note = render_template(
        "papers/paper-extraction.md",
        PAPER_ID=paper_id,
        PAPER_ID_JSON=json.dumps(paper_id, ensure_ascii=False),
        TITLE=title,
        TITLE_JSON=json.dumps(title + " 读取内容", ensure_ascii=False),
        SOURCE_NAME=source.name,
        SOURCE_NAME_JSON=json.dumps(source.name, ensure_ascii=False),
        CREATED=date.today().isoformat(),
        EXTRACTION_STATUS=extraction_status.rstrip("\n"),
        EXTRACTED_BODY=extracted_body,
    )
    extracted_created = write_if_missing(extracted_path, extraction_note.rstrip() + "\n")

    knowledge_created = write_if_missing(
        paper_index,
        build_knowledge_readme(
            title, method, paper_id, source.name, concept_name, topic_relative, paper_topic_rel
        ),
    )
    for section, section_title in SECTION_TITLES:
        write_if_missing(
            topic_dir / KNOWLEDGE_LIBRARY / paper_id / f"{section}.md",
            render_template("papers/paper-section.md", SECTION_TITLE=section_title),
        )

    concept_created = write_if_missing(
        concept_path,
        render_template(
            "papers/concept.md",
            CONCEPT_NAME=concept_name,
            METHOD=method,
            METHOD_JSON=json.dumps(method, ensure_ascii=False),
            TITLE=title,
            PAPER_ID=paper_id,
            KNOWLEDGE_TOPIC_REL=topic_relative.as_posix(),
            PAPER_TOPIC_REL=paper_topic_rel.as_posix(),
        ),
    )

    # Auto-maintain topic-level indexes (idempotent appends).
    ensure_readme(topic_dir / "README.md", topic_relative.parts[-1])
    ensure_readme(paper_topic / "README.md", topic_relative.parts[-1])
    ensure_readme(topic_dir / KNOWLEDGE_LIBRARY / "README.md", "知识库")
    ensure_readme(paper_topic / EXTRACTED_CONTENT / "README.md", "提取内容")
    ensure_readme(topic_dir / CONCEPT_LIBRARY / "README.md", "概念库")
    append_index_line(
        topic_dir / "README.md",
        f"- [[{topic_relative.as_posix()}/{KNOWLEDGE_LIBRARY}/{paper_id}/README|{method} 论文]]",
    )
    append_index_line(
        topic_dir / KNOWLEDGE_LIBRARY / "README.md",
        f"- [[{topic_relative.as_posix()}/{KNOWLEDGE_LIBRARY}/{paper_id}/README|{method} 论文]]",
    )
    append_index_line(
        paper_topic / "README.md",
        f"- [[{paper_topic_rel.as_posix()}/{EXTRACTED_CONTENT}/{paper_id}|{method} 论文提取内容]]",
    )
    append_index_line(
        paper_topic / EXTRACTED_CONTENT / "README.md",
        f"- [[{paper_topic_rel.as_posix()}/{EXTRACTED_CONTENT}/{paper_id}|{method} 论文提取内容]]",
    )
    append_index_line(
        topic_dir / CONCEPT_LIBRARY / "README.md",
        f"- [[{topic_relative.as_posix()}/{CONCEPT_LIBRARY}/{concept_name}|{method}]]",
    )

    transaction.commit()
    print(f"topic_dir={topic_dir}")
    print(f"source_library={source_library_dir}")
    print(f"extracted_content={extracted_path}")
    print(f"knowledge_index={paper_index}")
    print(f"concept_note={concept_path}")
    print(f"extracted_created={str(extracted_created).lower()}")
    print(f"knowledge_created={str(knowledge_created).lower()}")
    print(f"concept_created={str(concept_created).lower()}")
    if warning:
        print(f"extraction_warning={warning}")
    return 0


def main() -> int:
    import os
    if "--legacy-layout" in sys.argv or os.environ.get("LJH_RESEARCH_LEGACY_LAYOUT") == "1":
        if "--legacy-layout" in sys.argv:
            sys.argv.remove("--legacy-layout")
        return legacy_main()
    configure_utf8()
    parser = argparse.ArgumentParser(description="Import a paper into flat sources and layered scientific memory")
    parser.add_argument("--project-root")
    parser.add_argument("--source", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--method", default="")
    parser.add_argument("--topic", action="append", default=[])
    parser.add_argument("--topic-root-relative", help="Deprecated classification hint, never a storage path")
    parser.add_argument("--paper-id")
    parser.add_argument("--source-url")
    parser.add_argument("--force-extract", action="store_true")
    args = parser.parse_args()
    root = resolve_project_root(args.project_root)
    require_owned_workspace(root)
    from ljh_research.memory.repository import Memory
    source = Path(args.source).expanduser().resolve()
    topics = args.topic or ([Path(args.topic_root_relative).parts[-1]] if args.topic_root_relative else [])
    copied_input = None
    if not source.is_relative_to(root):
        import shutil
        copied_input = research_root(root) / ".runtime/memory/inbox" / source.name
        copied_input.parent.mkdir(parents=True, exist_ok=True)
        if copied_input.exists():
            raise SystemExit("Import staging file exists; inspect it before retrying")
        shutil.copy2(source, copied_input)
    try:
        request = {"kind": "paper", "title": args.title, "path": (copied_input or source).relative_to(root).as_posix(),
                   "topics": topics, "keywords": [args.method] if args.method else [], "origin": args.source_url or str(source)}
        if args.paper_id:
            request["id"] = args.paper_id
        result = Memory(root).import_object(request)
        if args.force_extract:
            Memory(root).extract({"id": result["id"], "refresh_text": True})
        record = Memory(root).get(result["id"])
        print(f"paper_id={result['id']}")
        print(f"exists={str(result['existing']).lower()}")
        print(f"source_library={research_root(root) / '1论文/源文件库'}")
        print(f"copied={root / record['sources'][0]['path']}")
        print(f"extracted_content={research_root(root) / '1论文/提取内容' / result['id'] / '全文.md'}")
        print(f"knowledge_index={root / result['record']}")
        for key in ("extracted_created", "knowledge_created"):
            print(f"{key}={str(not result['existing']).lower()}")
        print("concept_created=false")
    finally:
        if copied_input:
            copied_input.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
