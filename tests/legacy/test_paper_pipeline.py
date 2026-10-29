from __future__ import annotations



import functools

import http.server

import importlib.util

import locale

import subprocess

import sys

import tempfile

import threading

import unittest

from pathlib import Path



SKILL_DIR = Path(__file__).resolve().parents[2]

SCRIPTS = SKILL_DIR / "tools" / "compat"





def load_script_module(name: str):

    if str(SCRIPTS) not in sys.path:

        sys.path.insert(0, str(SCRIPTS))

    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")

    module = importlib.util.module_from_spec(spec)

    assert spec.loader is not None

    spec.loader.exec_module(module)

    return module





def run_script(name: str, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:

    return subprocess.run(

        [sys.executable, str(SCRIPTS / name), *args],

        cwd=str(cwd or SKILL_DIR),

        check=True,

        capture_output=True,

        text=True,

        encoding=locale.getpreferredencoding(False),

        errors="replace",

    )





def run_script_allow_failure(

    name: str, *args: str, cwd: Path | None = None

) -> subprocess.CompletedProcess[str]:

    return subprocess.run(

        [sys.executable, str(SCRIPTS / name), *args],

        cwd=str(cwd or SKILL_DIR),

        check=False,

        capture_output=True,

        text=True,

        encoding=locale.getpreferredencoding(False),

        errors="replace",

    )





def have_pypdf() -> bool:

    try:

        import pypdf  # noqa: F401

        return True

    except ImportError:

        return False





def make_pdf(path: Path, title: str) -> None:

    from pypdf import PdfWriter



    writer = PdfWriter()

    writer.add_blank_page(width=200, height=200)

    writer.add_metadata({"/Title": title})

    with open(path, "wb") as handle:

        writer.write(handle)





class PaperServer:

    def __init__(self, root: Path):

        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)

        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)



    def start(self) -> str:

        self.thread.start()

        return f"http://127.0.0.1:{self.server.server_port}"



    def stop(self) -> None:

        self.server.shutdown()

        self.server.server_close()

        self.thread.join(timeout=5)





class CcfVenueTests(unittest.TestCase):

    def test_lookup_abbreviations_aliases_and_case(self) -> None:

        cases = {

            "WWW": "WWW",

            "www": "WWW",

            "The Web Conference": "WWW",

            "ACM WWW": "WWW",

            "ACM MM": "ACMMM",

            "acmmm": "ACMMM",

            "NeurIPS": "NeurIPS",

            "nips": "NeurIPS",

            "SIGIR": "SIGIR",

            "IEEE VIS": "VIS",

            "KDD": "KDD",

        }

        for query, expected_abbr in cases.items():

            with self.subTest(query=query):

                result = run_script("ccf_venue.py", "--venue", query)

                self.assertIn("found=true", result.stdout)

                self.assertIn(f"venue={expected_abbr}", result.stdout)

                self.assertIn("rating=A", result.stdout)

                self.assertIn("ccf_list=2022", result.stdout)



    def test_unknown_and_not_in_ccf(self) -> None:

        unknown = run_script("ccf_venue.py", "--venue", "MyUnknownConf")

        self.assertIn("found=false", unknown.stdout)

        self.assertIn("rating=unknown", unknown.stdout)

        iclr = run_script("ccf_venue.py", "--venue", "ICLR")

        self.assertIn("found=false", iclr.stdout)

        self.assertIn("not_in_ccf=true", iclr.stdout)



    def test_list_all(self) -> None:

        result = run_script("ccf_venue.py", "--list")

        self.assertIn("|A|conference|2022", result.stdout)

        self.assertIn("|A|journal|2022", result.stdout)

        self.assertEqual(len([line for line in result.stdout.splitlines() if line.strip()]), 31)

        self.assertIn("WWW|The Web Conference|A|conference|2022", result.stdout)

        self.assertIn("ACMMM|ACM International Conference on Multimedia|A|conference|2022", result.stdout)





class UrlNormalizationTests(unittest.TestCase):

    def setUp(self) -> None:

        self.module = load_script_module("download_paper")



    def test_arxiv_abs_to_pdf(self) -> None:

        cases = {

            "https://arxiv.org/abs/2604.26247": "https://arxiv.org/pdf/2604.26247",

            "http://export.arxiv.org/abs/2604.26247v2": "https://arxiv.org/pdf/2604.26247v2",

            "https://arxiv.org/pdf/2604.26247": "https://arxiv.org/pdf/2604.26247",

        }

        for url, expected in cases.items():

            with self.subTest(url=url):

                self.assertEqual(self.module.normalize_url(url), expected)



    def test_doi_prefix(self) -> None:

        self.assertEqual(

            self.module.normalize_url("doi:10.1609/aaai.v40i18.38558"),

            "https://doi.org/10.1609/aaai.v40i18.38558",

        )



    def test_direct_pdf_detection(self) -> None:

        self.assertTrue(self.module.is_direct_pdf("https://example.com/paper.pdf"))

        self.assertFalse(self.module.is_direct_pdf("https://arxiv.org/abs/2604.26247"))





@unittest.skipUnless(have_pypdf(), "pypdf not available")

class DownloadPaperTests(unittest.TestCase):

    def setUp(self) -> None:

        self.temp = tempfile.TemporaryDirectory(prefix="ljh-download-test-")

        self.root = Path(self.temp.name)

        self.server = PaperServer(self.root)

        self.base = self.server.start()

        make_pdf(self.root / "paper.pdf", "Expected Title")



    def tearDown(self) -> None:

        self.server.stop()

        self.temp.cleanup()



    def test_download_verify_and_name(self) -> None:

        out_dir = self.root / "out"

        result = run_script(

            "download_paper.py",

            "--url",

            f"{self.base}/paper.pdf",

            "--title",

            "Expected Title",

            "--out-dir",

            str(out_dir),

        )

        self.assertIn("exists=false", result.stdout)

        self.assertIn("title_match=true", result.stdout)

        self.assertIn("pages=1", result.stdout)

        target = out_dir / "Expected-Title.pdf"

        self.assertTrue(target.is_file())

        self.assertIn(f"file={target}", result.stdout)

        self.assertEqual(target.read_bytes()[:5], b"%PDF-")



    def test_rejects_non_pdf(self) -> None:

        (self.root / "note.html").write_text("<html>not a pdf</html>", encoding="utf-8")

        out_dir = self.root / "out2"

        result = run_script_allow_failure(

            "download_paper.py",

            "--url",

            f"{self.base}/note.html",

            "--out-dir",

            str(out_dir),

        )

        self.assertNotEqual(result.returncode, 0)

        self.assertIn("not a valid PDF", result.stderr)

        self.assertEqual(list(out_dir.glob("*.pdf")), [])



    def test_title_mismatch_is_warning(self) -> None:

        make_pdf(self.root / "other.pdf", "Different Title")

        out_dir = self.root / "out3"

        result = run_script(

            "download_paper.py",

            "--url",

            f"{self.base}/other.pdf",

            "--title",

            "Expected Title",

            "--out-dir",

            str(out_dir),

        )

        self.assertEqual(result.returncode, 0)

        self.assertIn("title_match=false", result.stdout)





@unittest.skipUnless(have_pypdf(), "pypdf not available")

class AutoIngestTests(unittest.TestCase):

    def test_download_import_chain_and_dedup(self) -> None:

        import hashlib

        import os



        with tempfile.TemporaryDirectory(prefix="ljh-ingest-test-") as temp:

            root = Path(temp)

            server = PaperServer(root)

            base = server.start()

            try:

                fixture = root / "paper.pdf"

                make_pdf(fixture, "Test Paper Title")

                run_script("init_ljh_research.py", "create", "--project-root", str(root))

                args = (

                    "download_paper.py", "--url", f"{base}/paper.pdf",

                    "--title", "Test Paper Title", "--venue", "WWW", "--year", "2026",

                    "--project-root", str(root), "--topic-root-relative", "0知识库/Test/Topic",

                    "--method", "TestMethod",

                )



                def run_ingest() -> subprocess.CompletedProcess[str]:

                    return subprocess.run(

                        [sys.executable, str(SCRIPTS / args[0]), *args[1:]],

                        cwd=str(SKILL_DIR), check=True, capture_output=True,

                        text=True, encoding="utf-8", errors="strict",

                        env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},

                    )



                def fields(output: str) -> dict[str, str]:

                    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)



                first = fields(run_ingest().stdout)

                self.assertEqual(first.get("imported"), "true")

                self.assertEqual(first.get("exists"), "false")

                self.assertEqual(first.get("pages"), "1")

                self.assertEqual(first.get("pdf_title"), "Test Paper Title")

                self.assertEqual(first.get("title_match"), "true")

                for key in ("extracted_created", "knowledge_created", "concept_created"):

                    self.assertEqual(first.get(key), "true")



                workspace = root / "ljh research docs"

                knowledge_topic = workspace / "0知识库" / "Test" / "Topic"

                paper_topic = workspace / "1论文" / "Test" / "Topic"

                source_library = paper_topic / "源文件库"

                expected_pdf = source_library / "Test-Paper-Title-WWW2026.pdf"

                extraction = paper_topic / "提取内容" / "PAPER-0001.md"

                knowledge = knowledge_topic / "知识库" / "PAPER-0001" / "README.md"

                concept = knowledge_topic / "概念库" / "TestMethod.md"

                expected = {

                    "topic_dir": knowledge_topic, "source_library": source_library,

                    "copied": expected_pdf, "extracted_content": extraction,

                    "knowledge_index": knowledge, "concept_note": concept,

                    "file": workspace / "_downloads" / "Test-Paper-Title-WWW2026.pdf",

                }

                for key, path in expected.items():

                    self.assertIn(key, first)

                    self.assertEqual(Path(first[key]).resolve(), path.resolve())

                    self.assertTrue(path.is_dir() if key in {"topic_dir", "source_library"} else path.is_file())

                self.assertEqual(expected_pdf.read_bytes(), fixture.read_bytes())

                self.assertEqual(expected["file"].read_bytes(), fixture.read_bytes())

                self.assertRegex(knowledge.read_text(encoding="utf-8"), r"(?m)^id: PAPER-0001$")

                self.assertRegex(extraction.read_text(encoding="utf-8"), r"(?m)^id: EXTRACT-PAPER-0001$")

                self.assertIn('paper_id: "PAPER-0001"', extraction.read_text(encoding="utf-8"))

                for section in (

                    "01-论文问题与总体架构", "02-方法与模型", "03-关键机制与细节",

                    "04-实验设置与结论", "05-对本项目的启发",

                ):

                    self.assertTrue((knowledge.parent / f"{section}.md").is_file())

                self.assertFalse((root / "ljh research").exists())

                readme = (source_library / "README.md").read_text(encoding="utf-8")

                self.assertIn("官方来源 URL", readme)

                self.assertIn(f"{base}/paper.pdf", readme)

                self.assertIn(expected_pdf.name, readme)



                def snapshot() -> dict[str, tuple[str, str | None]]:

                    return {

                        p.relative_to(workspace).as_posix():

                        ("file", hashlib.sha256(p.read_bytes()).hexdigest()) if p.is_file()

                        else ("directory", None)

                        for p in workspace.rglob("*")

                    }



                before_repeat = snapshot()

                second = fields(run_ingest().stdout)

                self.assertEqual(second.get("exists"), "true")

                self.assertEqual(second.get("query"), "Test Paper Title")

                self.assertIn("duplicate", second.get("skipped", ""))

                self.assertNotIn("imported", second)

                self.assertNotIn("file", second)

                self.assertNotIn("copied", second)

                self.assertEqual(snapshot(), before_repeat)

                self.assertEqual(len(list(source_library.glob("*.pdf"))), 1)

                self.assertEqual(len(list((workspace / "_downloads").glob("*.pdf"))), 1)

                self.assertEqual(len(list((paper_topic / "提取内容").glob("PAPER-*.md"))), 1)

                self.assertEqual(len(list((knowledge_topic / "知识库").glob("PAPER-*"))), 1)

            finally:

                server.stop()



    def test_method_required_for_ingest(self) -> None:

        with tempfile.TemporaryDirectory(prefix="ljh-ingest-test-") as temp:

            root = Path(temp)

            result = run_script_allow_failure(

                "download_paper.py",

                "--url",

                "https://example.com/paper.pdf",

                "--project-root",

                str(root),

                "--topic-root-relative",

                "0知识库/Test/Topic",
            )

            self.assertNotEqual(result.returncode, 0)

            self.assertIn("--method", result.stderr)





if __name__ == "__main__":

    unittest.main()
