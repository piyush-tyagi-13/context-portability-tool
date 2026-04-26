from __future__ import annotations
from dataclasses import dataclass, field

from mdcore.core.ingester.classification_engine import ClassificationDecision
from mdcore.core.ingester.conflict_detector import ConflictPair
from mdcore.llm.llm_layer import LLMLayer
from mdcore.utils.logging import get_logger

log = get_logger("ingester.proposal")


@dataclass
class Proposal:
    action: str               # "update" | "new"
    target_file: str | None
    suggested_folder: str
    confidence: float
    proposal_text: str
    conflicts: list[ConflictPair] = field(default_factory=list)
    frontmatter_updates: dict = field(default_factory=dict)


class ProposalGenerator:
    def __init__(self, llm: LLMLayer) -> None:
        self._llm = llm

    def generate(
        self,
        decision: ClassificationDecision,
        incoming_summary: str,
        existing_content: str = "",
        conflicts: list[ConflictPair] | None = None,
        suggested_folder: str = "",
        frontmatter_updates: dict | None = None,
    ) -> Proposal:
        from mdcore.llm.llm_layer import ClassificationResult
        clf_result = ClassificationResult(
            action=decision.action,
            target_file=decision.target_file,
            reasoning=decision.reasoning,
            confidence=decision.confidence,
        )
        proposal_text = self._llm.propose(clf_result, existing_content, incoming_summary)

        return Proposal(
            action=decision.action,
            target_file=decision.target_file,
            suggested_folder=suggested_folder,
            confidence=decision.confidence,
            proposal_text=proposal_text,
            conflicts=conflicts or [],
            frontmatter_updates=frontmatter_updates or {},
        )
