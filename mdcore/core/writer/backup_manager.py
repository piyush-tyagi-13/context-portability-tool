from __future__ import annotations
import shutil
from datetime import datetime, timezone
from pathlib import Path

from mdcore.config.models import BackupConfig
from mdcore.config.loader import expand_path
from mdcore.utils.logging import get_logger

log = get_logger("writer.backup")


class BackupManager:
    def __init__(self, cfg: BackupConfig) -> None:
        self._cfg = cfg
        self._backup_dir = expand_path(cfg.backup_path)

    def backup(self, path: Path) -> Path | None:
        if not self._cfg.enabled or not path.exists():
            return None
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        backup_name = f"{path.name}.{timestamp}.bak"
        dest = self._backup_dir / backup_name
        shutil.copy2(path, dest)
        log.info("Backup created: %s", dest)
        self._rotate(path.name)
        return dest

    def _rotate(self, filename: str) -> None:
        existing = sorted(
            self._backup_dir.glob(f"{filename}.*.bak"),
            key=lambda p: p.stat().st_mtime,
        )
        while len(existing) > self._cfg.max_backups_per_file:
            oldest = existing.pop(0)
            oldest.unlink()
            log.debug("Removed old backup: %s", oldest)
