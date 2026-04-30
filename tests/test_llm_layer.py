"""Unit tests for mdcore LLM layer - mock-based, no real API calls."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mdcore.config.models import LLMConfig
from mdcore.llm.llm_layer import (
    LLMLayer,
    ClassificationResult,
    FolderRoutingResult,
    _build_llm,
    _extract_token_usage,
    _parse_classification,
    _parse_folder_routing,
    _strip_hallucinated_citations,
)


# ---------------------------------------------------------------------------
# _extract_token_usage
# ---------------------------------------------------------------------------

class TestExtractTokenUsage:

    def test_gemini_format(self):
        meta = {"usage_metadata": {"prompt_token_count": 10, "candidates_token_count": 20}}
        assert _extract_token_usage(meta) == (10, 20)

    def test_gemini_input_output_aliases(self):
        # usage_metadata with input_tokens / output_tokens (some gemini versions)
        meta = {"usage_metadata": {"input_tokens": 5, "output_tokens": 15}}
        assert _extract_token_usage(meta) == (5, 15)

    def test_openai_format(self):
        meta = {"token_usage": {"prompt_tokens": 8, "completion_tokens": 32}}
        assert _extract_token_usage(meta) == (8, 32)

    def test_anthropic_format(self):
        meta = {"usage": {"input_tokens": 12, "output_tokens": 44}}
        assert _extract_token_usage(meta) == (12, 44)

    def test_ollama_format(self):
        meta = {"prompt_eval_count": 7, "eval_count": 55}
        assert _extract_token_usage(meta) == (7, 55)

    def test_llm_keypool_format(self):
        # llm-keypool only reports combined tokens_used
        meta = {"tokens_used": 99}
        assert _extract_token_usage(meta) == (0, 99)

    def test_empty_metadata(self):
        assert _extract_token_usage({}) == (0, 0)

    def test_none_metadata(self):
        assert _extract_token_usage(None) == (0, 0)

    def test_zeros_not_confused_with_missing(self):
        # explicit zeros should return zeros, not fall through
        meta = {"token_usage": {"prompt_tokens": 0, "completion_tokens": 0}}
        assert _extract_token_usage(meta) == (0, 0)


# ---------------------------------------------------------------------------
# _strip_hallucinated_citations
# ---------------------------------------------------------------------------

class TestStripHallucinatedCitations:

    def test_removes_out_of_range_citation(self):
        raw_context = "[1] source one\n[2] source two"
        briefing = "Some fact [1]. Another fact [3]. More [2]."
        result = _strip_hallucinated_citations(briefing, raw_context)
        assert "[3]" not in result
        assert "[1]" in result
        assert "[2]" in result

    def test_preserves_valid_citations(self):
        raw_context = "[1] a\n[2] b\n[3] c"
        briefing = "Fact A [1]. Fact B [2]. Fact C [3]."
        result = _strip_hallucinated_citations(briefing, raw_context)
        assert result == briefing

    def test_no_sources_returns_unchanged(self):
        briefing = "Fact [1] and [5]."
        result = _strip_hallucinated_citations(briefing, "")
        assert result == briefing

    def test_all_citations_hallucinated(self):
        raw_context = "[1] only source"
        briefing = "Fact [2]. More [3]. Even more [99]."
        result = _strip_hallucinated_citations(briefing, raw_context)
        assert "[2]" not in result
        assert "[99]" not in result


# ---------------------------------------------------------------------------
# _parse_classification
# ---------------------------------------------------------------------------

class TestParseClassification:

    def test_update_action(self):
        raw = "ACTION: update\nTARGET: Career/playbook.md\nCONFIDENCE: 0.9\nREASONING: Direct continuation."
        result = _parse_classification(raw)
        assert result.action == "update"
        assert result.target_file == "Career/playbook.md"
        assert result.confidence == pytest.approx(0.9)
        assert "continuation" in result.reasoning

    def test_new_action(self):
        raw = "ACTION: new\nTARGET: none\nCONFIDENCE: 0.75\nREASONING: Standalone document."
        result = _parse_classification(raw)
        assert result.action == "new"
        assert result.target_file is None

    def test_invalid_action_defaults_to_new(self):
        raw = "ACTION: maybe\nTARGET: none\nCONFIDENCE: 0.5\nREASONING: Uncertain."
        result = _parse_classification(raw)
        assert result.action == "new"

    def test_invalid_confidence_defaults(self):
        raw = "ACTION: new\nTARGET: none\nCONFIDENCE: not-a-number\nREASONING: Test."
        result = _parse_classification(raw)
        assert result.confidence == pytest.approx(0.7)

    def test_missing_fields_return_defaults(self):
        raw = ""
        result = _parse_classification(raw)
        assert result.action == "new"
        assert result.target_file is None
        assert result.confidence == pytest.approx(0.7)

    def test_target_empty_string_treated_as_none(self):
        raw = "ACTION: new\nTARGET: \nCONFIDENCE: 0.8\nREASONING: Test."
        result = _parse_classification(raw)
        assert result.target_file is None


# ---------------------------------------------------------------------------
# _parse_folder_routing
# ---------------------------------------------------------------------------

class TestParseFolderRouting:

    FOLDERS = ["Career", "Finance", "Learning/Books", "Projects/Alpha"]

    def test_exact_match(self):
        raw = "FOLDER: Career\nCONFIDENCE: 0.95\nREASONING: Career doc."
        result = _parse_folder_routing(raw, self.FOLDERS)
        assert result.folder == "Career"
        assert result.confidence == pytest.approx(0.95)

    def test_case_insensitive_fallback(self):
        raw = "FOLDER: career\nCONFIDENCE: 0.8\nREASONING: Case mismatch."
        result = _parse_folder_routing(raw, self.FOLDERS)
        assert result.folder == "Career"

    def test_invented_folder_falls_back_to_first(self):
        raw = "FOLDER: InventedFolder\nCONFIDENCE: 0.5\nREASONING: Unknown."
        result = _parse_folder_routing(raw, self.FOLDERS)
        assert result.folder == self.FOLDERS[0]

    def test_subfolder_path_matched(self):
        raw = "FOLDER: Learning/Books\nCONFIDENCE: 0.88\nREASONING: Book notes."
        result = _parse_folder_routing(raw, self.FOLDERS)
        assert result.folder == "Learning/Books"

    def test_invalid_confidence_defaults(self):
        raw = "FOLDER: Finance\nCONFIDENCE: bad\nREASONING: Test."
        result = _parse_folder_routing(raw, self.FOLDERS)
        assert result.confidence == pytest.approx(0.7)

    def test_empty_folders_list(self):
        raw = "FOLDER: Career\nCONFIDENCE: 0.9\nREASONING: Test."
        result = _parse_folder_routing(raw, [])
        assert result.folder == ""


# ---------------------------------------------------------------------------
# _build_llm dispatch
# ---------------------------------------------------------------------------

class TestBuildLlm:

    def _cfg(self, **kwargs) -> LLMConfig:
        return LLMConfig(backend="ollama", model="test", **kwargs)

    @patch("mdcore.core.deps.assert_backend_available")
    def test_ollama_backend(self, mock_assert):
        import sys
        mock_ollama_mod = MagicMock()
        mock_chat_class = MagicMock(return_value=MagicMock())
        mock_ollama_mod.ChatOllama = mock_chat_class
        with patch.dict(sys.modules, {"langchain_ollama": mock_ollama_mod}):
            cfg = self._cfg()
            result = _build_llm("ollama", "qwen3:4b", None, cfg)
            mock_chat_class.assert_called_once()
            kw = mock_chat_class.call_args.kwargs
            assert kw["model"] == "qwen3:4b"

    @patch("mdcore.core.deps.assert_backend_available")
    def test_openai_backend(self, mock_assert):
        import sys
        mock_mod = MagicMock()
        mock_class = MagicMock(return_value=MagicMock())
        mock_mod.ChatOpenAI = mock_class
        with patch.dict(sys.modules, {"langchain_openai": mock_mod}):
            cfg = self._cfg()
            result = _build_llm("openai", "gpt-4o", "sk-test", cfg)
            mock_class.assert_called_once()
            kw = mock_class.call_args.kwargs
            assert kw["model"] == "gpt-4o"
            assert kw["api_key"] == "sk-test"

    @patch("mdcore.core.deps.assert_backend_available")
    def test_anthropic_backend(self, mock_assert):
        import sys
        mock_mod = MagicMock()
        mock_class = MagicMock(return_value=MagicMock())
        mock_mod.ChatAnthropic = mock_class
        with patch.dict(sys.modules, {"langchain_anthropic": mock_mod}):
            cfg = self._cfg()
            result = _build_llm("anthropic", "claude-3-5-sonnet-20241022", "sk-ant-test", cfg)
            mock_class.assert_called_once()
            kw = mock_class.call_args.kwargs
            assert kw["model"] == "claude-3-5-sonnet-20241022"

    @patch("mdcore.core.deps.assert_backend_available")
    def test_gemini_backend(self, mock_assert):
        import sys
        mock_mod = MagicMock()
        mock_class = MagicMock(return_value=MagicMock())
        mock_mod.ChatGoogleGenerativeAI = mock_class
        with patch.dict(sys.modules, {"langchain_google_genai": mock_mod}):
            cfg = self._cfg()
            result = _build_llm("gemini", "gemini-2.0-flash", "goog-key", cfg)
            mock_class.assert_called_once()
            kw = mock_class.call_args.kwargs
            assert kw["model"] == "gemini-2.0-flash"
            assert kw["google_api_key"] == "goog-key"

    @patch("mdcore.core.deps.assert_backend_available")
    def test_unknown_backend_raises(self, mock_assert):
        cfg = self._cfg()
        with pytest.raises(ValueError, match="Unknown LLM backend"):
            _build_llm("banana", "model", None, cfg)


# ---------------------------------------------------------------------------
# LLMLayer._invoke fallback
# ---------------------------------------------------------------------------

class TestLLMLayerFallback:

    def _make_response(self, content="ok"):
        r = MagicMock()
        r.content = content
        r.response_metadata = {}
        return r

    @patch("mdcore.llm.llm_layer._build_llm")
    def test_uses_primary_when_successful(self, mock_build):
        primary = MagicMock()
        primary.invoke.return_value = self._make_response("primary response")
        mock_build.return_value = primary

        cfg = LLMConfig(backend="ollama", model="qwen3:4b")
        layer = LLMLayer(cfg)
        result = layer._invoke("test prompt")

        assert result == "primary response"
        primary.invoke.assert_called_once_with("test prompt")

    @patch("mdcore.llm.llm_layer._build_llm")
    def test_falls_back_on_primary_error(self, mock_build):
        primary = MagicMock()
        primary.invoke.side_effect = RuntimeError("primary failed")
        fallback = MagicMock()
        fallback.invoke.return_value = self._make_response("fallback response")

        mock_build.side_effect = [primary, fallback]

        cfg = LLMConfig(
            backend="ollama", model="qwen3:4b",
            fallback_backend="openai", fallback_model="gpt-4o-mini",
        )
        layer = LLMLayer(cfg)
        result = layer._invoke("test prompt")

        assert result == "fallback response"
        fallback.invoke.assert_called_once()

    @patch("mdcore.llm.llm_layer._build_llm")
    def test_raises_when_no_fallback_configured(self, mock_build):
        primary = MagicMock()
        primary.invoke.side_effect = RuntimeError("down")
        mock_build.return_value = primary

        cfg = LLMConfig(backend="ollama", model="qwen3:4b")
        layer = LLMLayer(cfg)
        with pytest.raises(RuntimeError, match="no fallback configured"):
            layer._invoke("test prompt")

    @patch("mdcore.llm.llm_layer._build_llm")
    def test_empty_response_raises(self, mock_build):
        primary = MagicMock()
        primary.invoke.return_value = self._make_response("")
        mock_build.return_value = primary

        cfg = LLMConfig(backend="ollama", model="qwen3:4b")
        layer = LLMLayer(cfg)
        with pytest.raises(RuntimeError, match="empty response"):
            layer._invoke("test prompt")


# ---------------------------------------------------------------------------
# LLMLayer.classify
# ---------------------------------------------------------------------------

class TestLLMLayerClassify:

    @patch("mdcore.llm.llm_layer._build_llm")
    def test_classify_returns_result(self, mock_build):
        from langchain_core.documents import Document

        llm = MagicMock()
        resp = MagicMock()
        resp.content = "ACTION: new\nTARGET: none\nCONFIDENCE: 0.8\nREASONING: New topic."
        resp.response_metadata = {}
        llm.invoke.return_value = resp
        mock_build.return_value = llm

        cfg = LLMConfig(backend="ollama", model="qwen3:4b")
        layer = LLMLayer(cfg)
        docs = [Document(page_content="existing content", metadata={"source_file": "foo.md"})]
        result = layer.classify("incoming doc text " * 20, docs)

        assert isinstance(result, ClassificationResult)
        assert result.action == "new"

    @patch("mdcore.llm.llm_layer._build_llm")
    def test_classify_update_action(self, mock_build):
        from langchain_core.documents import Document

        llm = MagicMock()
        resp = MagicMock()
        resp.content = "ACTION: update\nTARGET: Career/notes.md\nCONFIDENCE: 0.92\nREASONING: Continuation."
        resp.response_metadata = {}
        llm.invoke.return_value = resp
        mock_build.return_value = llm

        cfg = LLMConfig(backend="ollama", model="qwen3:4b")
        layer = LLMLayer(cfg)
        docs = [Document(page_content="career notes", metadata={"source_file": "Career/notes.md"})]
        result = layer.classify("career update text " * 20, docs)

        assert result.action == "update"
        assert result.target_file == "Career/notes.md"


# ---------------------------------------------------------------------------
# LLMLayer.route_folder
# ---------------------------------------------------------------------------

class TestLLMLayerRouteFolder:

    @patch("mdcore.llm.llm_layer._build_llm")
    def test_route_returns_valid_folder(self, mock_build):
        llm = MagicMock()
        resp = MagicMock()
        resp.content = "FOLDER: Finance\nCONFIDENCE: 0.87\nREASONING: Financial document."
        resp.response_metadata = {}
        llm.invoke.return_value = resp
        mock_build.return_value = llm

        cfg = LLMConfig(backend="ollama", model="qwen3:4b")
        layer = LLMLayer(cfg)
        folders = ["Career", "Finance", "Learning"]
        result = layer.route_folder("budget spreadsheet doc", folders)

        assert isinstance(result, FolderRoutingResult)
        assert result.folder == "Finance"
        assert result.confidence == pytest.approx(0.87)

    @patch("mdcore.llm.llm_layer._build_llm")
    def test_route_includes_descriptions_in_prompt(self, mock_build):
        llm = MagicMock()
        resp = MagicMock()
        resp.content = "FOLDER: Career\nCONFIDENCE: 0.9\nREASONING: Job content."
        resp.response_metadata = {}
        llm.invoke.return_value = resp
        mock_build.return_value = llm

        cfg = LLMConfig(backend="ollama", model="qwen3:4b")
        layer = LLMLayer(cfg)
        descs = {"Career": "Job applications and career planning"}
        layer.route_folder("job offer letter", ["Career"], descriptions=descs)

        prompt_used = llm.invoke.call_args.args[0]
        assert "Job applications and career planning" in prompt_used


# ---------------------------------------------------------------------------
# LLMLayer.synthesise
# ---------------------------------------------------------------------------

class TestLLMLayerSynthesise:

    @patch("mdcore.llm.llm_layer._build_llm")
    def test_synthesise_returns_string(self, mock_build):
        llm = MagicMock()
        resp = MagicMock()
        resp.content = "Briefing text here [1]."
        resp.response_metadata = {}
        llm.invoke.return_value = resp
        mock_build.return_value = llm

        cfg = LLMConfig(backend="openai", model="gpt-4o", api_key="sk-test")
        layer = LLMLayer(cfg)
        result = layer.synthesise("query", "[1] source content here")

        assert "Briefing text" in result

    @patch("mdcore.llm.llm_layer._build_llm")
    def test_synthesise_strips_hallucinated_citations(self, mock_build):
        llm = MagicMock()
        resp = MagicMock()
        resp.content = "Fact [1]. Hallucinated [5]."
        resp.response_metadata = {}
        llm.invoke.return_value = resp
        mock_build.return_value = llm

        cfg = LLMConfig(backend="openai", model="gpt-4o", api_key="sk-test")
        layer = LLMLayer(cfg)
        result = layer.synthesise("query", "[1] one source")

        assert "[1]" in result
        assert "[5]" not in result
