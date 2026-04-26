from __future__ import annotations
import re
from pathlib import Path

from mdcore.config.models import WriterConfig, VaultConfig
from mdcore.utils.file_utils import atomic_write
from mdcore.utils.logging import get_logger

log = get_logger("writer.file")


class FileWriter:
    def __init__(self, vault_cfg: VaultConfig, cfg: WriterConfig) -> None:
        self._vault_path = Path(vault_cfg.path).expanduser()
        self._cfg = cfg

    def update(self, path: Path, existing_content: str, new_content: str) -> None:
        if self._cfg.append_position == "after_last_heading":
            body = _insert_after_last_heading(existing_content, new_content)
        else:
            separator = "\n\n---\n\n" if not existing_content.endswith("\n\n") else ""
            body = existing_content + separator + new_content
        atomic_write(path, body)
        log.info("Updated file: %s", path)

    def create(self, folder: str, filename: str, content: str) -> Path:
        target_dir = (self._vault_path / folder) if folder else self._vault_path
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / _sanitize_filename(filename)
        atomic_write(path, content)
        log.info("Created file: %s", path)
        return path


def _insert_after_last_heading(content: str, new_content: str) -> str:
    matches = list(re.finditer(r"^#{1,6}\s.+$", content, re.MULTILINE))
    if not matches:
        return content + "\n\n" + new_content
    last_heading_end = matches[-1].end()
    return content[:last_heading_end] + "\n\n" + new_content + content[last_heading_end:]


def _sanitize_filename(name: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*]', "-", name)
    if not safe.endswith(".md"):
        safe += ".md"
    return safe
