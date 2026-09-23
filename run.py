"""Convenient source-tree launcher; standard virtualenvs also work."""
from pathlib import Path
import sys

local_dependencies = Path(__file__).resolve().parent / ".deps"
if local_dependencies.is_dir():
    sys.path.insert(0, str(local_dependencies))

from moneygraph.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
