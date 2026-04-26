from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from ctxkit.config.models import CtxKitConfig

DEFAULT_CONFIG_PATH = Path("~/.ctxkit/config.yaml").expanduser()


def load_config(config_path: Optional[str] = None) -> CtxKitConfig:
    path = Path(config_path).expanduser() if config_path else DEFAULT_CONFIG_PATH

    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found at {path}.\n"
            "Run: ctxkit init  to create one interactively."
        )

    with open(path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        raw = {}

    try:
        return CtxKitConfig.model_validate(raw)
    except ValidationError as exc:
        lines = [f"Config validation failed ({path}):"]
        for err in exc.errors():
            loc = " → ".join(str(s) for s in err["loc"])
            lines.append(f"  [{loc}] {err['msg']}")
        raise SystemExit("\n".join(lines)) from exc


def expand_path(p: str) -> Path:
    return Path(os.path.expandvars(p)).expanduser()
