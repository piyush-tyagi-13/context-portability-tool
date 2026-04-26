from __future__ import annotations
import logging
import logging.handlers
from pathlib import Path

from ctxkit.config.models import LoggingConfig
from ctxkit.config.loader import expand_path

_configured = False


def setup_logging(cfg: LoggingConfig) -> None:
    global _configured
    if _configured:
        return
    _configured = True

    if not cfg.enabled:
        logging.disable(logging.CRITICAL)
        return

    log_dir = expand_path(cfg.log_path)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "ctxkit.log"

    level = getattr(logging, cfg.log_level, logging.INFO)
    handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=cfg.max_log_size_mb * 1024 * 1024,
        backupCount=cfg.max_log_files,
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    root = logging.getLogger("ctxkit")
    root.setLevel(level)
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"ctxkit.{name}")
