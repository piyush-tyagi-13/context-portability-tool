from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path

from ctxkit.config.models import ManifestConfig, VaultConfig
from ctxkit.config.loader import expand_path
from ctxkit.utils.logging import get_logger

log = get_logger("indexer.manifest")


@dataclass
class IndexDiff:
    new_files: list[Path] = field(default_factory=list)
    modified_files: list[Path] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)

    @property
    def total_changes(self) -> int:
        return len(self.new_files) + len(self.modified_files) + len(self.deleted_files)


class ManifestManager:
    def __init__(self, manifest_cfg: ManifestConfig, vault_cfg: VaultConfig) -> None:
        self._path = expand_path(manifest_cfg.path)
        self._vault_path = Path(vault_cfg.path).expanduser()
        self._drift_threshold = manifest_cfg.drift_warning_threshold
        self._data: dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path) as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)

    def diff(self, eligible_files: list[Path]) -> IndexDiff:
        eligible_keys = {self._key(p): p for p in eligible_files}
        diff = IndexDiff()

        for key, path in eligible_keys.items():
            mtime = path.stat().st_mtime
            if key not in self._data:
                diff.new_files.append(path)
            elif self._data[key] < mtime:
                diff.modified_files.append(path)

        for key in list(self._data.keys()):
            if key not in eligible_keys:
                diff.deleted_files.append(key)

        log.info(
            "Manifest diff: +%d modified=%d deleted=%d",
            len(diff.new_files), len(diff.modified_files), len(diff.deleted_files),
        )
        return diff

    def update(self, path: Path) -> None:
        key = self._key(path)
        self._data[key] = path.stat().st_mtime
        self._save()

    def remove(self, source_key: str) -> None:
        self._data.pop(source_key, None)
        self._save()

    def drift_count(self, eligible_files: list[Path]) -> int:
        diff = self.diff(eligible_files)
        return diff.total_changes

    def _key(self, path: Path) -> str:
        try:
            return str(path.relative_to(self._vault_path))
        except ValueError:
            return str(path)
