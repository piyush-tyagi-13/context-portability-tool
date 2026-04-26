from __future__ import annotations
from datetime import datetime, timezone

from mdcore.core.retriever.context_assembler import AssembledContext
from mdcore.config.models import RetrieverConfig


def format_context(ctx: AssembledContext, cfg: RetrieverConfig) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M") if cfg.include_timestamp else ""
    header_parts = [f"Assembled by mdcore"]
    if cfg.include_word_count:
        header_parts.append(f"{ctx.source_count} sources · {ctx.total_words} words")
    if cfg.include_timestamp:
        header_parts.append(now)
    header = " · ".join(header_parts)

    lines: list[str] = [
        f"## Context package: {ctx.query}",
        f"*{header}*",
        "",
        "---",
    ]

    for i, (source_file, passages) in enumerate(ctx.primary, 1):
        breadcrumbs = list(dict.fromkeys(bc for p in passages for bc in p.breadcrumbs))
        bc_str = " · ".join(breadcrumbs) if breadcrumbs else source_file
        display = source_file if cfg.include_source_paths else source_file.split("/")[-1]
        lines += [
            "",
            f"### [{i}] {display}",
            f"*Sections: {bc_str}*",
            "",
        ]
        for p in passages:
            lines.append(p.text)
        lines.append("")
        lines.append("---")

    if ctx.signpost:
        lines += [
            "",
            "## Also available — fetch if the LLM needs to go deeper",
            "",
            "| Source | Relevant sections | Suggested query |",
            "|---|---|---|",
        ]
        for source_file, breadcrumbs in ctx.signpost:
            display = source_file if cfg.include_source_paths else source_file.split("/")[-1]
            sections = " · ".join(breadcrumbs[:3]) if breadcrumbs else "—"
            terms = _suggest_query(source_file, breadcrumbs)
            lines.append(f"| {display} | {sections} | `mdcore search \"{terms}\"` |")

        lines += [
            "",
            "---",
            "*Paste this block at the start of your LLM conversation as opening context.*",
            "*The LLM can ask you to run any suggested query above to fetch deeper context.*",
        ]

    return "\n".join(lines)


_MAX_SYNTH_CHARS = 4_000  # keep synthesis prompt manageable for local models


def raw_text_for_synthesis(ctx: AssembledContext) -> str:
    """Return numbered excerpt blocks suitable for passing to the synthesis LLM.

    Each block is labelled [N] with its source path and section breadcrumbs so
    the LLM can emit accurate citations. Total text is capped at _MAX_SYNTH_CHARS
    so the prompt stays within a comfortable range for local models.
    """
    blocks: list[str] = []
    total_chars = 0
    for i, (source_file, passages) in enumerate(ctx.primary, 1):
        breadcrumbs = list(dict.fromkeys(bc for p in passages for bc in p.breadcrumbs))
        bc_str = " › ".join(breadcrumbs) if breadcrumbs else ""
        header = f"[{i}] Source: {source_file}"
        if bc_str:
            header += f"  |  Sections: {bc_str}"
        text = "\n".join(p.text for p in passages)

        remaining = _MAX_SYNTH_CHARS - total_chars
        if remaining <= 0:
            break
        if len(text) > remaining:
            text = text[:remaining] + " …[truncated]"

        block = f"{header}\n{text}"
        blocks.append(block)
        total_chars += len(block)

    return "\n\n".join(blocks)


def _suggest_query(source_file: str, breadcrumbs: list[str]) -> str:
    parts = source_file.replace("/", " ").replace(".md", "").split()
    bc_words = breadcrumbs[0].replace(">", "").split() if breadcrumbs else []
    combined = (parts + bc_words)[:5]
    return " ".join(combined)
