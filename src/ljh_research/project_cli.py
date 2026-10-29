"""Project-local launchers bind operations to their installation's project."""
import sys
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main(bound_project=sys.argv.pop(1)))
