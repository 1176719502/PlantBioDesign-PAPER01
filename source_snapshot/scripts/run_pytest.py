from __future__ import annotations

import os
import sys


sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import pytest


if __name__ == "__main__":
    raise SystemExit(pytest.main(sys.argv[1:]))
