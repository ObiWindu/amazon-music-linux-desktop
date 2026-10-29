"""Download handling policy."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote


class DownloadDecision:
    ALLOW = "allow"
    DENY = "deny"
    CONFIRM = "confirm"


def safe_filename(name: str) -> str:
    name = unquote(name or "").strip()
    name = name.replace("\\", "/")
    name = name.split("/")[-1]
    # remove control chars and traversal
    name = name.replace("..", "")
    if not name or name in {".", ".."}:
        name = "download"
    # limit length
    if len(name) > 200:
        name = name[:200]
    return name


def validate_destination(dest_dir: Path, filename: str) -> Path | None:
    try:
        dest_dir = dest_dir.resolve()
        target = (dest_dir / safe_filename(filename)).resolve()
        if dest_dir not in target.parents and target != dest_dir:
            return None
        # ensure within dest_dir
        try:
            target.relative_to(dest_dir)
        except ValueError:
            return None
        return target
    except Exception:
        return None


def default_download_dir() -> Path:
    base = Path(os.environ.get("XDG_DOWNLOAD_DIR", str(Path.home() / "Downloads")))
    base.mkdir(parents=True, exist_ok=True)
    return base
