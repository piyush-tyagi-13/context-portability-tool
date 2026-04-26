from __future__ import annotations

from mdcore.utils.logging import get_logger

log = get_logger("retriever.prefilter")

# Common English words that happen to start with an uppercase letter in folder
# names but are NOT person names. These are excluded when detecting whether a
# folder's first path component is a person's name.
_COMMON_FOLDER_WORDS = {
    "career", "learning", "misc", "notes", "projects", "personal",
    "programming", "noise", "emigration", "clippings", "related",
    "archive", "archives", "reading", "prep", "project", "annexes",
    "resources", "documents", "files", "work", "life", "private",
    "public", "inbox", "drafts", "templates", "reference", "areas",
    "daily", "weekly", "journal", "logs", "tasks", "todos",
}

# Score multiplier applied to files in other-person folders when the owner's
# name appears in the query.  0.2 drops a perfect-match score of 1.0 to 0.2,
# which falls below the default min_score of 0.3, effectively excluding them.
_OTHER_PERSON_PENALTY = 0.2


def _looks_like_person_name(word: str) -> bool:
    """Return True if word is plausibly a person's first name.

    Heuristic: starts with uppercase, not all-uppercase (rules out acronyms),
    purely alphabetic, 3–20 chars, not in the common folder words list.
    """
    if not (3 <= len(word) <= 20):
        return False
    if not word[0].isupper():
        return False
    if word.isupper():          # ALL-CAPS → acronym (AMEX, CBS, LBG…)
        return False
    if not word.isalpha():      # hyphens, digits → not a name
        return False
    if word.lower() in _COMMON_FOLDER_WORDS:
        return False
    return True


class KeywordPreFilter:
    def __init__(self, min_score: float = 0.3, owner_name: str = "") -> None:
        self._min_score = min_score
        # Support multi-word names ("Piyush Tyagi") — any word triggers the logic
        self._owner_words = {w.lower() for w in owner_name.split() if w}

    def filter(self, query: str, all_metadata: list[dict]) -> set[str]:
        """Return set of source_file values that have at least weak keyword overlap.

        When the vault owner's name appears in the query, this method:
          1. Strips the owner's name from keyword terms (it never appears in
             file content — people don't refer to themselves by name).
          2. Auto-detects "other-person" folder prefixes by scanning the first
             path component of every folder_path for plausible person names
             that are NOT the owner.
          3. Applies a strong score penalty to files in those folders so they
             are excluded unless the query specifically targets them.
        """
        raw_terms = set(query.lower().split())

        # ── Persona detection ─────────────────────────────────────────────────
        owner_in_query = bool(self._owner_words and self._owner_words & raw_terms)
        other_person_prefixes: set[str] = set()

        if owner_in_query:
            # Strip owner words from keyword terms — they add no signal
            terms = raw_terms - self._owner_words

            # Collect the first WORD of the first path component that looks like
            # a person's name but is not the vault owner.
            #
            # Why first word, not first component?
            #   folder_path for "Aishwarya Career/Resume.md" is "Aishwarya Career"
            #   (no slash — it's the immediate parent).  Splitting by "/" gives
            #   ["Aishwarya Career"] as one token; we need to split that further
            #   by space to isolate "Aishwarya".
            #
            # Use original-case meta for the uppercase check, store lowercase.
            for meta in all_metadata:
                folder_orig = meta.get("folder_path", "")
                if not folder_orig:
                    continue
                first_component = folder_orig.replace("\\", "/").split("/")[0].strip()
                first_word = first_component.split()[0] if first_component else ""
                if (_looks_like_person_name(first_word)
                        and first_word.lower() not in self._owner_words):
                    # Store the full first path component (lowercased) so the
                    # scoring loop can match against it exactly.
                    other_person_prefixes.add(first_component.lower())

            if other_person_prefixes:
                log.debug(
                    "Owner query detected — penalising other-person folders: %s",
                    other_person_prefixes,
                )
        else:
            terms = raw_terms

        # ── Scoring ───────────────────────────────────────────────────────────
        if not terms:
            # All terms were the owner's name — nothing left to match on;
            # fall back to returning everything (let vector search decide)
            log.debug("KeywordPreFilter: no terms remain after owner strip — returning all sources")
            return {meta.get("source_file", "") for meta in all_metadata}

        matching: set[str] = set()
        for meta in all_metadata:
            sf = meta.get("source_file", "")
            filename = meta.get("filename", "").lower()
            folder = meta.get("folder_path", "").lower()
            target = filename + " " + folder

            score = sum(1 for t in terms if t in target) / len(terms)

            # Penalise other-person folders.
            # folder is already lowercased; first_component is the first path
            # segment (e.g. "aishwarya career"), which matches what we stored.
            if other_person_prefixes:
                first_component = folder.replace("\\", "/").split("/")[0].strip()
                if first_component in other_person_prefixes:
                    score *= _OTHER_PERSON_PENALTY

            if score >= self._min_score:
                matching.add(sf)

        log.debug(
            "KeywordPreFilter: %d sources match query '%s' (owner_in_query=%s)",
            len(matching), query, owner_in_query,
        )
        return matching
