import argparse
import json
import sys
from . import workspace
from .doctor import inspect


def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Prepare, initialize, validate or repair LJH Research")
    parser.add_argument("operation", choices=["doctor", "plan", "create", "validate", "repair", "config", "version", "deploy", "migrate"])
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--approve", action="store_true", help="User approved the displayed concrete changes")
    parser.add_argument("--key")
    parser.add_argument("--value", help="JSON value for a project convention")
    parser.add_argument("--select", choices=["manual", "auto"], help="Select a research skill version (version operation)")
    parser.add_argument("--version", choices=["manual", "auto"], help="Research skill version for create (default manual)")
    parser.add_argument("--from", dest="source", choices=[".ljh-research", "ljh research"], help="Explicit old document-directory name for migrate")
    args = parser.parse_args()
    if args.operation == "doctor":
        print(json.dumps(inspect(), ensure_ascii=False, indent=2))
        return 0
    from ..public import dispatch
    params = {}
    if args.operation == "config":
        method = "config.update"
        params = {"key": args.key, "value": json.loads(args.value)}
    else:
        method = "setup." + args.operation
    if args.select:
        if args.operation != "version":
            parser.error("--select belongs to the version operation")
        params["version"] = args.select
    if args.version:
        if args.operation not in {"create", "plan", "deploy"}:
            parser.error("--version belongs to create, plan or deploy")
        params["version"] = args.version
    if args.source:
        if args.operation != "migrate":
            parser.error("--from belongs to migrate")
        params["source"] = args.source
    result = dispatch({"protocol_version": 1, "method": method, "project_root": args.project_root, "params": params},
                      human=args.approve, evidence="User approved the displayed setup plan" if args.approve else "")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
