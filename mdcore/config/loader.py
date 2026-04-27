from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from mdcore.config.models import MdCoreConfig

DEFAULT_CONFIG_PATH = Path("~/.mdcore/config.yaml").expanduser()
DEFAULT_MODELS_PATH = Path("~/.mdcore/models.yaml").expanduser()


def load_config(
    config_path: Optional[str] = None,
    models_path: Optional[str] = None,
) -> MdCoreConfig:
    path = Path(config_path).expanduser() if config_path else DEFAULT_CONFIG_PATH

    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found at {path}.\n"
            "Run: mdcore init  to create one interactively."
        )

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    # Merge models.yaml on top of llm + embeddings sections if it exists.
    # Explicit --models flag > default ~/.mdcore/models.yaml > inline config.yaml values.
    m_path = Path(models_path).expanduser() if models_path else DEFAULT_MODELS_PATH
    if m_path.exists():
        with open(m_path) as f:
            models_raw = yaml.safe_load(f) or {}
        if "llm" in models_raw:
            raw["llm"] = {**(raw.get("llm") or {}), **models_raw["llm"]}
        if "embeddings" in models_raw:
            raw["embeddings"] = {**(raw.get("embeddings") or {}), **models_raw["embeddings"]}

    try:
        return MdCoreConfig.model_validate(raw)
    except ValidationError as exc:
        lines = [f"Config validation failed ({path}):"]
        for err in exc.errors():
            loc = " -> ".join(str(s) for s in err["loc"])
            lines.append(f"  [{loc}] {err['msg']}")
        raise SystemExit("\n".join(lines)) from exc


def expand_path(p: str) -> Path:
    return Path(os.path.expandvars(p)).expanduser()
