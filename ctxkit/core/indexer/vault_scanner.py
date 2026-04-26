from __future__ import annotations
from pathlib import Path

from markdown_it import MarkdownIt

from ctxkit.config.models import VaultConfig, IndexerConfig
from ctxkit.utils.logging import get_logger

log = get_logger("indexer.scanner")
_md = MarkdownIt()


def _has_structure_signals(text: str, min_signals: int) -> bool:
    tokens = _md.parse(text)
    count = sum(1 for t in tokens if t.type in ("heading_open", "paragraph_open", "bullet_list_open"))
    return count >= min_signals


class VaultScanner:
    def __init__(self, vault_cfg: VaultConfig, indexer_cfg: IndexerConfig) -> None:
        self._vault_path = Path(vault_cfg.path).expanduser()
        # Normalise to lowercase for case-insensitive matching.
        # ctxkit-output is always excluded — it is ctxkit's own output folder
        # inside the vault and must never be indexed regardless of user config.
        self._excluded_folders = {f.lower() for f in vault_cfg.excluded_folders} | {"ctxkit-output"}
        self._excluded_extensions = {e.lower() for e in vault_cfg.excluded_extensions}
        self._min_word_count = indexer_cfg.min_word_count
        self._min_signals = indexer_cfg.min_structure_signals

    def scan(self) -> list[Path]:
        eligible: list[Path] = []
        for path in self._vault_path.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() != ".md":
                continue
            if path.suffix.lower() in self._excluded_extensions:
                continue
            if any(part.lower() in self._excluded_folders for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            words = len(text.split())
            if words < self._min_word_count:
                log.debug("Skipped (low word count %d): %s", words, path)
                continue
            if not _has_structure_signals(text, self._min_signals):
                log.debug("Skipped (low structure signals): %s", path)
                continue
            eligible.append(path)
        log.info("VaultScanner: %d eligible files in %s", len(eligible), self._vault_path)
        return eligible
