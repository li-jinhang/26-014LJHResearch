"""Source-grounded memory with bounded retrieval and explicit evidence drill-down."""
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

from ..errors import ResearchError, require
from ..workspace_contract import require_owned_workspace
from .layout import KINDS, MARKER
from .extract import ASPECTS, ALIASES, candidates, contains, outline, query_terms

FENCE = re.compile(r"```ljh-memory\n(.*?)\n```", re.S)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == data:
        return
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_bytes(data)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def bounded(value, budget):
    """Budget the entire JSON result in Unicode characters, not guessed tokens."""
    require(type(budget) is int and 600 <= budget <= 50000, "invalid_budget", "budget_chars must be 600..50000")
    value.update(budget_chars=budget, used_chars=0)
    for _ in range(5):
        value["used_chars"] = len(json.dumps(value, ensure_ascii=False))
    require(value["used_chars"] <= budget, "context_budget", "Requested unit exceeds the context budget; choose a section/point or a larger budget", {"needed_chars": value["used_chars"]})
    return value


class Memory:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.workspace = require_owned_workspace(self.root)
        marker = self.workspace / MARKER
        require(marker.is_file(), "memory_setup_required", "Use setup repair to prepare layered memory")
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        require(data == {"kind": "ljh-layered-memory", "schema_version": 1} and type(data.get("schema_version")) is int,
                "memory_schema", "Unsupported or unowned memory layout")

    def path(self, relative, *, inside_memory=True):
        require(isinstance(relative, str) and relative and not Path(relative).is_absolute() and ".." not in Path(relative).parts,
                "invalid_path", "Use a project-relative memory/source path")
        path = self.root / relative
        base = self.workspace if inside_memory else self.root
        require(path.resolve().is_relative_to(base), "invalid_path", "Path escapes its authorized root")
        return path

    def record_path(self, identifier, kind=None):
        require(isinstance(identifier, str) and re.fullmatch(r"(?:PAPER|RP|EXP|PRE|MEXP|REPRO|REP|RD)-\d{3,}", identifier), "invalid_memory_id", "Use a stable memory object ID")
        kinds = [kind] if kind else KINDS
        for candidate in kinds:
            require(candidate in KINDS, "invalid_memory_kind", "Unknown memory kind")
            _, folder, single, _ = KINDS[candidate]
            path = self.path(f"{self.workspace.name}/{folder}/{single}/{identifier}/摘要.md")
            if kind or path.is_file():
                return path
        raise ResearchError("not_found", "Memory object is not registered", {"id": identifier})

    def records(self):
        for _, folder, single, _ in KINDS.values():
            for path in sorted((self.workspace / folder / single).glob("*/摘要.md")):
                require(path.resolve().is_relative_to(self.workspace), "invalid_path", "Memory record escapes workspace")
                match = FENCE.search(path.read_text(encoding="utf-8"))
                if match:
                    yield json.loads(match[1])

    def get(self, identifier):
        path = self.record_path(identifier)
        match = FENCE.search(path.read_text(encoding="utf-8"))
        require(match is not None, "memory_schema", "Malformed memory record")
        return json.loads(match[1])

    def save(self, record):
        path = self.record_path(record["id"], record["kind"])
        text = (f"---\nid: MEMORY-{record['id']}\ntype: memory_object\nschema_version: 1\n---\n\n# {record['title']}\n\n"
                "本卡是单项提炼。结构抽取只代表原文或已有笔记的记录；科研判断须保留条件与来源。\n\n```ljh-memory\n"
                + json.dumps(record, ensure_ascii=False, indent=2) + "\n```\n")
        write(path, text.encode("utf-8"))

    def freshness(self, record):
        changed = []
        for source in record["sources"]:
            path = self.path(source["path"])
            if not path.is_file() or digest(path.read_bytes()) != source["sha256"]:
                changed.append(source["id"])
        return {"state": "stale" if changed else "current", "changed_sources": changed}

    def import_object(self, p):
        kind = p.get("kind")
        require(kind in KINDS, "invalid_memory_kind", "Choose paper, experiment, research_point, reproduction or experience")
        title = p.get("title", "")
        require(isinstance(title, str) and title.strip() and len(title) <= 400 and not re.search(r"[\r\n\x00]", title), "invalid_memory", "A concise single-line verified title is required")
        source = self.path(p["path"], inside_memory=False)
        require(source.is_file() and source.suffix.lower() in {".md", ".txt", ".pdf"} and source.stat().st_size <= 50_000_000,
                "invalid_source", "Expected a text/PDF source up to 50 MB")
        primary = digest(source.read_bytes())
        existing = list(self.records())
        for old in existing:
            if old["kind"] == kind and old["sources"][0]["sha256"] == primary:
                require(not p.get("id") or p["id"] == old["id"], "duplicate_source", "Source already has another stable ID", {"id": old["id"]})
                topics = self._strings(p.get("topics", []), "topics")
                for topic in topics:
                    self.topic_path(topic, kind)
                notes_added = False
                for name in self._strings(p.get("reading_notes", []), "reading_notes"):
                    note = self.path(name, inside_memory=False)
                    require(note.is_file() and note.suffix.lower() in {".md", ".txt"} and note.stat().st_size <= 2_000_000, "invalid_source", "Reading notes must be bounded text")
                    data = note.read_bytes()
                    data.decode("utf-8")
                    if any(s["sha256"] == digest(data) for s in old["sources"]):
                        continue
                    index = max([int(s["id"][1:]) for s in old["sources"] if re.fullmatch(r"S\d+", s["id"])] + [0]) + 1
                    destination = self.workspace / KINDS[kind][1] / ("提取内容/" + old["id"] if kind == "paper" else KINDS[kind][3]) / f"{old['id']}-研读材料-{index:02d}.md"
                    self.path(self.relative(destination))
                    require(not destination.exists(), "revision_conflict", "Reading-note destination already exists")
                    write(destination, data)
                    old["sources"].append({"id": f"S{index:02d}", "path": self.relative(destination), "sha256": digest(data), "role": "reading_note", "format": "md", "origin": self.relative(note)})
                    notes_added = True
                if set(topics) - set(old["topics"]):
                    old["topics"] = sorted(set(old["topics"] + topics))
                    self.save(old)
                    self.rebuild()
                result = {"id": old["id"], "existing": True, "record": self.relative(self.record_path(old["id"]))}
                if notes_added:
                    self.save(old)
                    result["extraction"] = self.extract({"id": old["id"]})
                return result
        prefix, folder, _, detail = KINDS[kind]
        number = max([int(m[1]) for path in self.workspace.rglob(prefix + "-*.md") if (m := re.match(prefix + r"-(\d+)", path.name))]
                     + [int(o["id"].split("-")[-1]) for o in existing if o["kind"] == kind] + [0]) + 1
        identifier = p.get("id") or f"{prefix}-{number:04d}"
        require(re.fullmatch(("(?:EXP|PRE|MEXP)" if kind == "experiment" else "(?:REPRO|REP)" if kind == "reproduction" else prefix) + r"-\d{3,}", identifier),
                "invalid_memory_id", "Stable ID prefix does not match object kind")
        target = self.record_path(identifier, kind)
        require(not target.exists(), "revision_conflict", "Stable ID already exists; update its registered evidence explicitly")
        topics = self._strings(p.get("topics", []), "topics")
        for topic in topics:
            self.topic_path(topic, kind)
        keywords = self._strings(p.get("keywords", []), "keywords")
        inputs = [source]
        for name in self._strings(p.get("reading_notes", []), "reading_notes"):
            note = self.path(name, inside_memory=False)
            require(note.is_file() and note.suffix.lower() in {".md", ".txt"} and note.stat().st_size <= 2_000_000, "invalid_source", "Reading notes must be bounded text files")
            inputs.append(note)
        planned = []
        sources = []
        for index, original in enumerate(inputs):
            if p.get("reference_only"):
                require(original.resolve().is_relative_to(self.workspace), "invalid_path", "Referenced records must already belong to this workspace")
                destination = original
            elif kind == "paper":
                destination = (self.workspace / folder / detail / (identifier + original.suffix.lower()) if index == 0 else
                               self.workspace / folder / "提取内容" / identifier / f"研读材料-{index:02d}.md")
            else:
                if index:
                    destination = self.workspace / folder / detail / identifier / f"附件{index}.md"
                else:
                    suffix = "-record" if kind in {"experiment", "research_point", "reproduction"} else ""
                    destination = self.workspace / folder / detail / (identifier + suffix + original.suffix.lower())
            require(not destination.exists() or destination.read_bytes() == original.read_bytes(), "revision_conflict", "A destination contains different evidence")
            self.path(self.relative(destination))
            raw = original.read_bytes()
            if original.suffix.lower() != ".pdf":
                require(len(raw) <= 2_000_000, "invalid_source", "Use smaller text evidence units up to 2 MB")
                raw.decode("utf-8")
            planned.append((destination, raw))
            sources.append({"id": f"S{index+1:02d}", "path": self.relative(destination), "sha256": digest(raw),
                            "role": "reading_note" if index else "original", "origin": p.get("origin", self.relative(original)) if index == 0 else self.relative(original),
                            "format": original.suffix.lower().lstrip(".")})
        if kind == "paper":
            if source.suffix.lower() == ".pdf":
                from ..knowledge.import_paper import extract_text
                text, warning = extract_text(source)
            else:
                text, warning = source.read_text(encoding="utf-8"), None
            extracted = self.workspace / folder / "提取内容" / identifier / "全文.md"
            require(not extracted.exists(), "revision_conflict", "Extraction already exists without this record")
            data = (text or "# 提取待补充\n\n源文件尚无可用文本；需要 OCR 或人工核验。\n").encode("utf-8")
            planned.append((extracted, data))
            sources.append({"id": "TEXT", "path": self.relative(extracted), "sha256": digest(data), "role": "extracted_text", "format": "md", "origin": sources[0]["path"], "extraction_warning": warning})
        else:
            warning = None
        record = {"schema_version": 1, "id": identifier, "kind": kind, "title": title, "topics": topics, "keywords": keywords,
                  "sources": sources, "claims": [], "extraction": {"mode": "pending", "coverage": [], "warning": warning}, "updated_at": time.time()}
        created = []
        try:
            for destination, raw in planned:
                if not destination.exists():
                    created.append(destination)
                write(destination, raw)
            self.save(record)
            created.append(target)
            result = self.extract({"id": identifier})
        except BaseException:
            for destination in reversed(created):
                destination.unlink(missing_ok=True)
            raise
        return {"id": identifier, "existing": False, "record": self.relative(target), "extraction": result}

    @staticmethod
    def _strings(value, field):
        require(isinstance(value, list) and len(value) <= 30 and all(isinstance(x, str) and 0 < len(x.strip()) <= (1800 if field == "conditions" else 160) for x in value), "invalid_memory", field + " must be a short string array")
        return list(dict.fromkeys(x.strip() for x in value))

    def relative(self, path):
        return path.relative_to(self.root).as_posix()

    def _text_source(self, record, source_id):
        source = next((s for s in record["sources"] if s["id"] == source_id), None)
        require(source is not None and source["format"] in {"md", "txt"}, "invalid_source", "Select a text source ID from the outline")
        path = self.path(source["path"])
        require(path.is_file() and path.stat().st_size <= 2_000_000, "invalid_source", "Text source is absent or too large")
        data = path.read_bytes()
        return {**source, "sha256": digest(data)}, data.decode("utf-8")

    def extract(self, p):
        record = self.get(p["id"])
        if p.get("refresh_text") and record["kind"] == "paper":
            original = record["sources"][0]
            path = self.path(original["path"])
            require(digest(path.read_bytes()) == original["sha256"], "source_changed", "Register a changed original as a new version")
            extracted = next(s for s in record["sources"] if s["id"] == "TEXT")
            target = self.path(extracted["path"])
            require(digest(target.read_bytes()) == extracted["sha256"], "revision_conflict", "Preserve locally edited extraction before refreshing")
            from ..knowledge.import_paper import extract_text
            text, warning = extract_text(path)
            write(target, (text or "# 提取待补充\n\n需要 OCR 或人工核验。\n").encode("utf-8"))
            extracted.update(sha256=digest(target.read_bytes()), extraction_warning=warning)
        claims = []
        coverage = []
        supplied = p.get("claims")
        require(supplied is None or isinstance(supplied, list) and 0 < len(supplied) <= 24, "invalid_extraction", "Supply up to 24 source-grounded claims")
        if supplied is None:
            text_sources = sorted([s for s in record["sources"] if s["format"] in {"md", "txt"}], key=lambda s: s["role"] != "reading_note")
            for source in text_sources:
                if source.get("extraction_warning"):
                    continue
                if record["kind"] == "paper" and any(s["role"] == "reading_note" for s in text_sources) and source["role"] != "reading_note":
                    continue
                if record["kind"] == "paper" and not any(s["role"] == "reading_note" for s in text_sources) and source["id"] != "TEXT":
                    continue
                current, text = self._text_source(record, source["id"])
                coverage.append({"source_id": source["id"], "source_sha256": current["sha256"], "mode": "structural_scan", "sections": outline(text)})
                items = list(candidates(text))
                scopes = [c for c in items if c["aspect"] == "condition"][:2] + [c for c in items if c["aspect"] == "limitation"][:1]
                priorities = (["architecture", "innovation", "application", "limitation", "hypothesis"] if record["kind"] == "paper" else
                              ["result", "limitation", "lesson", "condition", "hypothesis"])
                items.sort(key=lambda c: (priorities.index(c["aspect"]) if c["aspect"] in priorities else 10, c["start_line"]))
                for item in items[:16]:
                    claims.append({"text": item["text"], "aspect": item["aspect"], "keywords": [],
                        "conditions": ["现有文档摘取，未独立核验原始实验或论文；逐轮条件差异须下钻核实。", *[s["text"] for s in scopes]],
                        "evidence_type": "reading_note" if source["role"] == "reading_note" else "paper_claim" if record["kind"] == "paper" else "project_record",
                        "citations": [{"source_id": source["id"], "source_sha256": current["sha256"], "start_line": s["start_line"], "end_line": s["end_line"], "quote": s["text"]}
                                      for s in [item, *[s for s in scopes if s is not item]]]})
            claims = claims[:24]
        else:
            claims = supplied
        checked = []
        for point in claims:
            require(isinstance(point, dict) and isinstance(point.get("text"), str) and 0 < len(point["text"]) <= 2200,
                    "invalid_extraction", "Every claim needs bounded text")
            require(point.get("aspect") in {*ASPECTS, "overview", "unknown"}, "invalid_extraction", "Unknown knowledge aspect")
            require(point.get("evidence_type") in {"paper_claim", "reading_note", "project_record", "agent_inference", "open_question"}, "invalid_extraction", "Separate source claims, project records, inference and unknowns")
            conditions = self._strings(point.get("conditions", []), "conditions")
            require(conditions, "conditions_required", "Preserve applicability conditions or explicitly state what is unknown")
            citations = point.get("citations", [])
            require(isinstance(citations, list) and 1 <= len(citations) <= 8, "citation_required", "Every knowledge point needs one to eight exact source citations")
            for citation in citations:
                require(isinstance(citation, dict), "invalid_citation", "Citation must be an object")
                source, text = self._text_source(record, citation.get("source_id"))
                require(citation.get("source_sha256") == source["sha256"], "stale_source", "Read current evidence before extracting")
                start, end = citation.get("start_line"), citation.get("end_line")
                require(type(start) is int and type(end) is int and 1 <= start <= end <= len(text.splitlines()), "invalid_citation", "Citation lines are outside the source")
                snippet = "\n".join(text.splitlines()[start-1:end]).strip()
                require(isinstance(citation.get("quote"), str) and 0 < len(citation["quote"].strip()) <= 6000 and citation["quote"].strip() in snippet,
                        "invalid_citation", "Quoted evidence must occur in the specified source lines")
                if supplied is not None:
                    coverage.append({"source_id": source["id"], "source_sha256": source["sha256"], "mode": "agent_selected", "start_line": start, "end_line": end})
            value = {"text": point["text"], "aspect": point["aspect"], "conditions": conditions,
                     "keywords": self._strings(point.get("keywords", []), "keywords"), "evidence_type": point["evidence_type"], "citations": citations,
                     "extraction_mode": point.get("extraction_mode", "agent_semantic" if supplied is not None else "extractive")}
            require(value["extraction_mode"] in {"agent_semantic", "extractive"}, "invalid_extraction", "Unknown point extraction mode")
            value["point_id"] = "K-" + digest(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8"))[:14]
            if not any(c["point_id"] == value["point_id"] for c in checked):
                checked.append(value)
        if supplied is not None:
            supersedes = self._strings(p.get("supersedes", []), "supersedes")
            require(set(supersedes) <= {c["point_id"] for c in record["claims"]}, "not_found", "Only existing knowledge points can be superseded")
            retained = []
            for old in record["claims"]:
                valid = all(self._text_source(record, c["source_id"])[0]["sha256"] == c["source_sha256"] for c in old["citations"])
                if valid and old["point_id"] not in supersedes and not any(c["point_id"] == old["point_id"] for c in checked):
                    retained.append(old)
            checked = retained + checked
        else:
            # Newly imported reading notes must not discard prior semantic work.
            for old in record["claims"]:
                valid = all(self._text_source(record, c["source_id"])[0]["sha256"] == c["source_sha256"] for c in old["citations"])
                if old.get("extraction_mode") == "agent_semantic" and valid and not any(c["point_id"] == old["point_id"] for c in checked):
                    checked.append(old)
        if record["claims"] == checked and record["extraction"].get("mode") == ("agent_semantic" if supplied is not None else "extractive") and self.freshness(record)["state"] == "current":
            return {"id": record["id"], "changed": False, "points": len(checked), "mode": record["extraction"]["mode"]}
        for source in record["sources"]:
            path = self.path(source["path"])
            if path.is_file():
                require(not (record["kind"] == "paper" and source["role"] == "original") or source["sha256"] == digest(path.read_bytes()),
                        "source_changed", "Paper original changed; register its new version instead of marking the old extraction current")
                source["sha256"] = digest(path.read_bytes())
        if not record["topics"]:
            meaningful = record["title"] + " " + " ".join(c["text"] for c in checked[:8])
            record["topics"] = [group[0] for group in ALIASES[:3] if any(contains(meaningful, t) for t in group)] or ["待归类"]
        record["keywords"] = sorted(set(record["keywords"] + [g[0] for g in ALIASES if any(contains(record["title"] + " " + " ".join(c["text"] for c in checked), t) for t in g)]))
        record.update(claims=checked, extraction={"mode": "agent_semantic" if supplied is not None else "extractive", "coverage": coverage,
                      "state": "partial" if checked else "pending", "note": "覆盖仅限已引用片段；不等同于全文研读或科研验证。"}, updated_at=time.time())
        previous = self.record_path(record["id"])
        if previous.is_file():
            content = previous.read_bytes()
            history = self.path(f"{self.workspace.name}/.runtime/memory/history/{record['id']}/{digest(content)}.md")
            write(history, content)
        self.save(record)
        view_status = {"state": "current"}
        try:
            self.rebuild()
        except (ResearchError, OSError) as exc:
            view_status = {"state": "needs_rebuild", "message": str(exc)}
        record["derived_state"] = view_status["state"]
        self.save(record)
        return {"id": record["id"], "changed": True, "points": len(checked), "mode": record["extraction"]["mode"], "coverage": "partial", "derived_views": view_status}

    def status(self):
        records = list(self.records())
        return {"objects": len(records), "by_kind": {k: sum(r["kind"] == k for r in records) for k in KINDS},
                "stale_ids": [r["id"] for r in records if self.freshness(r)["state"] == "stale"],
                "pending_ids": [r["id"] for r in records if not r["claims"]],
                "views_pending": [r["id"] for r in records if r.get("derived_state") == "needs_rebuild"], "coverage": "registered_objects_only"}

    @staticmethod
    def facets(record):
        return sorted(set(record["topics"] + [k for k in record["keywords"] if k in {group[0] for group in ALIASES}]))

    def owned_write(self, path, content):
        self.path(self.relative(path))
        require(not path.exists() or "<!-- ljh-memory-owned -->" in path.read_text(encoding="utf-8"),
                "memory_conflict", "Preserve user-authored derived notes before rebuilding", {"path": self.relative(path)})
        write(path, content)

    def rebuild(self):
        records = list(self.records())
        topics = sorted({topic for record in records for topic in self.facets(record)})
        for topic in topics:
            for kind in [*KINDS, "all"]:
                selected = [r for r in records if topic in self.facets(r) and (kind == "all" or kind == r["kind"])]
                if not selected:
                    continue
                path = self.topic_path(topic, kind)
                if path.exists():
                    require("<!-- ljh-memory-owned -->" in path.read_text(encoding="utf-8"), "memory_conflict", "Preserve user-authored topic notes before rebuilding")
                lines = ["# " + topic, "", "<!-- ljh-memory-owned -->", "", "以下为有来源的提炼入口，保留来源性质和适用条件；未覆盖全部项目资料。", ""]
                for record in selected:
                    lines.extend([f"## {record['id']} · {record['title']}", "", f"- 来源类型：{record['kind']}；提取方式：{record['extraction']['mode']}；新鲜度：{self.freshness(record)['state']}。"])
                    points = record["claims"]
                    if record["kind"] == "paper":
                        points = [c for c in points if c["aspect"] in {"architecture", "innovation", "application", "limitation", "hypothesis"}]
                    for point in points[:4]:
                        if len(point["text"]) <= 500:
                            lines.append(f"- [{point['aspect']}/{point['evidence_type']}] {point['text']}\n  - 条件：{'；'.join(point['conditions'])}\n  - 证据入口：`{record['id']}/{point['point_id']}`。")
                    lines.append(f"- 按需展开：`memory.read id={record['id']}`。\n")
                self.owned_write(path, ("\n".join(lines) + "\n").encode("utf-8"))
        index = {"schema_version": 1, "objects": [{"id": r["id"], "kind": r["kind"], "title": r["title"], "topics": r["topics"], "keywords": r["keywords"], "record": self.relative(self.record_path(r["id"]))} for r in records], "topics": topics}
        write(self.path(f"{self.workspace.name}/.runtime/memory/index.json"), json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8"))
        for _, folder, _, _ in KINDS.values():
            readme = self.workspace / folder / "知识提炼/README.md"
            self.owned_write(readme, (f"# {folder}提炼导航\n\n<!-- ljh-memory-owned -->\n\n" + "\n".join(f"- {r['id']} · {r['title']} · 主题：{'、'.join(r['topics'])}" for r in records if KINDS[r["kind"]][1] == folder) + "\n").encode("utf-8"))
        papers = [r for r in records if r["kind"] == "paper"]
        source_index = self.workspace / "1论文/源文件库/README.md"
        self.owned_write(source_index, ("# 论文源文件索引\n\n<!-- ljh-memory-owned -->\n\n" + "\n\n".join(f"- `{Path(r['sources'][0]['path']).name}`\n  - 题名：{r['title']}\n  - 身份：{r['id']}\n  - 原始外部路径/URL：`{r['sources'][0]['origin']}`" for r in papers) + "\n").encode("utf-8"))
        for record in records:
            if record.get("derived_state") == "needs_rebuild":
                record["derived_state"] = "current"
                self.save(record)
        return {"objects": len(records), "topics": topics, "index_is_derived": True}

    def topic_path(self, topic, kind):
        require(kind in {*KINDS, "all"}, "invalid_memory_kind", "Unknown topic kind")
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", topic).strip(" .")
        require(name and name == topic and len(name) <= 80 and name.upper() not in {"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"}, "invalid_topic", "Use a safe, unambiguous topic filename")
        relative = f"0知识库/方法与问题/{name}.md" if kind == "all" else f"{KINDS[kind][1]}/知识提炼/领域专题/{name}.md"
        return self.path(self.workspace.name + "/" + relative)

    def read(self, p):
        budget = p.get("budget_chars", 7000)
        if p.get("topic"):
            path = self.topic_path(p["topic"], p.get("kind", "all"))
            require(path.is_file(), "not_found", "Topic has no registered knowledge yet")
            # A topic may grow: oversized requests return routing instead of a cut claim.
            text = path.read_text(encoding="utf-8")
            result = {"level": "topic", "topic": p["topic"], "path": self.relative(path), "content": text, "truncated": False}
            stale = [r["id"] for r in self.records() if p["topic"] in self.facets(r) and (p.get("kind", "all") == "all" or p["kind"] == r["kind"]) and self.freshness(r)["state"] == "stale"]
            if stale:
                result.pop("content")
                result.update(stale_ids=stale, freshness="stale", message="Evidence changed; read current object evidence and refresh extraction before using this topic")
            if len(json.dumps(result, ensure_ascii=False)) + 150 > budget:
                result.pop("content", None)
                result.update(truncated=True, message="Topic exceeds budget; search for specific mechanisms or read an object", object_ids=[r["id"] for r in self.records() if p["topic"] in r["topics"]][:15])
            return bounded(result, budget)
        record = self.get(p["id"])
        fresh = self.freshness(record)
        if p.get("view", "summary") == "summary":
            points = [c for c in record["claims"] if not p.get("point_id") or c["point_id"] == p["point_id"]]
            require(not p.get("point_id") or points, "not_found", "Knowledge point not found")
            result = {"level": "object", "id": record["id"], "kind": record["kind"], "title": record["title"], "topics": record["topics"],
                      "freshness": fresh, "extraction": record["extraction"]["mode"], "coverage": "partial", "points": [],
                      "sources": [{k:s[k] for k in ("id", "role", "format")} for s in record["sources"]],
                      "writeback": "After new semantic reading, call memory.extract with claims and exact source citations"}
            for point in points:
                trial = {**result, "points": result["points"] + [point]}
                if len(json.dumps(trial, ensure_ascii=False)) + 150 <= budget:
                    result["points"].append(point)
            result["omitted_points"] = len(points) - len(result["points"])
            return bounded(result, budget)
        source_id = p.get("source_id")
        require(source_id, "source_required", "Select source_id from the object summary")
        source, text = self._text_source(record, source_id)
        lines = text.splitlines()
        if not p.get("section") and not p.get("start_line"):
            headings = outline(text)
            return bounded({"level": "outline", "id": record["id"], "source_id": source_id, "source_sha256": source["sha256"],
                            "line_count": len(lines), "sections": headings[:30], "omitted_sections": max(0, len(headings)-30)}, budget)
        if p.get("section"):
            headings = outline(text)
            heading = next((h for h in headings if h["section"] == p["section"]), None)
            require(heading is not None, "not_found", "Select an exact section from the outline")
            start = heading["line"]
            end = next((h["line"]-1 for h in headings if h["line"] > start), len(lines))
        else:
            start, end = p["start_line"], p.get("end_line", p["start_line"] + 30)
        require(type(start) is int and type(end) is int and 1 <= start <= end <= len(lines), "invalid_range", "Select existing source lines")
        return bounded({"level": "evidence", "id": record["id"], "source_id": source_id, "path": source["path"], "source_sha256": source["sha256"],
                        "start_line": start, "end_line": end, "content": "\n".join(lines[start-1:end]), "freshness": fresh,
                        "writeback_required": record["extraction"]["mode"] != "agent_semantic" or fresh["state"] == "stale"}, budget)

    def search(self, p):
        query = p.get("query", "")
        require(isinstance(query, str) and 0 < len(query.strip()) <= 500, "invalid_query", "Supply a focused keyword question")
        budget = p.get("budget_chars", 5000)
        require(type(p.get("limit", 8)) is int and 1 <= p.get("limit", 8) <= 30, "invalid_limit", "limit must be 1..30")
        require(type(budget) is int and 600 <= budget <= 50000, "invalid_budget", "budget_chars must be 600..50000")
        terms = query_terms(query)
        ranked = []
        purpose = p.get("purpose", "overview")
        require(purpose in {"overview", "innovation", "experiment_design", "result_analysis", "debug", "reproduction"}, "invalid_purpose", "Use a declared research reading purpose")
        preferred = {"experiment_design": {"experiment", "research_point"}, "result_analysis": {"experiment", "reproduction", "experience"}, "debug": {"experience", "experiment"}, "reproduction": {"reproduction", "paper"}}
        all_records = list(self.records())
        for record in all_records:
            if p.get("kind") and record["kind"] != p["kind"]:
                continue
            if p.get("topic") and p["topic"] not in record["topics"]:
                continue
            header = " ".join([record["id"], record["title"], *record["topics"], *record["keywords"]])
            matched = sorted(record["claims"], key=lambda c: -sum(len(t) for t in terms if contains(" ".join([c["text"], *c["keywords"]]), t)))
            best = matched[0] if matched else None
            score = sum(3 * len(t) for t in terms if contains(header, t)) + (sum(len(t) for t in terms if contains(best["text"] + " " + " ".join(best["keywords"]), t)) if best else 0)
            if score:
                score += 10 if record["kind"] in preferred.get(purpose, set()) else 0
                fresh = self.freshness(record)
                hit = {"id": record["id"], "kind": record["kind"], "title": record["title"], "topics": record["topics"], "freshness": fresh["state"],
                       "read_more": {"method": "memory.read", "id": record["id"]}}
                if best:
                    hit["point"] = {k:best[k] for k in ("point_id", "text", "aspect", "conditions", "evidence_type")}
                ranked.append((score, hit))
        ranked.sort(key=lambda x: (-x[0], x[1]["id"]))
        result = {"coverage": "registered_objects_only", "registered_objects": len(all_records), "matched_objects": len(ranked), "hits": [],
                  "warning": "No hit is not proof of no prior research. Stale/partial summaries require evidence drill-down; ranking is lexical relevance, not scientific quality."}
        for _, hit in ranked[:p.get("limit", 8)]:
            if len(json.dumps({**result, "hits": result["hits"] + [hit]}, ensure_ascii=False)) + 150 > budget:
                hit = {k:v for k,v in hit.items() if k != "point"}
                hit["summary_omitted"] = True
            if len(json.dumps({**result, "hits": result["hits"] + [hit]}, ensure_ascii=False)) + 150 <= budget:
                result["hits"].append(hit)
        result["omitted_hits"] = len(ranked) - len(result["hits"])
        topic_candidates = {t for r in all_records if r["id"] in {h["id"] for h in result["hits"]} for t in self.facets(r)}
        result["topic_entrypoints"] = sorted(topic_candidates, key=lambda t: (-sum(len(term) for term in terms if contains(t, term)), t))[:5]
        # Drop optional topic routing before exceeding the caller's hard budget.
        if len(json.dumps(result, ensure_ascii=False)) + 150 > budget:
            result.pop("topic_entrypoints")
        return bounded(result, budget)
