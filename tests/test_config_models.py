"""Tests for mdcore config model validation and defaults."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from mdcore.config.models import (
    LLMConfig,
    EmbeddingsConfig,
    MdCoreConfig,
    VaultConfig,
)


class TestLLMConfigDefaults:

    def test_default_backend_is_ollama(self):
        cfg = LLMConfig()
        assert cfg.backend == "ollama"

    def test_default_model(self):
        cfg = LLMConfig()
        assert cfg.model == "qwen3.5:4b"

    def test_default_temperature(self):
        cfg = LLMConfig()
        assert cfg.temperature == pytest.approx(0.2)

    def test_default_aggregator_rotate_every(self):
        cfg = LLMConfig()
        assert cfg.aggregator_rotate_every == 5

    def test_aggregator_category_defaults_to_none(self):
        cfg = LLMConfig()
        assert cfg.aggregator_category is None

    def test_no_api_key_by_default(self):
        cfg = LLMConfig()
        assert cfg.api_key is None

    def test_no_fallback_by_default(self):
        cfg = LLMConfig()
        assert cfg.fallback_backend is None
        assert cfg.fallback_model is None


class TestLLMConfigAggregator:

    def test_aggregator_backend_accepted(self):
        cfg = LLMConfig(backend="aggregator")
        assert cfg.backend == "aggregator"

    def test_aggregator_category_set(self):
        cfg = LLMConfig(backend="aggregator", aggregator_category="general_purpose")
        assert cfg.aggregator_category == "general_purpose"

    def test_aggregator_rotate_every_custom(self):
        cfg = LLMConfig(backend="aggregator", aggregator_rotate_every=10)
        assert cfg.aggregator_rotate_every == 10

    def test_aggregator_no_api_key_needed(self):
        # api_key should remain None - keypool manages its own DB
        cfg = LLMConfig(backend="aggregator", aggregator_category="general_purpose")
        assert cfg.api_key is None

    def test_synthesise_backend_can_be_aggregator(self):
        cfg = LLMConfig(backend="ollama", model="qwen3:4b", synthesise_backend="aggregator")
        assert cfg.synthesise_backend == "aggregator"

    def test_fallback_can_be_aggregator(self):
        cfg = LLMConfig(backend="ollama", model="qwen3:4b", fallback_backend="aggregator")
        assert cfg.fallback_backend == "aggregator"


class TestLLMConfigBackendValidation:

    def test_all_valid_backends_accepted(self):
        backends = ["ollama", "openai", "anthropic", "gemini", "huggingface", "aggregator"]
        for b in backends:
            cfg = LLMConfig(backend=b)
            assert cfg.backend == b

    def test_invalid_backend_raises(self):
        with pytest.raises(ValidationError):
            LLMConfig(backend="banana")


class TestLLMConfigFallback:

    def test_fallback_backend_and_model(self):
        cfg = LLMConfig(
            backend="aggregator",
            fallback_backend="ollama",
            fallback_model="qwen3:4b",
        )
        assert cfg.fallback_backend == "ollama"
        assert cfg.fallback_model == "qwen3:4b"

    def test_fallback_api_key(self):
        cfg = LLMConfig(
            backend="ollama",
            model="qwen3:4b",
            fallback_backend="openai",
            fallback_model="gpt-4o-mini",
            fallback_api_key="sk-test",
        )
        assert cfg.fallback_api_key == "sk-test"


class TestEmbeddingsConfig:

    def test_default_backend_is_ollama(self):
        cfg = EmbeddingsConfig()
        assert cfg.backend == "ollama"

    def test_aggregator_not_valid_backend(self):
        # aggregator was removed as embeddings backend
        with pytest.raises(ValidationError):
            EmbeddingsConfig(backend="aggregator")

    def test_valid_backends(self):
        for b in ["ollama", "huggingface", "openai", "gemini"]:
            cfg = EmbeddingsConfig(backend=b)
            assert cfg.backend == b


class TestMdCoreConfigConstruction:

    def test_minimal_config_with_vault(self):
        cfg = MdCoreConfig(vault=VaultConfig(path="~/vault"))
        assert cfg.vault.path == "~/vault"
        assert cfg.llm.backend == "ollama"  # defaults

    def test_aggregator_llm_in_full_config(self):
        cfg = MdCoreConfig(
            vault=VaultConfig(path="~/vault"),
            llm=LLMConfig(
                backend="aggregator",
                aggregator_category="general_purpose",
                aggregator_rotate_every=5,
                fallback_backend="ollama",
                fallback_model="qwen3:4b",
            ),
        )
        assert cfg.llm.backend == "aggregator"
        assert cfg.llm.fallback_backend == "ollama"
