from __future__ import annotations
import re
from pathlib import Path

from ctxkit.config.models import IngesterConfig
from ctxkit.utils.file_utils import word_count


class SummaryReceiver:
    def __init__(self, cfg: IngesterConfig) -> None:
        self._cfg = cfg

    def receive_from_file(self, path: str) -> str:
        p = Path(path).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"Summary file not found: {p}")
        return self._validate(p.read_text(encoding="utf-8", errors="ignore"))

    def receive_from_text(self, text: str) -> str:
        return self._validate(text)

    def _validate(self, text: str) -> str:
        wc = word_count(text)
        if wc < self._cfg.min_summary_word_count:
            raise ValueError(
                f"Summary too short ({wc} words). Minimum is {self._cfg.min_summary_word_count}."
            )
        heading_count = len(re.findall(r"^#{1,6}\s", text, re.MULTILINE))
        if heading_count < self._cfg.min_summary_headings:
            raise ValueError(
                f"Summary has no headings. At least {self._cfg.min_summary_headings} heading required."
            )
        return text.strip()
