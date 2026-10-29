from ljh_research.knowledge.import_paper import *
if __name__ == "__main__":
    import os
    os.environ["LJH_RESEARCH_LEGACY_LAYOUT"] = "1"
    raise SystemExit(main())
