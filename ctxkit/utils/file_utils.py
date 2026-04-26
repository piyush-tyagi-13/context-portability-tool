from __future__ import annotations
import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically via a temp file rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".ctxkit_tmp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise


def word_count(text: str) -> int:
    return len(text.split())


def vault_relative_path(file_path: Path, vault_path: Path) -> str:
    try:
        return str(file_path.relative_to(vault_path))
    except ValueError:
        return str(file_path)


def folder_path_from_relative(rel: str) -> str:
    parts = rel.replace("\\", "/").split("/")
    return "/".join(parts[:-1]) if len(parts) > 1 else ""
