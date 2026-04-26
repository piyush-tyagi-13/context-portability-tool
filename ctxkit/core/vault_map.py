"""VaultMap — manages <vault>/.ctxkit-meta.yaml.

Stores user-provided folder descriptions used by FolderRouter and the
classification LLM to make accurate placement decisions.

The meta file lives inside the vault so it travels with it (e.g. Google Drive
sync) and works on any machine. It is always excluded from indexing.
"""
from __future__ import annotations
from pathlib import Path

import yaml

from ctxkit.utils.logging import get_logger

log = get_logger("vault_map")

META_FILENAME = ".ctxkit-meta.yaml"


class VaultMap:
    def __init__(self, vault_path: Path) -> None:
        self._vault_path = vault_path
        self._meta_file = vault_path / META_FILENAME
        self._data: dict = self._load()

    # ── persistence ──────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if self._meta_file.exists():
            try:
                return yaml.safe_load(self._meta_file.read_text(encoding="utf-8")) or {}
            except Exception:
                log.warning("Failed to parse %s — starting fresh", self._meta_file)
        return {"folders": {}}

    def save(self) -> None:
        self._meta_file.write_text(
            yaml.dump(self._data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        log.debug("VaultMap saved: %s", self._meta_file)

    # ── folder descriptions ───────────────────────────────────────────────────

    def folder_descriptions(self) -> dict[str, str]:
        """Return {folder_relative_path: description} for all described folders."""
        return dict(self._data.get("folders", {}))

    def set_description(self, folder: str, description: str) -> None:
        self._data.setdefault("folders", {})[folder] = description

    def remove_description(self, folder: str) -> None:
        self._data.get("folders", {}).pop(folder, None)

    # ── discovery helpers ─────────────────────────────────────────────────────

    def all_vault_folders(self) -> list[str]:
        """Return all subdirectory paths relative to vault root, sorted."""
        folders = []
        for p in sorted(self._vault_path.rglob("*")):
            if p.is_dir() and p != self._vault_path:
                rel = str(p.relative_to(self._vault_path))
                # Skip hidden dirs and ctxkit-output
                if not any(part.startswith(".") for part in rel.split("/")) and rel != "ctxkit-output":
                    folders.append(rel)
        return folders

    def undescribed_folders(self) -> list[str]:
        """Return folders that exist in vault but have no description yet."""
        described = set(self._data.get("folders", {}).keys())
        return [f for f in self.all_vault_folders() if f not in described]

    def stale_descriptions(self) -> list[str]:
        """Return described folders that no longer exist in vault."""
        existing = set(self.all_vault_folders())
        return [f for f in self._data.get("folders", {}) if f not in existing]

    # ── template generation ───────────────────────────────────────────────────

    def write_template(self) -> Path:
        """Write (or refresh) .ctxkit-meta.yaml with all current folders.

        Existing descriptions are preserved. New folders are added with empty
        values. Stale folders (no longer in vault) are removed.
        Returns the path to the written file.
        """
        existing_descs = self._data.get("folders", {})
        all_folders = self.all_vault_folders()

        # Build ordered folder block preserving existing descriptions
        folders: dict[str, str] = {}
        for f in all_folders:
            folders[f] = existing_descs.get(f, "")

        header = (
            "# ctxkit vault map\n"
            "# Add a short description after each folder path to help ctxkit\n"
            "# route ingested documents to the right location.\n"
            "# Leave blank for folders where the name is self-explanatory.\n"
            "# Run: ctxkit index   once done.\n"
            "#\n"
            "# Example:\n"
            "#   Career: Job applications, CV, interview prep, OSS contributions\n"
            "#   Project High Road: Career advancement strategy, 70-80 LPA targeting\n"
            "#   Tanmay: Tanmay's personal notes — never route incoming docs here\n\n"
            "folders:\n"
        )

        lines = [header]
        for folder, desc in folders.items():
            # Quote folder names that contain special YAML chars
            safe_key = f'"{folder}"' if any(c in folder for c in ":{}[]|>&*!") else folder
            lines.append(f"  {safe_key}: {desc}\n")

        self._meta_file.write_text("".join(lines), encoding="utf-8")
        # Reload so in-memory state matches file
        self._data = self._load()
        log.info("VaultMap template written: %s", self._meta_file)
        return self._meta_file
