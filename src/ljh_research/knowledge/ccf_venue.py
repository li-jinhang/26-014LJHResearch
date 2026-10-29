#!/usr/bin/env python3
"""Look up CCF ratings from the CCF 2022 recommended list (A conferences) plus
a locally maintained extension for common journals and B/C conferences."""

from __future__ import annotations

import argparse
import re

from ljh_research.knowledge.cli_output import configure_utf8

CCF_LIST_YEAR = "2022"

# CCF-A conferences (CCF 2022 recommended list) relevant to AI, multimedia,
# data mining, information retrieval, and databases. Key = canonical
# abbreviation used in file names; aliases are matched case-insensitively.
CCF_A_CONFERENCES: dict[str, dict[str, object]] = {
    "AAAI": {
        "full_name": "AAAI Conference on Artificial Intelligence",
        "rating": "A",
        "aliases": ("AAAI",),
    },
    "NeurIPS": {
        "full_name": "Annual Conference on Neural Information Processing Systems",
        "rating": "A",
        "aliases": ("NeurIPS", "NIPS", "Conference on Neural Information Processing Systems"),
    },
    "ICML": {
        "full_name": "International Conference on Machine Learning",
        "rating": "A",
        "aliases": ("ICML",),
    },
    "IJCAI": {
        "full_name": "International Joint Conference on Artificial Intelligence",
        "rating": "A",
        "aliases": ("IJCAI",),
    },
    "ACL": {
        "full_name": "Annual Meeting of the Association for Computational Linguistics",
        "rating": "A",
        "aliases": ("ACL",),
    },
    "CVPR": {
        "full_name": "IEEE/CVF Conference on Computer Vision and Pattern Recognition",
        "rating": "A",
        "aliases": ("CVPR",),
    },
    "ICCV": {
        "full_name": "IEEE/CVF International Conference on Computer Vision",
        "rating": "A",
        "aliases": ("ICCV",),
    },
    "KDD": {
        "full_name": "ACM SIGKDD Conference on Knowledge Discovery and Data Mining",
        "rating": "A",
        "aliases": ("KDD", "SIGKDD", "Knowledge Discovery and Data Mining"),
    },
    "SIGIR": {
        "full_name": "International ACM SIGIR Conference on Research and Development in Information Retrieval",
        "rating": "A",
        "aliases": ("SIGIR",),
    },
    "WWW": {
        "full_name": "The Web Conference",
        "rating": "A",
        "aliases": (
            "WWW",
            "ACM WWW",
            "The Web Conference",
            "International World Wide Web Conference",
            "World Wide Web Conference",
        ),
    },
    "SIGMOD": {
        "full_name": "ACM SIGMOD International Conference on Management of Data",
        "rating": "A",
        "aliases": ("SIGMOD",),
    },
    "ICDE": {
        "full_name": "IEEE International Conference on Data Engineering",
        "rating": "A",
        "aliases": ("ICDE",),
    },
    "VLDB": {
        "full_name": "International Conference on Very Large Data Bases",
        "rating": "A",
        "aliases": ("VLDB",),
    },
    "ACMMM": {
        "full_name": "ACM International Conference on Multimedia",
        "rating": "A",
        "aliases": ("ACM MM", "ACMMM", "ACM Multimedia", "Multimedia Conference", "MM"),
    },
    "SIGGRAPH": {
        "full_name": "ACM SIGGRAPH Conference on Computer Graphics and Interactive Techniques",
        "rating": "A",
        "aliases": ("SIGGRAPH",),
    },
    "VIS": {
        "full_name": "IEEE Visualization Conference",
        "rating": "A",
        "aliases": ("IEEE VIS", "VIS", "IEEE Visualization"),
    },
    "CHI": {
        "full_name": "ACM CHI Conference on Human Factors in Computing Systems",
        "rating": "A",
        "aliases": ("CHI", "ACM CHI", "Conference on Human Factors in Computing Systems"),
    },
}

# Locally maintained extension: journals and B/C-class conferences commonly
# used in recommendation / multimedia research. Ratings follow the public
# CCF 2022 recommended list; confirm externally before asserting in a report.
CCF_JOURNALS: dict[str, dict[str, object]] = {
    "TOIS": {
        "full_name": "ACM Transactions on Information Systems",
        "rating": "A",
        "aliases": ("TOIS", "ACM TOIS", "Transactions on Information Systems"),
    },
    "TKDE": {
        "full_name": "IEEE Transactions on Knowledge and Data Engineering",
        "rating": "A",
        "aliases": ("TKDE", "IEEE TKDE"),
    },
    "TMM": {
        "full_name": "IEEE Transactions on Multimedia",
        "rating": "B",
        "aliases": ("TMM", "IEEE TMM", "IEEE Transactions on Multimedia"),
    },
    "TOMM": {
        "full_name": "ACM Transactions on Multimedia Computing, Communications, and Applications",
        "rating": "B",
        "aliases": ("TOMM", "ACM TOMM"),
    },
    "TIST": {
        "full_name": "ACM Transactions on Intelligent Systems and Technology",
        "rating": "B",
        "aliases": ("TIST", "ACM TIST"),
    },
}

CCF_BC_CONFERENCES: dict[str, dict[str, object]] = {
    "CIKM": {
        "full_name": "ACM International Conference on Information and Knowledge Management",
        "rating": "B",
        "aliases": ("CIKM",),
    },
    "ECIR": {
        "full_name": "European Conference on Information Retrieval",
        "rating": "B",
        "aliases": ("ECIR",),
    },
    "RecSys": {
        "full_name": "ACM Conference on Recommender Systems",
        "rating": "B",
        "aliases": ("RecSys", "ACM RecSys", "Recommender Systems Conference"),
    },
    "ICMR": {
        "full_name": "ACM International Conference on Multimedia Retrieval",
        "rating": "B",
        "aliases": ("ICMR", "ACM ICMR"),
    },
    "ICDM": {
        "full_name": "IEEE International Conference on Data Mining",
        "rating": "B",
        "aliases": ("ICDM",),
    },
    "SDM": {
        "full_name": "SIAM International Conference on Data Mining",
        "rating": "B",
        "aliases": ("SDM",),
    },
    "WSDM": {
        "full_name": "ACM International Conference on Web Search and Data Mining",
        "rating": "B",
        "aliases": ("WSDM",),
    },
    "DASFAA": {
        "full_name": "International Conference on Database Systems for Advanced Applications",
        "rating": "C",
        "aliases": ("DASFAA",),
    },
    "WISE": {
        "full_name": "International Conference on Web Information Systems Engineering",
        "rating": "C",
        "aliases": ("WISE",),
    },
}

# Well-known venues that are NOT in the CCF recommended list.
NOT_IN_CCF = ("ICLR", "International Conference on Learning Representations")


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def lookup(query: str) -> tuple[str | None, dict[str, object] | None, str | None]:
    normalized = normalize(query)
    for category, table in (("conference", CCF_A_CONFERENCES), ("journal", CCF_JOURNALS), ("conference", CCF_BC_CONFERENCES)):
        for abbr, info in table.items():
            candidates = [abbr, str(info["full_name"]), *(str(alias) for alias in info["aliases"])]
            if any(normalize(candidate) == normalized for candidate in candidates):
                return abbr, info, category
    return None, None, None


def main() -> int:
    configure_utf8()
    parser = argparse.ArgumentParser(
        description="Look up CCF ratings (A-class conferences from the official 2022 list; "
                    "journals and B/C conferences from the local extension)."
    )
    parser.add_argument("--venue", help="Conference/journal name or abbreviation (case-insensitive).")
    parser.add_argument("--list", action="store_true", help="List all built-in venues.")
    args = parser.parse_args()

    if args.list:
        for category, table in (("conference", CCF_A_CONFERENCES), ("journal", CCF_JOURNALS), ("conference", CCF_BC_CONFERENCES)):
            for abbr, info in table.items():
                print(f"{abbr}|{info['full_name']}|{info['rating']}|{category}|{CCF_LIST_YEAR}")
        return 0

    if not args.venue:
        parser.error("provide --venue or --list")

    query = args.venue.strip()
    abbr, info, category = lookup(query)
    if abbr and info:
        print("found=true")
        print(f"rating={info['rating']}")
        print(f"category={category}")
        print(f"ccf_list={CCF_LIST_YEAR}")
        print(f"venue={abbr}")
        print(f"full_name={info['full_name']}")
        print(f"source={'official-2022' if category == 'conference' and abbr in CCF_A_CONFERENCES else 'local-extension'}")
        return 0

    if normalize(query) in {normalize(venue) for venue in NOT_IN_CCF}:
        print("found=false")
        print("rating=not_in_ccf")
        print("not_in_ccf=true")
        print(f"venue={query}")
        return 0

    print("found=false")
    print("rating=unknown")
    print(f"venue={query}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
