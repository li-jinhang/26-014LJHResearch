import argparse
import json
import sys
from .public import dispatch


def main(bound_project=None):
    parser = argparse.ArgumentParser(description="LJH Research version 1 JSON operations")
    parser.add_argument("method", nargs="?", help="Operation name; omit to read a full request from stdin")
    parser.add_argument("--project-root", default=bound_project or ".")
    parser.add_argument("--params", default="{}", help="JSON object, or @path-to-UTF8-file")
    parser.add_argument("--human", action="store_true", help="Assert a direct user decision; never use from a reasoning/controller plugin")
    parser.add_argument("--evidence", default="", help="Quote or identify the user's specific confirmation")
    args = parser.parse_args()
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        if args.method:
            from pathlib import Path
            raw = Path(args.params[1:]).read_text(encoding="utf-8") if args.params.startswith("@") else args.params
            request = {"protocol_version": 1, "project_root": args.project_root, "method": args.method, "params": json.loads(raw)}
        else:
            request = json.load(sys.stdin)
        if bound_project is not None:
            from pathlib import Path
            if not isinstance(request, dict) or Path(request.get("project_root", bound_project)).expanduser().resolve() != Path(bound_project).resolve():
                result = {"protocol_version": 1, "ok": False, "error": {"code": "project_binding", "message": "This deployed skill only operates on its installation project", "details": {}}}
            else:
                request["project_root"] = str(Path(bound_project).resolve())
                result = dispatch(request, human=args.human, evidence=args.evidence)
        else:
            result = dispatch(request, human=args.human, evidence=args.evidence)
    except (ValueError, OSError, TypeError) as exc:
        result = {"protocol_version": 1, "ok": False, "error": {"code": "invalid_json", "message": str(exc)}}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
