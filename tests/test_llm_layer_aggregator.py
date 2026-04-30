"""Tests for LLMLayer with aggregator (llm-keypool) backend."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Point llm-keypool at a temp DB so tests never touch real keys
_tmp = tempfile.mkdtemp()
os.environ["LLM_KEYPOOL_DB"] = str(Path(_tmp) / "test_mdcore.db")

from mdcore.config.models import LLMConfig
from mdcore.llm.llm_layer import LLMLayer, _build_llm, _extract_token_usage


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _llm_cfg(**kwargs) -> LLMConfig:
    return LLMConfig(backend="aggregator", model="", **kwargs)


def _mock_response(content="ok", tokens_used=50):
    r = MagicMock()
    r.content = content
    r.response_metadata = {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "tokens_used": tokens_used,
        "requests_today": 3,
        "tokens_used_today": 200,
        "remaining_requests": 97,
        "key_id": 1,
    }
    return r


# ---------------------------------------------------------------------------
# _build_llm("aggregator")
# ---------------------------------------------------------------------------

class TestBuildLlmAggregator:

    @patch("mdcore.core.deps.assert_backend_available")
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    def test_returns_aggregator_chat_instance(self, mock_rotator, mock_assert):
        from llm_keypool import AggregatorChat
        mock_rotator.return_value = MagicMock()
        cfg = _llm_cfg(aggregator_category="general_purpose", aggregator_rotate_every=5)
        result = _build_llm("aggregator", "", None, cfg)
        assert isinstance(result, AggregatorChat)

    @patch("mdcore.core.deps.assert_backend_available")
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    def test_passes_category_and_rotate_every(self, mock_rotator, mock_assert):
        from llm_keypool import AggregatorChat
        mock_rotator.return_value = MagicMock()
        cfg = _llm_cfg(aggregator_category="general_purpose", aggregator_rotate_every=3)
        result = _build_llm("aggregator", "", None, cfg)
        assert isinstance(result, AggregatorChat)
        assert result.category == "general_purpose"
        assert result.rotate_every == 3

    @patch("mdcore.core.deps.assert_backend_available")
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    def test_defaults_when_category_not_set(self, mock_rotator, mock_assert):
        from llm_keypool import AggregatorChat
        mock_rotator.return_value = MagicMock()
        # aggregator_category=None -> AggregatorChat defaults to "general_purpose"
        cfg = _llm_cfg()
        result = _build_llm("aggregator", "", None, cfg)
        assert isinstance(result, AggregatorChat)


# ---------------------------------------------------------------------------
# token usage extraction from llm-keypool metadata
# ---------------------------------------------------------------------------

class TestAggregatorTokenExtraction:

    def test_tokens_used_field(self):
        meta = {
            "tokens_used": 123,
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
        }
        inp, out = _extract_token_usage(meta)
        assert inp == 0
        assert out == 123

    def test_zero_tokens_still_extracts(self):
        meta = {"tokens_used": 0}
        inp, out = _extract_token_usage(meta)
        assert inp == 0
        assert out == 0

    def test_aggregator_fields_do_not_confuse_other_parsers(self):
        # aggregator metadata should NOT be mis-parsed as openai token_usage
        meta = {
            "tokens_used": 77,
            "requests_today": 5,
            "tokens_used_today": 400,
        }
        inp, out = _extract_token_usage(meta)
        assert out == 77


# ---------------------------------------------------------------------------
# LLMLayer with aggregator backend - full invoke path
# ---------------------------------------------------------------------------

class TestLLMLayerAggregator:

    @patch("llm_keypool.providers.dispatch.complete", new_callable=AsyncMock)
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    @patch("mdcore.core.deps.assert_backend_available")
    def test_invoke_returns_content(self, mock_assert, mock_rotator, mock_complete):
        from types import SimpleNamespace
        mock_rotator.return_value = MagicMock()
        mock_complete.return_value = (
            SimpleNamespace(text="synthesis result", tokens_used=80, error=None, remaining_requests=50),
            {"provider": "groq", "model": "llama-3.3-70b", "key_id": 1,
             "requests_today": 2, "tokens_used_today": 160},
        )

        cfg = _llm_cfg(aggregator_category="general_purpose")
        layer = LLMLayer(cfg)
        result = layer._invoke("Hello!")
        assert result == "synthesis result"

    @patch("llm_keypool.providers.dispatch.complete", new_callable=AsyncMock)
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    @patch("mdcore.core.deps.assert_backend_available")
    def test_invoke_raises_on_keypool_error(self, mock_assert, mock_rotator, mock_complete):
        from types import SimpleNamespace
        mock_rotator.return_value = MagicMock()
        mock_complete.return_value = (
            SimpleNamespace(text=None, tokens_used=0, error="all keys exhausted", remaining_requests=None),
            {"provider": "groq", "model": "", "key_id": 1,
             "requests_today": 0, "tokens_used_today": 0},
        )

        cfg = _llm_cfg(aggregator_category="general_purpose")
        layer = LLMLayer(cfg)
        with pytest.raises(RuntimeError):
            layer._invoke("Hello!")


# ---------------------------------------------------------------------------
# Fallback: aggregator -> ollama
# ---------------------------------------------------------------------------

class TestAggregatorFallback:

    @patch("llm_keypool.providers.dispatch.complete", new_callable=AsyncMock)
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    @patch("mdcore.core.deps.assert_backend_available")
    def test_falls_back_to_ollama_on_aggregator_error(
        self, mock_assert, mock_rotator, mock_complete
    ):
        from types import SimpleNamespace

        mock_rotator.return_value = MagicMock()
        mock_complete.return_value = (
            SimpleNamespace(text=None, tokens_used=0, error="quota exceeded", remaining_requests=None),
            {"provider": "groq", "model": "", "key_id": 1,
             "requests_today": 0, "tokens_used_today": 0},
        )

        fallback_llm = MagicMock()
        fb_resp = MagicMock()
        fb_resp.content = "fallback answer"
        fb_resp.response_metadata = {"prompt_eval_count": 5, "eval_count": 20}
        fallback_llm.invoke.return_value = fb_resp

        cfg = _llm_cfg(
            aggregator_category="general_purpose",
            fallback_backend="ollama",
            fallback_model="qwen3:4b",
        )
        layer = LLMLayer(cfg)
        # Inject fallback directly to avoid building a real ChatOllama
        layer._fallback = fallback_llm

        result = layer._invoke("some prompt")
        assert result == "fallback answer"
        fallback_llm.invoke.assert_called_once()


# ---------------------------------------------------------------------------
# synthesise_backend = "aggregator"
# ---------------------------------------------------------------------------

class TestSynthesiseWithAggregatorBackend:

    @patch("llm_keypool.providers.dispatch.complete", new_callable=AsyncMock)
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    @patch("mdcore.core.deps.assert_backend_available")
    def test_synthesise_via_aggregator_backend(
        self, mock_assert, mock_rotator, mock_complete
    ):
        from types import SimpleNamespace

        mock_rotator.return_value = MagicMock()
        mock_complete.return_value = (
            SimpleNamespace(text="Synthesised briefing [1].", tokens_used=60,
                            error=None, remaining_requests=44),
            {"provider": "mistral", "model": "mistral-large-latest", "key_id": 2,
             "requests_today": 1, "tokens_used_today": 60},
        )

        cfg = LLMConfig(
            backend="ollama",
            model="qwen3:4b",
            synthesise_backend="aggregator",
            aggregator_category="general_purpose",
        )
        # Stub the primary ollama LLM so it doesn't attempt a connection
        primary_llm = MagicMock()
        primary_llm.invoke.return_value = MagicMock(content="classified", response_metadata={})

        layer = LLMLayer(cfg)
        layer._llm = primary_llm

        result = layer.synthesise("test query", "[1] source text here")
        assert "Synthesised briefing" in result
        assert "[1]" in result

    @patch("llm_keypool.providers.dispatch.complete", new_callable=AsyncMock)
    @patch("llm_keypool.langchain_wrapper._build_rotator")
    @patch("mdcore.core.deps.assert_backend_available")
    def test_synthesise_aggregator_strips_hallucinated_citations(
        self, mock_assert, mock_rotator, mock_complete
    ):
        from types import SimpleNamespace

        mock_rotator.return_value = MagicMock()
        mock_complete.return_value = (
            SimpleNamespace(text="Fact [1]. Hallucinated [9].", tokens_used=30,
                            error=None, remaining_requests=50),
            {"provider": "groq", "model": "llama-3.3-70b", "key_id": 1,
             "requests_today": 1, "tokens_used_today": 30},
        )

        cfg = LLMConfig(
            backend="ollama",
            model="qwen3:4b",
            synthesise_backend="aggregator",
            aggregator_category="general_purpose",
        )
        primary_llm = MagicMock()
        layer = LLMLayer(cfg)
        layer._llm = primary_llm

        result = layer.synthesise("query", "[1] only one source")
        assert "[9]" not in result
        assert "[1]" in result


# ---------------------------------------------------------------------------
# current_key() and pool_status() available on aggregator backend
# ---------------------------------------------------------------------------

class TestAggregatorKeyInspection:

    @patch("mdcore.core.deps.assert_backend_available")
    def test_current_key_returns_none_when_no_keys(self, mock_assert):
        """Real rotator + empty temp DB -> current_key() returns None."""
        from llm_keypool import AggregatorChat

        cfg = _llm_cfg(aggregator_category="general_purpose")
        layer = LLMLayer(cfg)
        chat = layer._get_llm()
        assert isinstance(chat, AggregatorChat)
        # Temp DB has no keys registered
        assert chat.current_key() is None

    @patch("mdcore.core.deps.assert_backend_available")
    def test_pool_status_empty_when_no_keys(self, mock_assert):
        """Real KeyStore + empty temp DB -> pool_status() returns empty list."""
        from llm_keypool import AggregatorChat

        cfg = _llm_cfg(aggregator_category="general_purpose")
        layer = LLMLayer(cfg)
        chat = layer._get_llm()
        assert isinstance(chat, AggregatorChat)
        status = chat.pool_status()
        assert isinstance(status, list)
        assert len(status) == 0
