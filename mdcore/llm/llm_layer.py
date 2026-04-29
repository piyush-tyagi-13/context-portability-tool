from __future__ import annotations
import os
import re
from dataclasses import dataclass
from typing import Optional

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel

from mdcore.config.models import LLMConfig
from mdcore.utils.logging import get_logger

log = get_logger("llm")


def _extract_token_usage(response_metadata: dict) -> tuple[int, int]:
    """Return (input_tokens, output_tokens) from a LangChain response_metadata dict.

    Each backend stores usage differently:
    - Gemini:    usage_metadata.prompt_token_count / candidates_token_count
    - OpenAI:    token_usage.prompt_tokens / completion_tokens
    - Anthropic: usage.input_tokens / output_tokens
    - Ollama:    prompt_eval_count / eval_count
    """
    m = response_metadata or {}

    # Gemini
    usage_meta = m.get("usage_metadata", {})
    if usage_meta:
        inp = usage_meta.get("prompt_token_count", 0) or usage_meta.get("input_tokens", 0)
        out = usage_meta.get("candidates_token_count", 0) or usage_meta.get("output_tokens", 0)
        if inp or out:
            return int(inp), int(out)

    # OpenAI
    token_usage = m.get("token_usage", {})
    if token_usage:
        return int(token_usage.get("prompt_tokens", 0)), int(token_usage.get("completion_tokens", 0))

    # Anthropic
    usage = m.get("usage", {})
    if usage:
        return int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))

    # Ollama
    if "prompt_eval_count" in m or "eval_count" in m:
        return int(m.get("prompt_eval_count", 0)), int(m.get("eval_count", 0))

    # llm-keypool (reports combined tokens_used only)
    if "tokens_used" in m:
        return 0, int(m.get("tokens_used", 0))

    return 0, 0


def _strip_hallucinated_citations(briefing: str, raw_context: str) -> str:
    """Remove citation numbers [N] that exceed the actual source count.

    phi4-mini occasionally emits [3], [4] … even when only 1–2 sources were
    provided. Count sources from the raw_context block headers ([1], [2] …)
    and strip any reference beyond that count.
    """
    source_count = len(re.findall(r"^\[\d+\]", raw_context, re.MULTILINE))
    if source_count == 0:
        return briefing

    def _replace(m: re.Match) -> str:
        n = int(m.group(1))
        return m.group(0) if n <= source_count else ""

    return re.sub(r"\[(\d+)\]", _replace, briefing)


@dataclass
class ClassificationResult:
    action: str          # "update" | "new"
    target_file: Optional[str]
    reasoning: str
    confidence: float


@dataclass
class FolderRoutingResult:
    folder: str
    confidence: float
    reasoning: str


def _build_llm(backend: str, model: str, api_key: Optional[str], cfg: LLMConfig) -> BaseChatModel:
    from mdcore.core.deps import assert_backend_available
    assert_backend_available(backend, "llm")
    match backend:
        case "ollama":
            from langchain_ollama import ChatOllama
            return ChatOllama(
                model=model,
                temperature=cfg.temperature,
                num_predict=cfg.max_tokens,
                think=cfg.think,
                request_timeout=cfg.timeout_seconds,
            )
        case "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model,
                api_key=api_key,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                timeout=cfg.timeout_seconds,
            )
        case "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=model,
                api_key=api_key,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                timeout=cfg.timeout_seconds,
            )
        case "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=model,
                google_api_key=api_key,
                temperature=cfg.temperature,
                max_output_tokens=cfg.max_tokens,
                request_timeout=cfg.timeout_seconds,
            )
        case "aggregator":
            from llm_keypool import AggregatorChat
            return AggregatorChat(
                category=cfg.aggregator_category,
                rotate_every=cfg.aggregator_rotate_every,
            )
        case _:
            raise ValueError(f"Unknown LLM backend: {backend}")


class LLMLayer:
    def __init__(self, cfg: LLMConfig) -> None:
        self._cfg = cfg
        self._llm: Optional[BaseChatModel] = None
        self._fallback: Optional[BaseChatModel] = None

        # LangSmith observability - set env vars before any LangChain call.
        if cfg.langsmith_api_key:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = cfg.langsmith_api_key
            os.environ["LANGCHAIN_PROJECT"] = cfg.langsmith_project or "mdcore"
            log.info("LangSmith tracing enabled (project: %s)", cfg.langsmith_project or "mdcore")

    def _get_llm(self) -> BaseChatModel:
        if self._llm is None:
            self._llm = _build_llm(self._cfg.backend, self._cfg.model, self._cfg.api_key, self._cfg)
        return self._llm

    def _get_fallback(self) -> Optional[BaseChatModel]:
        if self._cfg.fallback_backend and self._fallback is None:
            self._fallback = _build_llm(
                self._cfg.fallback_backend,
                self._cfg.fallback_model or "",
                self._cfg.fallback_api_key,
                self._cfg,
            )
        return self._fallback

    def _log_tokens(self, label: str, response) -> None:  # type: ignore[type-arg]
        meta = getattr(response, "response_metadata", {}) or {}
        inp, out = _extract_token_usage(meta)
        if inp or out:
            log.info("tokens [%s] in=%d out=%d total=%d", label, inp, out, inp + out)
        else:
            log.debug("tokens [%s] unavailable (backend did not report usage)", label)

    def _invoke(self, prompt: str) -> str:
        try:
            response = self._get_llm().invoke(prompt)
            content = response.content  # type: ignore[attr-defined]
            if not content:
                raise RuntimeError(
                    "LLM returned an empty response. "
                    "Ollama may be under load — try again, or check 'ollama ps'."
                )
            self._log_tokens(self._cfg.model, response)
            return content
        except Exception as primary_err:
            log.warning("Primary LLM failed: %s", primary_err)
            fallback = self._get_fallback()
            if fallback:
                log.info("Trying fallback LLM")
                response = fallback.invoke(prompt)
                self._log_tokens(self._cfg.fallback_model or "fallback", response)
                return response.content  # type: ignore[attr-defined]
            raise RuntimeError(
                f"LLM call failed and no fallback configured.\nError: {primary_err}"
            ) from primary_err

    def classify(self, summary: str, candidates: list[Document]) -> ClassificationResult:
        candidate_block = "\n\n".join(
            f"FILE: {d.metadata.get('source_file', '?')}\n{d.page_content[:400]}"
            for d in candidates
        )
        prompt = (
            "You are a knowledge base classifier. Given an incoming document and a list "
            "of candidate files, decide whether the document should UPDATE an existing file or "
            "create a NEW file.\n\n"
            "RULES — apply in order:\n"
            "1. If the incoming document is self-contained and structured (has its own headings, "
            "tables, or prioritised lists covering a distinct topic), prefer NEW over UPDATE.\n"
            "2. Only choose UPDATE if the incoming content is clearly a continuation, correction, "
            "or direct elaboration of an existing file — not merely topically related.\n"
            "3. Topical similarity alone is NOT sufficient reason to UPDATE. A document about "
            "'OSS contribution strategy' is related to a career playbook but is its own artefact.\n"
            "4. When in doubt between UPDATE and NEW, choose NEW.\n\n"
            "Respond in this exact format (no extra text):\n"
            "ACTION: update|new\n"
            "TARGET: <vault-relative path or 'none' for new>\n"
            "CONFIDENCE: <0.0–1.0>\n"
            "REASONING: <one sentence>\n\n"
            f"INCOMING DOCUMENT:\n{summary[:800]}\n\n"
            f"CANDIDATE FILES:\n{candidate_block}"
        )
        raw = self._invoke(prompt)
        return _parse_classification(raw)

    def route_folder(
        self,
        document: str,
        folders: list[str],
        descriptions: dict[str, str] | None = None,
    ) -> FolderRoutingResult:
        """Ask LLM to pick the best vault folder for a new document."""
        folder_lines = []
        for f in folders:
            desc = (descriptions or {}).get(f, "")
            folder_lines.append(f"  {f}" + (f" — {desc}" if desc else ""))
        folder_block = "\n".join(folder_lines)

        prompt = (
            "You are a file organiser for a personal knowledge base vault.\n"
            "Given an incoming document and a list of vault folders, choose the single "
            "most appropriate folder to save the document in.\n\n"
            "RULES:\n"
            "1. Pick the most specific matching folder (prefer a sub-folder over its parent).\n"
            "2. If no folder is a good fit, pick the closest reasonable one.\n"
            "3. Never invent a folder that is not in the list.\n"
            "4. For folders with no description, use the folder name itself as a strong semantic "
            "signal — e.g. 'Financials' means financial documents, 'Career' means job/work topics.\n\n"
            "Respond in this exact format (no extra text):\n"
            "FOLDER: <exact folder path from the list>\n"
            "CONFIDENCE: <0.0–1.0>\n"
            "REASONING: <one sentence>\n\n"
            f"INCOMING DOCUMENT (first 600 chars):\n{document[:600]}\n\n"
            f"VAULT FOLDERS:\n{folder_block}"
        )
        raw = self._invoke(prompt)
        return _parse_folder_routing(raw, folders)

    def synthesise(self, query: str, raw_context: str) -> str:
        """Reformat retrieved vault excerpts into a coherent briefing.

        The LLM acts as a formatter only — it must not add, infer, or extrapolate
        beyond the provided text. Citations [1], [2] … are preserved so the reader
        can verify every claim against the raw sources shown below.

        Uses think=True for Ollama so that qwen-family models can use their
        reasoning chain on the reorganisation task. The thinking tokens are
        discarded; only response.content (the briefing itself) is returned.
        """
        prompt = (
            "You are a context organiser. Your job is to rewrite the retrieved knowledge base "
            "excerpts below into a single, coherent, well-structured briefing that directly "
            "addresses the query.\n\n"
            "STRICT RULES — violations defeat the purpose:\n"
            "1. Use ONLY the information present in the excerpts. Do not add, infer, assume, or "
            "extrapolate anything that is not explicitly stated in the text below.\n"
            "2. Every factual claim in your output MUST be tagged with its source number, e.g. [1], [2].\n"
            "3. If something is not covered by the excerpts, do not mention it.\n"
            "4. Do not write an introduction or conclusion. Go straight into the content.\n"
            "5. Use clear headings and bullet points where the source material uses them.\n"
            "6. Do not repeat the same fact twice even if it appears in multiple sources.\n\n"
            f"QUERY: {query}\n\n"
            "RETRIEVED EXCERPTS:\n"
            "---\n"
            f"{raw_context}\n"
            "---\n\n"
            "Write the briefing now. Cite every claim with [source number]."
        )
        # Determine which backend + model to use for synthesis.
        # Priority:
        #   1. synthesise_backend + synthesise_model  (fully independent provider)
        #   2. same backend + synthesise_model        (different model, same provider)
        #   3. primary backend + model                (fallback — same as ingestion)
        synth_backend = self._cfg.synthesise_backend or self._cfg.backend
        synth_model   = self._cfg.synthesise_model
        synth_api_key = self._cfg.synthesise_api_key or self._cfg.api_key

        if synth_backend == "ollama" and synth_model:
            # Dedicated Ollama synthesis model (e.g. phi4-mini).
            # think=False is mandatory — thinking models burn token budget on <think>.
            from mdcore.core.deps import assert_backend_available
            assert_backend_available("ollama", "synthesise")
            from langchain_ollama import ChatOllama
            synth_llm = ChatOllama(
                model=synth_model,
                temperature=0,
                num_predict=self._cfg.max_tokens,
                think=False,
                request_timeout=self._cfg.timeout_seconds,
            )
            response = synth_llm.invoke(prompt)
            content = response.content  # type: ignore[attr-defined]
            if not content:
                raise RuntimeError(
                    f"Synthesise model '{synth_model}' returned an empty response. "
                    "Check 'ollama ps' and ensure the model is pulled."
                )
            self._log_tokens(synth_model, response)
        elif synth_backend != self._cfg.backend or (synth_model and synth_model != self._cfg.model):
            # Different backend or model from primary — build a dedicated LLM instance.
            model_name = synth_model or self._cfg.model
            synth_llm = _build_llm(synth_backend, model_name, synth_api_key, self._cfg)
            response = synth_llm.invoke(prompt)
            self._log_tokens(model_name, response)
            content = response.content  # type: ignore[attr-defined]
        else:
            content = self._invoke(prompt)

        return _strip_hallucinated_citations(content, raw_context)

    def propose(
        self,
        classification: ClassificationResult,
        existing_content: str,
        incoming_summary: str,
    ) -> str:
        action_desc = (
            f"UPDATE the file: {classification.target_file}"
            if classification.action == "update"
            else "CREATE a new file"
        )
        prompt = (
            "You are a knowledge base proposal writer. Write a concise human-readable proposal "
            "for the following ingestion action.\n\n"
            f"ACTION: {action_desc}\n"
            f"CONFIDENCE: {classification.confidence:.2f}\n\n"
            f"EXISTING FILE CONTENT (truncated):\n{existing_content[:600]}\n\n"
            f"INCOMING SUMMARY:\n{incoming_summary[:800]}\n\n"
            "Write the proposed changes as 2–4 bullet points. Be specific about what content "
            "will be added or changed. Do not include headers or preamble."
        )
        return self._invoke(prompt)


def _parse_classification(raw: str) -> ClassificationResult:
    lines = {
        k.strip().lower(): v.strip()
        for line in raw.strip().splitlines()
        if ":" in line
        for k, v in [line.split(":", 1)]
    }
    action = lines.get("action", "new").lower()
    if action not in ("update", "new"):
        action = "new"
    target = lines.get("target", "none")
    target = None if target.lower() in ("none", "") else target
    try:
        confidence = float(lines.get("confidence", "0.7"))
    except ValueError:
        confidence = 0.7
    reasoning = lines.get("reasoning", "")
    return ClassificationResult(action=action, target_file=target, confidence=confidence, reasoning=reasoning)


def _parse_folder_routing(raw: str, valid_folders: list[str]) -> FolderRoutingResult:
    lines: dict[str, str] = {}
    for line in raw.strip().splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            lines[key.strip().lower()] = val.strip()

    folder = lines.get("folder", "")
    # Validate — must be an exact match from the provided list
    if folder not in valid_folders:
        # Best-effort: case-insensitive fallback
        folder_lower = folder.lower()
        folder = next((f for f in valid_folders if f.lower() == folder_lower), valid_folders[0] if valid_folders else "")
    try:
        confidence = float(lines.get("confidence", "0.7"))
    except ValueError:
        confidence = 0.7
    reasoning = lines.get("reasoning", "")
    return FolderRoutingResult(folder=folder, confidence=confidence, reasoning=reasoning)
