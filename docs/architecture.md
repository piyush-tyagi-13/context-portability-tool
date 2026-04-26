# ctxkit — Architecture Blueprint
**Context Portability and Knowledge Ingestion Tool**

Version: 1.1.0 | Status: Design Phase | Last Updated: April 2026

> **v1.1.0 corrections:** Updated embedding model from `all-MiniLM-L6-v2` to `nomic-embed-text` (Ollama-native, 8192 token context). Updated LLM model from `llama3.1` to `qwen3.5:4b` with `think=false`. Retriever redesigned from single-chunk-per-source deduplication to full context packager with `ChunkGrouper`, `ChunkStitcher`, and `SourceRanker`. Word budget increased from 500 to 1000 words. Top K increased from 6 to 15. Heading-aware splitting added to TextSplitter. Full breadcrumb metadata added to all chunks. Output format updated to cited, source-attributed context package. `ctxkit eval` command added to CLI.
>
> **v1.2.0 additions:** LLM synthesis added to Flow A — raw excerpts are now reformatted into a coherent briefing by a dedicated `synthesise_model` (default: `phi4-mini`). Search output written to `<vault>/ctxkit-output/YYYY-MM-DD-<slug>.md` instead of terminal. `--raw` flag skips synthesis. `vault.owner_name` added for multi-person vault routing — owner-aware keyword prefilter penalises other-person folder prefixes. Phase-2 keyword rescue in `VectorSearcher` using ChromaDB `$in` filter ensures vocabulary-mismatched files (e.g. "emigration" query vs. visa/Chancenkarte content) are not silently dropped. Hallucination guard strips citation numbers exceeding actual source count. `search_in_sources()` added to VectorStore.

---

## Table of Contents

1. [Product Definition](#1-product-definition)
2. [Problem Statements](#2-problem-statements)
3. [Design Principles](#3-design-principles)
4. [Tech Stack](#4-tech-stack)
5. [High Level Architecture](#5-high-level-architecture)
6. [Component Architecture](#6-component-architecture)
   - 6.1 [CLI Layer](#61-cli-layer)
   - 6.2 [Config](#62-config)
   - 6.3 [Indexer](#63-indexer)
   - 6.4 [Retriever](#64-retriever)
   - 6.5 [Ingester](#65-ingester)
   - 6.6 [Writer](#66-writer)
   - 6.7 [LLM Layer](#67-llm-layer)
   - 6.8 [Vector Store](#68-vector-store)
7. [Data Flows](#7-data-flows)
8. [LLM Call Map](#8-llm-call-map)
9. [Configuration Reference](#9-configuration-reference)
10. [Project Structure](#10-project-structure)
11. [Hardware Tiers](#11-hardware-tiers)
12. [What ctxkit Is Not](#12-what-ctxkit-is-not)

---

## 1. Product Definition

**Full name:** Context Portability and Knowledge Ingestion Tool

**CLI name:** `ctxkit`

**One line:** A local, LLM-agnostic context delivery and knowledge sync tool for users who live across multiple subscription LLMs.

**Primary user:** A technically literate knowledge worker who subscribes to one or more LLM platforms (Claude, ChatGPT, Gemini), maintains a personal markdown knowledge base, and switches between LLMs based on cost, capability, or availability. Comfortable with a CLI tool. Does not want to pay twice for intelligence they already have access to via subscriptions.

---

## 2. Problem Statements

### Part 1 — Context Portability

A knowledge worker who uses multiple subscription LLMs interchangeably has no reliable way to carry personal and professional context across those tools. Each LLM handles memory differently — and while memory can technically be exported from most platforms, the way each LLM utilises that memory during a conversation is inconsistent, particularly as context windows fill up. The result is that every new conversation, and often every mid-conversation topic shift, requires significant manual re-explanation of background the user has already articulated before.

The user has a growing personal knowledge base in markdown format covering technical domains (architecture decisions, stack-specific patterns, project context) and personal domains (career goals, role research, interview frameworks). This knowledge base is LLM-agnostic and under the user's full control — but it is currently inert. It is not queryable in any meaningful way, and nothing bridges it to the LLMs the user converses with daily.

The conventional solution — a RAG agent that queries the knowledge base and injects context via API calls — is not economically viable for daily use. API pricing is per-token, and context-heavy interactions make costs compound quickly. Critically, almost every user in this situation is already paying a flat subscription to one or more LLM platforms (OpenAI, Anthropic, Google). The API route would mean paying again, on top of subscriptions they are already committed to, for functionality that should work with what they already have.

The goal therefore is to bridge the user's personal knowledge base to whichever subscription LLM they are using at any given moment — without API dependency, without manual file hunting, and without injecting so much context that the conversation becomes unwieldy. The tool must be LLM-agnostic by design, since the choice of LLM at any moment is driven by cost, availability, or capability — not by the tool.

### Part 2 — Knowledge Base Freshness and Index Synchronisation

A user's personal knowledge base is only as useful as it is current. The context portability tool described in Part 1 assumes that the markdown files it retrieves from are accurate representations of the user's latest thinking, decisions, and discussion outcomes. But in practice, knowledge bases go stale.

This creates a two-layer freshness problem:

**The raw layer** — markdown files are not being updated after meaningful LLM conversations. Session summaries, new decisions, revised positions, and newly learned concepts exist only inside the LLM's context window and disappear when the session ends.

**The index layer** — even when markdown files do get updated manually, the vector store and search index are not automatically aware of those changes. A stale index returns stale context, silently, with no indication that newer information exists.

The result is that the retrieval tool gradually becomes less trustworthy over time — not because retrieval is broken, but because the knowledge it retrieves from has drifted behind reality.

---

## 3. Design Principles

**LLM as last resort, not first instinct**
Every step that can be solved deterministically — keyword filtering, vector similarity routing, conflict flagging — is solved without an LLM. In Flow A, one local LLM call fires for synthesis (reformatting raw excerpts into a coherent briefing). Skip it with `--raw` for a fully LLM-free retrieval path. In Flow B, the generative model only fires for ambiguous classification and proposal generation.

**Hardware tiered**
Runs meaningfully on low-end hardware using CPU-based embeddings and cloud API for LLM steps. Scales up to full local execution on capable machines via Ollama. User configures their backend once at setup.

**LLM agnostic**
The tool has no preference for which LLM the user converses with. It works identically whether the user is on claude.ai, chatgpt.com, or gemini.google.com.

**Human in the loop always**
The tool never writes to the knowledge base autonomously. Every proposed change requires explicit user approval before any file is touched.

**Subscription first**
Designed from the ground up to work with subscription LLMs as the conversation layer, not API keys. API keys are supported as a configuration option for the local tool's LLM steps only — not as a replacement for the subscription workflow.

**Configuration as control plane**
Code is the fixed engine. Configuration is the control plane. Every tuneable parameter is externalised into config. No magic numbers in code. No code changes required after initial development — all behaviour is managed via config.

**Noise isolation is user responsibility**
A designated noise folder is excluded from all indexing. What goes into noise is the user's decision. The tool applies a minimum quality filter (word count, structure signals) as a silent secondary guard.

---

## 4. Tech Stack

| Concern | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Widest library support for embeddings, vector DBs, LLMs, and CLI tooling |
| CLI framework | Typer + Rich | Typer for command structure, Rich for terminal UI rendering (openclaw-style) |
| Config validation | Pydantic v2 | Typed config models per component, clear validation errors at startup |
| Embedding model (local) | `nomic-embed-text` via Ollama | 137M params, ~0.5GB RAM, 8192 token context, very fast on Apple Silicon. Default for M2 Air. `bge-m3` recommended for desktop (higher quality, 100+ languages). |
| Vector store | ChromaDB | Fully local, no server required, good Python SDK, handles incremental updates |
| RAG and LLM layer | LangChain | Unified interface for LLM providers, document loaders, text splitters, retrieval chains. Growth surface for future agent features |
| Local LLM | Ollama | Clean Python SDK, model-agnostic, runs on both Apple Silicon and NVIDIA GPU |
| Cloud LLM providers | LangChain (ChatOpenAI / ChatAnthropic / ChatGoogleGenerativeAI) | Provider switching is config-driven, zero code change |
| Frontmatter handling | python-frontmatter | Reads and writes YAML frontmatter without touching file content |
| Markdown parsing | markdown-it-py | Reliable markdown AST for structure signal detection |
| Config format | YAML | Human-readable, comment-friendly, well-supported in Python |
| Packaging | pip installable Python package | `pip install ctxkit` for ease of distribution |

---

## 5. High Level Architecture

```
┌─────────────────────────────────────────────────────┐
│                   YOUR MARKDOWN VAULT                │
│         (Obsidian or any markdown folder tree)       │
└─────────────────────────┬───────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│                      ctxkit core                     │
│                                                      │
│   ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│   │ Indexer  │  │Retriever │  │    Ingester       │  │
│   └──────────┘  └──────────┘  └──────────────────┘  │
│   ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│   │  Writer  │  │LLM Layer │  │   Vector Store    │  │
│   └──────────┘  └──────────┘  └──────────────────┘  │
│                                                      │
│              Config | CLI | Logging                  │
└─────────────────────────┬───────────────────────────┘
                          │
              (copy-paste by user)
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│          ANY SUBSCRIPTION LLM OF YOUR CHOICE         │
│        Claude  |  ChatGPT  |  Gemini  |  Others      │
└─────────────────────────────────────────────────────┘
```

`ctxkit` sits entirely in the middle layer. It never talks to your subscription LLM directly. It only prepares context for it (Flow A) and processes output from it (Flow B). The user is the bridge between ctxkit and their LLM.

---

## 6. Component Architecture

### 6.1 CLI Layer

**Tech:** Typer + Rich

**Responsibility:** The only surface the user directly interacts with. Intentionally thin — parses commands, delegates immediately to core components, renders output via Rich. Zero business logic.

**Commands:**

```bash
ctxkit init                     # interactive setup wizard — create ~/.ctxkit/config.yaml
ctxkit index                    # scan vault, show diff, confirm, index delta
ctxkit search <topic>           # flow A — synthesise briefing → write to <vault>/ctxkit-output/
ctxkit search <topic> --raw     # flow A — raw excerpts only, no LLM synthesis
ctxkit search <topic> --verbose # show chunk similarity scores
ctxkit ingest                   # flow B — accept session summary, classify, propose
ctxkit ingest --file <path>     # flow B — ingest from file
ctxkit status                   # show index health, drift warnings, last sync
ctxkit eval                     # run user-guided quality check on retrieval output
ctxkit config                   # open config file in default editor
ctxkit config --validate        # validate config file and report errors
```

**Rich rendering responsibilities:**
- Progress bars during indexing
- Syntax-highlighted context block output
- Diff-style proposal display during ingestion
- Confirmation prompts before any write operation
- Status dashboard with index health indicators
- Colour-coded drift warnings

---

### 6.2 Config

**Tech:** YAML + Pydantic v2

**Responsibility:** Single source of truth for all component behaviour. Loaded once at startup. Validated against Pydantic models. Each component receives only its own typed config section — never the full config object.

**Config location:** `~/.ctxkit/config.yaml`

**Pydantic model pattern:**

```python
class IndexerConfig(BaseModel):
    min_word_count: int = 50
    min_structure_signals: int = 1
    manifest_path: str = "~/.ctxkit/manifest.json"
    chunk_size: int = 512
    chunk_overlap: int = 64
    max_chunk_words: int = 400
    heading_aware_splitting: bool = True
    preserve_tables: bool = True
    preserve_code_blocks: bool = True
    heading_levels: list[int] = [2, 3]
    batch_size: int = 32
    metadata_fields: list[str]

class CtxKitConfig(BaseModel):
    vault: VaultConfig
    indexer: IndexerConfig
    embeddings: EmbeddingsConfig
    vector_store: VectorStoreConfig
    retriever: RetrieverConfig
    ingester: IngesterConfig
    writer: WriterConfig
    llm: LLMConfig
    manifest: ManifestConfig
    cli: CLIConfig
    logging: LoggingConfig
```

Missing fields use Pydantic defaults. Required missing fields raise a clear validation error at startup — not buried in a runtime crash.

**Multiple config profiles support:**

```bash
ctxkit search "istio auth" --config ~/.ctxkit/config-technical.yaml
ctxkit search "career goals" --config ~/.ctxkit/config-personal.yaml
```

Zero change to component code — profile switching is a CLI flag only.

---

### 6.3 Indexer

**Tech:** LangChain (UnstructuredMarkdownLoader, RecursiveCharacterTextSplitter), sentence-transformers, ChromaDB, python-frontmatter

**Responsibility:** Scans the vault, identifies what needs indexing, loads and chunks documents, generates embeddings, writes to vector store, maintains the index manifest.

**Sub-components:**

`VaultScanner`
- Walks vault directory tree recursively
- Excludes noise folder and any configured exclusions
- Excludes non-markdown file extensions
- Applies minimum word count filter
- Applies minimum structure signal filter (headings, paragraphs)
- Returns list of eligible file paths with folder path as metadata

`ManifestManager`
- Reads `~/.ctxkit/manifest.json` on startup
- Compares manifest timestamps against filesystem `mtime` for each file
- Identifies three categories: new files, modified files, deleted files
- Presents diff to user via CLI before any indexing begins
- Updates manifest after successful indexing of each file

`DocumentLoader`
- Wraps LangChain `UnstructuredMarkdownLoader`
- Loads each markdown file
- Preserves folder path, filename, and existing frontmatter as metadata
- Passes raw `Document` objects downstream

`TextSplitter`
- Uses heading-aware splitting strategy: splits on markdown headings (`##`, `###`) first, then by token count within sections that exceed `max_chunk_words`
- Heading sections below `min_chunk_words` are merged with the next sibling section under the same parent heading
- Tables and code blocks are never split mid-block — kept intact as single chunks even if oversized
- Captures heading breadcrumb chain for each chunk (e.g. `The Two Ingress Paths > Path 1 — Bruno`) and stores as metadata
- Chunk size, overlap, heading levels, and preservation flags are all config-driven
- Attaches chunk index and chunk total to metadata for ordering and stitching

`EmbeddingEngine`
- Wraps LangChain embedding interface
- Default: `HuggingFaceEmbeddings` with `all-MiniLM-L6-v2` (local, CPU)
- Config-switched: `OpenAIEmbeddings` or equivalent for API backends
- Embedding cache: stores computed embeddings keyed by file hash to avoid recompute on unchanged files
- Rest of system never touches this directly — only via EmbeddingEngine

`IndexWriter`
- Takes embedded chunks, writes to ChromaDB via Store layer
- Stores metadata per chunk: source_file, folder_path, filename, heading_breadcrumb, chunk_index, chunk_total, word_count, is_table, is_code, last_indexed
- On reindex of a single file: deletes all existing chunks for that source_file before writing new ones
- Prevents duplicate or stale chunks accumulating

**Full index flow:**

```
ctxkit index
    → VaultScanner (eligible files list)
        → ManifestManager (diff: new | modified | deleted)
            → CLI presents diff, user confirms
                → DocumentLoader (per file in delta)
                    → TextSplitter
                        → EmbeddingEngine
                            → IndexWriter → ChromaDB
                                → ManifestManager (update manifest)
```

**On-demand only. No background watcher.**

---

### 6.4 Retriever

**Tech:** LangChain (Chroma retriever), Ollama embedding model, Rich

**Responsibility:** Given a topic query, assembles a comprehensive, cited, up-to-1000-word context package from the vault — ready to paste into any subscription LLM as the opening context of a conversation. ctxkit is a context packager, not a question-answering agent. The subscription LLM does the reasoning; ctxkit does the knowledge delivery.

**Sub-components:**

`KeywordPreFilter`
- Runs before any vector search
- Keyword match against file titles and folder paths stored in index metadata
- Pure string matching — no ML, no embeddings
- Narrows candidate pool before vector search runs
- Runs in milliseconds
- Config flag: `keyword_prefilter: true/false`
- **Owner-aware routing** (when `vault.owner_name` is set): if the query mentions the owner's name, ctxkit strips the owner word from the vector query and detects other-person top-level folder prefixes by heuristic (Title-Case single alphabetic word, not a common folder term). Chunks from detected other-person folders receive a `0.2×` score penalty — dropping them below `min_score` threshold — so queries like `"piyush career"` route to the owner's files even when another person's career folder exists in the vault.

`VectorSearcher`
- Wraps ChromaDB retriever
- Operates on narrowed candidate pool from KeywordPreFilter
- Returns top K=15 chunks with cosine similarity scores
- K=15 (not 6) to ensure enough raw material for 1000-word assembly
- K is config-driven
- **Phase-2 keyword rescue:** after the main similarity search, checks whether any keyword-prefilter candidate files got zero chunks above the threshold (vocabulary mismatch — e.g. query uses "emigration" but file content uses "visa", "Chancenkarte", "sponsorship"). For those files, runs a targeted ChromaDB `$in`-filtered search at `threshold × 0.75`. This ensures files matched by filename/folder keywords always get representation even when query vocabulary differs from content vocabulary.

`ChunkGrouper`
- Groups retrieved chunks by source file
- Within each source file, sorts chunks by chunk_index (document order)
- Preserves reading order within each source for coherent stitching

`ChunkStitcher`
- Detects adjacent or near-adjacent chunks within each source file group
- Adjacent = chunk_index N and N+1; near-adjacent = N and N+2 (intervening chunk included)
- Stitches qualifying chunks into coherent passages rather than disconnected fragments
- Stitched passages capped at max_stitch_words (default 400) to prevent single file dominating budget
- Stitching never crosses source file boundaries

`SourceRanker`
- Ranks source files by aggregate relevance score
- Aggregate score = weighted sum of individual chunk similarity scores within that source, normalised by chunk count
- Highest ranked source appears first in the assembled output

`ContextAssembler`
- Assembles output from ranked sources up to configured word budget (default 1000 words)
- Sources fitting within budget are included in full as primary context
- Sources that do not fit go into the signpost list with their most relevant section headings
- Enforces max_chunks_per_source cap to prevent one large file consuming the entire budget
- Attaches heading breadcrumb to each passage from chunk metadata

`ContextFormatter`
- Renders final output as a structured, cited markdown block
- Each source passage prefixed with vault-relative path and heading breadcrumb sections
- Signpost list rendered as a table with source, relevant sections, and suggested follow-up query
- Output format is config-driven (markdown | plain)
- Also produces a capped (`_MAX_SYNTH_CHARS = 4000`) raw text block for synthesis input

`LLMSynthesiser`
- Takes raw excerpts from ContextFormatter and passes to `LLMLayer.synthesise()`
- Uses a dedicated `synthesise_model` (default: `phi4-mini`) configured separately from the primary `model`
- **Why a separate model?** Thinking models like `qwen3.5:4b` consume their token budget on `<think>` tokens, leaving nothing for the actual briefing. `phi4-mini` (Microsoft Phi-4 Mini 3.8B) is non-thinking, instruction-following, and completes synthesis in ~10s vs 3–5 min on M2 Air.
- LLMLayer applies strict grounding prompt: cites every claim with `[N]`, no additions or extrapolations beyond provided text
- Hallucination guard strips any `[N]` citation where N exceeds actual source count (phi4-mini occasionally emits out-of-range citation numbers)
- Skipped entirely when `--raw` flag is passed

**Output:** written to `<vault>/ctxkit-output/YYYY-MM-DD-<query-slug>.md` (not rendered to terminal). Terminal prints one confirmation line: `✓ Saved → <path>  (N sources · synthesised)`.

**Output file format:**

```markdown
# [query]

*YYYY-MM-DD HH:MM UTC · N sources · synthesised by phi4-mini*

> ⚠ Verify claims against raw excerpts below.

## Briefing

[Coherent, cited prose reformatted from raw excerpts — every claim tagged [1], [2] …]

---

## Raw Excerpts

### [1] [Folder path / Filename]
*Sections: [heading breadcrumbs of included chunks]*

[Raw assembled passage]

---

## Also available — fetch if the LLM needs to go deeper

| Source | Relevant sections | Suggested query |
|---|---|---|
| [path/filename] | [section headings] | `ctxkit search "[suggested terms]"` |

---
*Paste this block at the start of your LLM conversation as opening context.*
*The LLM can ask you to run any suggested query above to fetch deeper context.*
```

**Retrieval flow (default — with synthesis):**

```
ctxkit search "Bruno ingress path adaptor"
    → KeywordPreFilter (metadata scan, owner-aware penalty)
        → VectorSearcher (top K=15, phase-2 rescue for vocabulary-mismatched files)
            → ChunkGrouper (group by source, sort by position)
                → ChunkStitcher (stitch adjacent chunks into passages)
                    → SourceRanker (rank sources by aggregate score)
                        → ContextAssembler (fill word budget, build signpost)
                            → ContextFormatter (cited markdown block + raw_text_for_synthesis)
                                → LLMSynthesiser (phi4-mini, ~10s) ← one LLM call
                                    → write <vault>/ctxkit-output/YYYY-MM-DD-<slug>.md
                                        → terminal: ✓ Saved → <path>
                                            → user opens file, copies, pastes into LLM
```

**Retrieval flow (`--raw` — no LLM call):**

```
ctxkit search "topic" --raw
    → [same up to ContextFormatter]
        → write raw excerpts only to <vault>/ctxkit-output/YYYY-MM-DD-<slug>.md
            → terminal: ✓ Saved → <path>  (N sources · raw)
```

---

### 6.5 Ingester

**Tech:** LangChain, sentence-transformers, ChromaDB, markdown-it-py

**Responsibility:** Accepts an incoming session summary from a completed LLM conversation, classifies it against the existing knowledge base, detects conflicts, and generates a proposal for user approval. Writes nothing — that is the Writer's job.

**Sub-components:**

`SummaryReceiver`
- Two input modes: paste directly into terminal prompt, or pass a file path
- Validates minimum structure: at least one heading, minimum word count (config-driven)
- Rejects malformed or empty input with clear error message

`SummaryEmbedder`
- Embeds the entire incoming summary as a single vector
- Uses the same EmbeddingEngine as Indexer — consistency is critical
- Also embeds at sentence level for ConflictDetector

`ClassificationEngine`
- Compares summary embedding against file-level aggregate embeddings in ChromaDB
- Note: file-level aggregates, not chunk-level — classification is about the whole document, not fragments
- Returns similarity scores against all indexed files
- Applies threshold logic:

```
similarity > threshold_high (default 0.82)
    → clear update candidate
    → top matching file is the target
    → no LLM call needed

similarity < threshold_low (default 0.65)
    → clear new file candidate
    → pass to FolderRouter to determine target folder
    → no LLM call needed

threshold_low ≤ similarity ≤ threshold_high
    → ambiguous
    → pass top N candidate files to LLM layer for adjudication
    → LLM returns classification decision with reasoning
```

`FolderRouter`
- Fires for new file cases
- Matches summary content keywords against folder names and existing file titles per folder
- Returns folder suggestion with confidence score
- Below confidence threshold (config-driven): prompts user to confirm folder
- Above threshold: includes folder in proposal as suggested, user can override

`ConflictDetector`
- Fires for update cases only
- Sentence-level embedding comparison between incoming summary and existing file
- Flags sentence pairs where similarity is in the conflict band (config-driven min/max)
  - Too low: unrelated sentences, not a conflict
  - Too high: same claim, not a contradiction
  - In band: same topic, potentially different position — flag for review
- Surfaces flagged pairs in proposal for user review

`ProposalGenerator`
- Assembles full proposal from classification decision, folder routing, and conflict flags
- Calls LLM layer to generate human-readable proposal text
- For clear cases: LLM writes the proposal text only (decision already made deterministically)
- For ambiguous cases: LLM already adjudicated in ClassificationEngine; ProposalGenerator formats that decision

**Proposal output (Rich rendered):**

```
PROPOSAL — ctxkit ingestion
─────────────────────────────────────────────
Action:       UPDATE existing file
Target:       /Career/EM-transition.md
Confidence:   0.91

Changes proposed:
+ [new section or appended content shown here]

Possible conflicts detected:
! Existing:  "Targeting EM roles at product companies"
  Incoming:  "Shifting focus toward Principal Engineer track"
  → Review before approving

Frontmatter to be added/updated:
  tags: [career, em-transition, principal-engineer]
  updated: 2026-04-20
  related: [interview-framework.md]

[A] Approve   [E] Edit first   [R] Reject
─────────────────────────────────────────────
```

**Ingestion flow:**

```
ctxkit ingest
    → SummaryReceiver (validate input)
        → SummaryEmbedder (full + sentence level)
            → ClassificationEngine (threshold logic)
                → clear match → FolderRouter skipped
                → new file   → FolderRouter
                → ambiguous  → LLM Layer (adjudicate)
            → ConflictDetector (update cases only)
                → ProposalGenerator
                    → LLM Layer (generate proposal text)
                        → Rich renders proposal
                            → user: Approve | Edit | Reject
                                → if Approved → Writer
                                → if Rejected → exit cleanly
```

---

### 6.6 Writer

**Tech:** python-frontmatter, standard file I/O

**Responsibility:** Executes approved write operations. Handles frontmatter injection. Creates backups before writing. Triggers reindex of written file. Never fires without explicit user approval.

**Sub-components:**

`BackupManager`
- Before any write: copies current file to `~/.ctxkit/backups/`
- Backup filename includes timestamp: `EM-transition.md.2026-04-20T14-32.bak`
- Rolling backups: max N backups per file (config-driven), oldest deleted when exceeded
- Enabled/disabled via config

`FrontmatterInjector`
- Uses `python-frontmatter` to read existing frontmatter if present
- Merges new fields: tags (deduplicated), updated (timestamp), related (deduplicated file list)
- Writes back without touching file content body
- Respects max tag count and max related count (config-driven)

`FileWriter`
- For updates: appends new content at configured position (end of file or after last heading)
- For new files: creates file in resolved target folder with clean structure and injected frontmatter
- Atomic write: writes to temp file first, renames on success — prevents partial writes corrupting files

`IndexTrigger`
- After successful write: fires targeted reindex of the written file through Indexer
- Does not wait for `ctxkit index` — triggers immediately
- Ensures index is current before user's next retrieval

**Writer flow:**

```
user approves proposal
    → BackupManager (backup current file if update)
        → FrontmatterInjector (merge frontmatter)
            → FileWriter (atomic write)
                → IndexTrigger (reindex single file)
                    → ManifestManager (update manifest entry)
                        → CLI confirms success
```

---

### 6.7 LLM Layer

**Tech:** LangChain (ChatOllama, ChatOpenAI, ChatAnthropic, ChatGoogleGenerativeAI)

**Responsibility:** Single abstraction layer for all generative LLM calls in ctxkit. No other component touches LangChain LLM interfaces directly. This keeps LangChain contained, testable, and swappable.

**Three functions exposed to the rest of ctxkit:**

```python
def classify(summary: str, candidates: list[Document]) -> ClassificationResult:
    """
    Used by ClassificationEngine for ambiguous cases.
    Returns: target file, action (update|new), reasoning, confidence
    """

def propose(
    classification: ClassificationResult,
    existing_content: str,
    incoming_summary: str
) -> str:
    """
    Used by ProposalGenerator.
    Returns: human-readable proposal text for Rich rendering
    """

def synthesise(query: str, raw_context: str) -> str:
    """
    Used by LLMSynthesiser in Flow A.
    Reformats raw vault excerpts into a coherent, cited briefing.
    Strict grounding: only information present in raw_context, every claim cited [N].
    Returns: synthesised briefing string (markdown)
    """
```

**Two-model design:**

`synthesise()` uses a dedicated `synthesise_model` when configured (Ollama only), bypassing the primary `model`. This is critical when `model` is a thinking model (e.g. `qwen3.5:4b`):
- Thinking models consume their `max_tokens` budget on `<think>` tokens first
- With budget `1000`, the actual briefing gets zero tokens → empty response
- `phi4-mini` is non-thinking: all tokens go to the briefing
- `synthesise_model` is ignored for non-Ollama backends (API models handle `think` differently)

```python
# synthesise() model selection logic
if backend == "ollama" and synthesise_model:
    synth_llm = ChatOllama(model=synthesise_model, think=False, temperature=0)
    response = synth_llm.invoke(prompt)
else:
    response = self._invoke(prompt)  # uses primary model
```

**Hallucination guard:**
After synthesis, `_strip_hallucinated_citations()` counts actual source blocks (`[1]`, `[2]` … headers in raw context) and strips any `[N]` citation in the briefing where N exceeds that count. phi4-mini occasionally emits `[3]` or `[4]` with only 1–2 sources provided.

**Provider switching (config-driven, zero code change):**

```python
match config.llm.backend:
    case "ollama":
        llm = ChatOllama(
            model=config.llm.model,
            think=False          # disables thinking mode — passed per API call
        )
    case "openai":
        llm = ChatOpenAI(model=config.llm.model, api_key=config.llm.api_key)
    case "anthropic":
        llm = ChatAnthropic(model=config.llm.model, api_key=config.llm.api_key)
    case "gemini":
        llm = ChatGoogleGenerativeAI(model=config.llm.model, api_key=config.llm.api_key)
```

**Fallback support:**
If primary LLM call fails (timeout, API error, Ollama not running), falls back to configured fallback backend if defined. If no fallback, surfaces clear error and prompts user to resolve or approve manually.

**Prompt design note:**
`classify` and `propose` prompts are tight and well-scoped. Hard decisions are made deterministically before LLM is called. `synthesise` uses a strict grounding prompt: no additions, no inference, every claim cited — the LLM acts as a formatter, not a reasoner.

---

### 6.8 Vector Store

**Tech:** ChromaDB

**Responsibility:** Thin wrapper around ChromaDB. The single interface for all vector store operations. No other component accesses ChromaDB directly.

**Five operations exposed:**

```python
def upsert(chunks: list[Document], metadata: list[dict]) -> None:
    """Add or update chunks for a source file"""

def delete(source_file: str) -> None:
    """Remove all chunks for a given source file"""

def search(query_embedding: list[float], k: int, filter: dict = None) -> list[Document]:
    """Cosine similarity search, optional metadata filter"""

def search_in_sources(
    query_embedding: list[float],
    source_files: set[str],
    k: int
) -> list[Document]:
    """
    Vector search restricted to specific source_file values.
    Uses ChromaDB $in filter — only chunks from these files are ranked.
    Used by VectorSearcher phase-2 rescue for keyword-matched files
    that score below the main similarity threshold in phase-1.
    """

def file_embeddings() -> dict[str, list[float]]:
    """Aggregate file-level embeddings for ClassificationEngine"""
```

**Persistence:** ChromaDB persists to disk at configured path. No server process required. Loads on ctxkit startup, writes immediately on upsert/delete.

---

## 7. Data Flows

### Flow A — Context Retrieval (Outward)

```
User types topic into terminal
         │
         ▼
    ctxkit search [--raw]
         │
         ▼
  KeywordPreFilter ──── scans index metadata, owner-aware penalty (milliseconds)
         │
         ▼
  VectorSearcher ─────── cosine similarity top K=15, phase-2 rescue for vocab-mismatched files
         │
         ▼
  ChunkGrouper ────────── group by source file, sort by document order
         │
         ▼
  ChunkStitcher ───────── stitch adjacent chunks into coherent passages
         │
         ▼
  SourceRanker ────────── rank sources by aggregate similarity score
         │
         ▼
  ContextAssembler ───── fill word budget, build signpost list
         │
         ▼
  ContextFormatter ───── cited markdown block + raw_text_for_synthesis (capped 4000 chars)
         │
         ├─── --raw ───► write raw excerpts → <vault>/ctxkit-output/YYYY-MM-DD-<slug>.md
         │
         └─── default ─► LLMSynthesiser
                              │  phi4-mini (non-thinking, ~10s on M2 Air)
                              │  strict grounding prompt + hallucination guard
                              ▼
                         write briefing + raw excerpts → <vault>/ctxkit-output/YYYY-MM-DD-<slug>.md
         │
         ▼
  Terminal: ✓ Saved → <path>  (N sources · synthesised|raw)
         │
    (user opens file, copies contents)
         │
         ▼
  Pasted into Claude / ChatGPT / Gemini
```

**LLM calls in this flow: one** (synthesis via `phi4-mini`). **Zero with `--raw`.**

---

### Flow B — Knowledge Ingestion (Inward)

```
LLM session ends
User runs standardised summary prompt in LLM chat
LLM produces structured markdown summary
         │
         ▼
    ctxkit ingest
         │
         ▼
  SummaryReceiver ─────── validate structure and length
         │
         ▼
  SummaryEmbedder ─────── embed full summary + sentences
         │
         ▼
  ClassificationEngine
         ├── similarity > 0.82 ──► clear update, no LLM
         ├── similarity < 0.65 ──► clear new file, no LLM
         └── in between ─────────► LLM Layer (adjudicate)
         │
         ▼
  FolderRouter (new file cases only)
         │
         ▼
  ConflictDetector (update cases only)
         │
         ▼
  ProposalGenerator ──── LLM Layer (generate proposal text)
         │
         ▼
  Rich renders proposal
         │
  User: [A]pprove / [E]dit / [R]eject
         │
    ┌────┴─────┐
  Approve    Reject
    │           │
    ▼         exit
  BackupManager
    │
    ▼
  FrontmatterInjector
    │
    ▼
  FileWriter (atomic)
    │
    ▼
  IndexTrigger ────► Indexer (single file reindex) ────► ChromaDB
    │
    ▼
  ManifestManager (update entry)
    │
    ▼
  CLI confirms success
```

---

### Flow C — On-Demand Index Sync

```
    ctxkit index
         │
         ▼
  VaultScanner ─────── eligible files list
         │
         ▼
  ManifestManager ──── diff against filesystem mtime
         │
         ▼
  CLI presents diff:
    New files (N)
    Modified files (N)
    Deleted files (N)
         │
  User: [A]ll / [S]elect / [C]ancel
         │
         ▼
  Per file in confirmed delta:
    DocumentLoader → TextSplitter → EmbeddingEngine → IndexWriter → ChromaDB
         │
         ▼
  ManifestManager (update all indexed entries)
         │
         ▼
  CLI reports: N files indexed, N skipped, time taken
```

---

## 8. LLM Call Map

| Situation | LLM fires? | Model | Why |
|---|---|---|---|
| Flow A: retrieval (default) | Yes — synthesise() | `synthesise_model` (phi4-mini) | Reformat raw excerpts into coherent briefing |
| Flow A: retrieval (`--raw`) | Never | — | Raw excerpts only, no synthesis |
| Flow B: ingestion, clear match (>0.82) | No | — | Deterministic threshold |
| Flow B: ingestion, clear new file (<0.65) | No | — | Deterministic threshold |
| Flow B: ingestion, ambiguous (in band) | Yes — classify() | `model` (qwen3.5:4b) | Needs language adjudication |
| Flow B: proposal generation | Yes — propose() | `model` (qwen3.5:4b) | Needs human-readable output |
| Flow C: index sync | Never | — | Pure embedding |
| Conflict detection | No | — | Sentence-level embedding comparison |
| Folder routing (high confidence) | No | — | Keyword matching |
| Folder routing (low confidence) | No — asks user | — | User is the fallback |

**Flow A involves one local LLM call** (phi4-mini synthesis, ~10s). Use `--raw` for zero LLM calls.
**Flow B LLM calls** only fire for proposal generation plus ambiguous classification. Clear cases (majority) require no LLM call.

---

## 9. Configuration Reference

```yaml
# ~/.ctxkit/config.yaml
# ctxkit — Context Portability and Knowledge Ingestion Tool

# ─────────────────────────────
# VAULT
# ─────────────────────────────
vault:
  path: /Users/you/obsidian-vault
  owner_name: ""               # your first name — enables owner-aware query routing
  excluded_folders:
    - noise
  excluded_extensions:
    - .canvas
    - .pdf

# ─────────────────────────────
# INDEXER
# ─────────────────────────────
indexer:
  min_word_count: 50
  min_structure_signals: 1
  manifest_path: ~/.ctxkit/manifest.json
  chunk_size: 512
  chunk_overlap: 64
  max_chunk_words: 400                  # chunks above this are split further
  heading_aware_splitting: true         # split on headings before token count
  preserve_tables: true                 # never split mid-table
  preserve_code_blocks: true            # never split mid-code-block
  heading_levels: [2, 3]               # heading levels used as split boundaries
  batch_size: 32
  metadata_fields:
    - source_file
    - folder_path
    - filename
    - heading_breadcrumb
    - chunk_index
    - chunk_total
    - word_count
    - is_table
    - is_code
    - last_indexed

# ─────────────────────────────
# EMBEDDINGS
# ─────────────────────────────
embeddings:
  backend: local                   # local | openai | gemini
  local_model: nomic-embed-text    # M2 Air default — 0.5GB RAM, 8192 token context, very fast
  # local_model: bge-m3            # desktop default — higher quality, 100+ languages
  api_model: text-embedding-3-small
  api_key: null
  cache_embeddings: true
  cache_path: ~/.ctxkit/embed_cache

# ─────────────────────────────
# VECTOR STORE
# ─────────────────────────────
vector_store:
  backend: chroma
  persist_path: ~/.ctxkit/chroma_db
  collection_name: ctxkit_vault
  distance_metric: cosine          # cosine | l2 | ip

# ─────────────────────────────
# RETRIEVER
# ─────────────────────────────
retriever:
  # Candidate retrieval
  keyword_prefilter: true
  keyword_prefilter_min_score: 0.3      # minimum keyword match signal required
  top_k: 15                             # raw chunks from vector search — increased from 6
  similarity_threshold: 0.65            # minimum similarity score to include

  # Assembly
  context_block_max_words: 1000         # target word budget — increased from 500
  max_chunks_per_source: 2             # max chunks included per source file
  stitch_distance: 2                    # max chunk index gap to stitch together
  stitch_max_words: 400                 # max words in a single stitched passage

  # Signpost list
  signpost_max_items: 8
  signpost_include_section_hints: true  # show heading breadcrumbs in signpost

  # Output
  output_format: markdown               # markdown | plain
  include_word_count: true
  include_timestamp: true
  include_source_paths: true
  include_similarity_scores: false      # debug mode

# ─────────────────────────────
# INGESTER
# ─────────────────────────────
ingester:
  min_summary_word_count: 100
  min_summary_headings: 1
  similarity_threshold_high: 0.82
  similarity_threshold_low: 0.65
  max_candidates_for_llm: 3
  conflict_detection: true
  conflict_similarity_min: 0.70
  conflict_similarity_max: 0.85
  folder_routing_confidence: 0.75

# ─────────────────────────────
# WRITER
# ─────────────────────────────
writer:
  require_approval: true           # non-negotiable, always true
  append_position: end             # end | after_last_heading
  frontmatter:
    inject: true
    fields:
      - tags
      - updated
      - related
    tag_max_count: 8
    related_max_count: 5
  backup:
    enabled: true
    backup_path: ~/.ctxkit/backups
    max_backups_per_file: 5

# ─────────────────────────────
# LLM
# ─────────────────────────────
llm:
  backend: ollama                  # ollama | openai | anthropic | gemini
  model: qwen3.5:4b                # primary model — classify() and propose() (Flow B)
  synthesise_model: phi4-mini      # synthesis model — synthesise() (Flow A, ctxkit search)
                                   # must be non-thinking; phi4-mini recommended
                                   # run: ollama pull phi4-mini
  # model: qwen3:8b               # desktop default (i5 + RTX 4070)
  api_key: null
  temperature: 0.2
  think: false                     # disables thinking mode — passed to Ollama API per call
  max_tokens: 1000
  timeout_seconds: 30
  fallback_backend: null
  fallback_model: null
  fallback_api_key: null

# ─────────────────────────────
# MANIFEST
# ─────────────────────────────
manifest:
  path: ~/.ctxkit/manifest.json
  drift_warning_threshold: 3
  drift_warning_age_hours: 24

# ─────────────────────────────
# CLI
# ─────────────────────────────
cli:
  theme: dark                      # dark | light
  confirm_before_index: true
  show_similarity_scores: false
  verbose: false
  # search output: always written to <vault.path>/ctxkit-output/ — not configurable

# ─────────────────────────────
# LOGGING
# ─────────────────────────────
logging:
  enabled: true
  log_path: ~/.ctxkit/logs
  log_level: INFO                  # DEBUG | INFO | WARNING | ERROR
  max_log_size_mb: 10
  max_log_files: 5
```

---

## 10. Project Structure

```
ctxkit/
│
├── cli/
│   └── commands.py               # Typer commands, Rich rendering
│
├── core/
│   ├── indexer/
│   │   ├── vault_scanner.py
│   │   ├── manifest_manager.py
│   │   ├── document_loader.py
│   │   ├── text_splitter.py
│   │   ├── embedding_engine.py
│   │   └── index_writer.py
│   │
│   ├── retriever/
│   │   ├── keyword_prefilter.py
│   │   ├── vector_searcher.py
│   │   ├── chunk_grouper.py
│   │   ├── chunk_stitcher.py
│   │   ├── source_ranker.py
│   │   ├── context_assembler.py
│   │   └── context_formatter.py
│   │
│   ├── ingester/
│   │   ├── summary_receiver.py
│   │   ├── summary_embedder.py
│   │   ├── classification_engine.py
│   │   ├── folder_router.py
│   │   ├── conflict_detector.py
│   │   └── proposal_generator.py
│   │
│   └── writer/
│       ├── backup_manager.py
│       ├── frontmatter_injector.py
│       ├── file_writer.py
│       └── index_trigger.py
│
├── llm/
│   └── llm_layer.py              # classify() and propose() only
│
├── store/
│   └── vector_store.py           # ChromaDB wrapper, 4 operations
│
├── config/
│   ├── loader.py                 # YAML load + Pydantic validation
│   └── models.py                 # All Pydantic config models
│
├── utils/
│   ├── logging.py
│   └── file_utils.py
│
├── pyproject.toml
├── README.md
└── config.yaml.example
```

---

## 11. Hardware Tiers

| Capability | Minimum (any laptop) | Mid (16GB RAM) | High (GPU / Apple Silicon) |
|---|---|---|---|
| Keyword pre-filter | Yes | Yes | Yes |
| Local embeddings | Slow but works | Comfortable | Fast |
| ChromaDB | Yes | Yes | Yes |
| LLM — ambiguous classification | API key required | Ollama 4–8B | Ollama 8B+ |
| LLM — proposal generation | API key required | Ollama 4–8B | Ollama 8B+ |
| Full local (no API key) | No | Yes (4B models) | Yes (any model) |

**Recommended local models via Ollama:**

| Hardware | `model` | `synthesise_model` | Embedding | Notes |
|---|---|---|---|---|
| Apple M2 Air 16GB | `qwen3.5:4b` | `phi4-mini` | `nomic-embed-text` | think=false required for qwen3 |
| i5 + RTX 4070 (12GB VRAM) | `qwen3:8b` | `phi4-mini` | `bge-m3` | Higher quality classification |
| Low-end / no GPU | `gpt-4o-mini` | *(leave blank)* | `text-embedding-3-small` | API key required |
| Low-end / no GPU | `claude-haiku-4-5` | *(leave blank)* | `text-embedding-3-small` | API key required |

---

## 12. What ctxkit Is Not

- Not a chatbot
- Not an API wrapper around your subscription LLMs
- Not a replacement for Claude, ChatGPT, or Gemini
- Not a note-taking application
- Not a general purpose RAG agent
- Not a always-on background service
- Not a tool that writes anything without your explicit approval
- Not dependent on any specific LLM subscription or provider

---

*ctxkit — Context Portability and Knowledge Ingestion Tool*
*Architecture Blueprint v1.1.0*
