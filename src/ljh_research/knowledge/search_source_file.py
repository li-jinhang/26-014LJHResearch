#!/usr/bin/env python3
"""Search topic-level ljh research source-file indexes."""

from __future__ import annotations

import argparse
from pathlib import Path

from ljh_research.knowledge.cli_output import configure_utf8
from ljh_research.knowledge.source_index import search_source_library, exact_matches
from ljh_research.workspace_contract import resolve_project_root
from ljh_research.knowledge.layout import PAPERS_DIR, research_root


def main() -> int:
    configure_utf8()
    parser = argparse.ArgumentParser(description="Search ljh research source-file indexes.")
    parser.add_argument("--project-root", help="Project root path. Defaults to the current directory.")
    parser.add_argument("--query", required=True, help="Paper title, DOI, filename, path, or URL.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum matches to print.")
    args = parser.parse_args()

    project_root = resolve_project_root(args.project_root)
    papers_dir = research_root(project_root) / PAPERS_DIR
    matches = search_source_library(papers_dir, [args.query])
    exact = exact_matches(matches)
    candidates = [match for match in matches if match.match_type == "candidate"]
    print(f"project_root={project_root}")
    print(f"papers_dir={papers_dir}")
    print(f"found={'true' if exact else 'false'}")
    print(f"match_count={len(exact)}")
    print(f"candidate_count={len(candidates)}")
    for match in exact[: args.limit]:
        print(f"match_readme={match.readme}")
        print(match.entry)
        print("---")
    for match in candidates[: args.limit]:
        print(f"candidate_readme={match.readme}")
        print(match.entry)
        print("---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
