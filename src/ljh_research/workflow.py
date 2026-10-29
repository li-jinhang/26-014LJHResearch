"""Packaged scientific guidance and Markdown decision records, shared by drivers."""
import hashlib
from importlib.resources import files
import json
import re

from .errors import require


REVISION = 1
TOPICS = ("manual", "auto", "task-control", "conclusion-discipline", "paper-management",
          "research-points", "experiments", "reproduction", "framework-evolution", "align", "review", "foam-rag", "layered-memory")
RECORD = re.compile(r"```ljh-research-cycle\n(.*?)\n```", re.DOTALL)


def version(config):
    return "auto" if config.get("update_mode") == "automatic" else "manual"


def guide(selected, topic=None):
    require(selected in {"manual", "auto"}, "invalid_version", "Choose manual or auto")
    topic = topic or selected
    require(topic in TOPICS, "unknown_topic", "Unknown workflow topic", {"topics": TOPICS})
    content = files("ljh_research").joinpath("resources", "research", topic + ".md").read_text(encoding="utf-8")
    return {"research_version": selected, "skill_name": "ljh-research",
            "workflow_revision": REVISION, "topic": topic, "topics": list(TOPICS), "content": content,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}


def records(text):
    result = []
    for match in RECORD.finditer(text):
        try:
            record = json.loads(match[1])
        except ValueError:
            continue
        if isinstance(record, dict) and record.get("kind") in {"plan", "analysis"}:
            result.append(record)
    return result


def validate_record(p):
    kind = p.get("kind")
    require(kind in {"plan", "analysis"}, "invalid_research_record", "kind must be plan or analysis")
    common = ("record_key", "kind", "evidence")
    fields = (("question", "hypotheses", "next_action", "expected_information", "decision_rule", "stop_rule", "run_keys")
              if kind == "plan" else ("plan_id", "run_ids", "observations", "credibility", "interpretation", "limitations", "decision", "next_action"))
    record = {k: p[k] for k in (*common, *fields) if k in p}
    require(set(record) == set((*common, *fields)), "invalid_research_record", "Missing scientific decision fields", {"required": list((*common, *fields))})
    for key in ("evidence", "hypotheses", "run_keys", "run_ids"):
        if key in record:
            require(isinstance(record[key], list) and all(isinstance(x, str) and x.strip() for x in record[key]),
                    "invalid_research_record", key + " must be an array of nonempty strings")
    for key, value in record.items():
        if not isinstance(value, list):
            require(isinstance(value, str) and (value.strip() or key == "next_action" and record.get("decision") == "stop"),
                    "invalid_research_record", key + " must be nonempty text")
    if kind == "plan":
        require(len(record["hypotheses"]) >= 2, "invalid_research_record", "Compare the hypothesis with at least one alternative/null explanation and their predictions")
        require(len(set(record["run_keys"])) == len(record["run_keys"]), "invalid_research_record", "run_keys must be unique")
    else:
        require(record["credibility"] in {"valid", "invalid", "partial"}, "invalid_research_record", "Classify result credibility")
        require(record["decision"] in {"continue", "pivot", "stop"}, "invalid_research_record", "Choose continue, pivot or stop")
    require(len(json.dumps(record, ensure_ascii=False)) <= 16000, "invalid_research_record", "Record exceeds 16000 characters; link large artifacts instead")
    require("```" not in json.dumps(record, ensure_ascii=False), "invalid_research_record", "Link code artifacts instead of embedding Markdown fences")
    return record
