from __future__ import annotations

import re
from pathlib import Path


def safe_filename(value: str, fallback: str = "documento") -> str:
    value = Path(value or fallback).name
    value = re.sub(r"[^A-Za-z0-9._ -]+", "_", value).strip(" ._")
    return value[:180] or fallback
