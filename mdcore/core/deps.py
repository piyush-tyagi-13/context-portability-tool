"""
mdcore dependency manager.

All backend libraries are optional. This module maps config backend names to
the pip packages they need, checks whether they are importable, and installs
them into the running Python environment on request.

Install target is always sys.executable — works correctly whether mdcore was
installed via pipx (isolated venv), regular pip, or editable dev install.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

from mdcore.utils.logging import get_logger

log = get_logger("deps")

# ── backend → pip packages ────────────────────────────────────────────────────
# Each entry: backend name → list of pip requirement strings.
# langchain-ollama is in core deps (always installed) so its entry is empty.

LLM_BACKEND_PACKAGES: dict[str, list[str]] = {
    "ollama":    [],                              # in core
    "openai":    ["langchain-openai>=0.2"],
    "anthropic": ["langchain-anthropic>=0.2"],
    "gemini":    ["langchain-google-genai>=2"],
    "huggingface": ["langchain-huggingface>=0.1", "sentence-transformers>=3"],
}

EMBEDDING_BACKEND_PACKAGES: dict[str, list[str]] = {
    "ollama":      [],                             # in core
    "openai":      ["langchain-openai>=0.2"],
    "huggingface": ["langchain-huggingface>=0.1", "sentence-transformers>=3"],
    "gemini":      ["langchain-google-genai>=2"],
}

# Import probe: one representative module per backend.
# If this import succeeds the backend is available.
LLM_BACKEND_PROBE: dict[str, str] = {
    "ollama":      "langchain_ollama",
    "openai":      "langchain_openai",
    "anthropic":   "langchain_anthropic",
    "gemini":      "langchain_google_genai",
    "huggingface": "langchain_huggingface",
}

EMBEDDING_BACKEND_PROBE: dict[str, str] = {
    "ollama":      "langchain_ollama",
    "openai":      "langchain_openai",
    "huggingface": "sentence_transformers",
    "gemini":      "langchain_google_genai",
}


# ── public helpers ────────────────────────────────────────────────────────────

@dataclass
class DepStatus:
    backend: str
    role: str          # "llm", "synthesise", "embeddings"
    packages: list[str]
    installed: bool
    probe_module: str


def check_backend(backend: str, role: str = "llm") -> DepStatus:
    """Return installation status for one backend."""
    if role == "embeddings":
        packages = EMBEDDING_BACKEND_PACKAGES.get(backend, [])
        probe = EMBEDDING_BACKEND_PROBE.get(backend, "")
    else:
        packages = LLM_BACKEND_PACKAGES.get(backend, [])
        probe = LLM_BACKEND_PROBE.get(backend, "")

    installed = _is_importable(probe) if probe else True
    return DepStatus(
        backend=backend, role=role, packages=packages,
        installed=installed, probe_module=probe,
    )


def required_backends(cfg) -> list[DepStatus]:
    """
    Given a MdCoreConfig, return DepStatus for every backend the config
    references — deduplicated. Checks llm.backend, llm.synthesise_backend,
    llm.fallback_backend, and embeddings.backend.
    """
    checks: list[DepStatus] = []
    seen: set[tuple[str, str]] = set()

    def _add(backend: str, role: str) -> None:
        if not backend or (backend, role) in seen:
            return
        seen.add((backend, role))
        checks.append(check_backend(backend, role))

    _add(cfg.llm.backend, "llm")
    _add(getattr(cfg.llm, "synthesise_backend", None) or "", "synthesise")
    _add(cfg.llm.fallback_backend or "", "llm-fallback")
    _add(cfg.embeddings.backend, "embeddings")
    return checks


def install_packages(packages: list[str], quiet: bool = False) -> bool:
    """
    Install pip packages into the current Python environment.
    Returns True on success.
    """
    if not packages:
        return True
    cmd = [sys.executable, "-m", "pip", "install"] + packages
    if quiet:
        cmd.append("--quiet")
    log.info("Installing: %s", " ".join(packages))
    result = subprocess.run(cmd)
    return result.returncode == 0


def install_for_backend(backend: str, role: str = "llm", quiet: bool = False) -> bool:
    status = check_backend(backend, role)
    if status.installed:
        return True
    return install_packages(status.packages, quiet=quiet)


def assert_backend_available(backend: str, role: str = "llm") -> None:
    """
    Raise ImportError with an actionable message if backend deps are missing.
    Called at the point of use in LLMLayer / EmbeddingEngine.
    """
    status = check_backend(backend, role)
    if not status.installed:
        pkgs = " ".join(status.packages)
        raise ImportError(
            f"Backend '{backend}' ({role}) requires packages that are not installed.\n"
            f"Fix:  mdcore deps install\n"
            f"  or: pip install {pkgs}"
        )


# ── internal ──────────────────────────────────────────────────────────────────

def _is_importable(module: str) -> bool:
    if not module:
        return True
    try:
        __import__(module)
        return True
    except ImportError:
        return False
