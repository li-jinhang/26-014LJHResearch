from pathlib import Path
import sys
from _entry import run
if __name__ == "__main__":
    sys.argv.insert(1, str(Path(__file__).resolve().parents[4]))
    run("ljh_research.project_cli")
