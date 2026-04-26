# mdcore - Markdown CORE AI

**Classification, Organisation, Retrieval & Entry for your personal markdown knowledge base**

**Version:** 1.0.0 | **PyPI:** `markdowncore-ai` | **CLI:** `mdcore`

---

## What It Does

`mdcore` is a local, LLM-agnostic knowledge base engine for anyone with a folder of markdown notes. It does two things:

**Flow A - Retrieval:** Given a topic, it retrieves relevant chunks from your vault, synthesises them into a coherent cited briefing, and writes the result to `<vault>/mdcore-output/`. Copy and paste into any LLM conversation as context. Zero calls to your subscription LLM.

**Flow B - Ingestion:** Given any document - an LLM session summary, a research note, an article, a strategy doc, or any new piece of knowledge - it classifies the content against your existing vault, decides whether to update an existing note or create a new one, routes it to the right folder, detects conflicts, generates a proposal, and only after your explicit approval writes the changes and reindexes automatically.

---

---

## Documentation

- **[Getting Started](docs/getting-started.md)** - installation, first index, first search, first ingest, daily workflow
- **[Config Reference](docs/config-reference.md)** - every config field documented with defaults, valid values, and tuning guidance
- **[Architecture](docs/architecture.md)** - component design and data flow
- **[Retrieval & Eval Guide](docs/retrieval-and-eval-guide.md)** - symptom-to-fix guide for tuning retrieval quality

---

## Installation

### Any platform (uv - recommended)

```bash
uv tool install markdowncore-ai
```

### Any platform (pipx)

```bash
pipx install markdowncore-ai
```

### Ollama models (for local inference)

```bash
ollama pull nomic-embed-text   # embeddings
ollama pull qwen3.5:4b         # primary LLM - classification + proposals
ollama pull phi4-mini          # synthesis - fast, non-thinking
```

### After install

```bash
mdcore init           # interactive setup wizard
mdcore deps install   # install any backend packages not yet present
mdcore index          # index your vault
```

---

## Commands

```bash
mdcore init                           # Interactive setup wizard - create config
mdcore index                          # Scan vault, show diff, confirm, index delta
mdcore index --force                  # Wipe and reindex from scratch
mdcore search <topic>                 # Synthesise briefing -> write to <vault>/mdcore-output/ (Flow A)
mdcore search <topic> --raw           # Raw excerpts only - skip synthesis
mdcore search <topic> --verbose       # Show chunk scores alongside results
mdcore ingest                         # Paste any document - classify, route, propose (Flow B)
mdcore ingest --file doc.md           # Ingest from a file (session summary, article, notes, etc.)
mdcore map                            # Generate vault folder map for doc routing
mdcore map --repair                   # Remove stale folder descriptions from map
mdcore status                         # Show index health and drift warnings
mdcore eval [topic]                   # Run quality evaluation checklist
mdcore config                         # Open config file in editor
mdcore config --validate              # Validate config and report errors
```

### Multiple config profiles

```bash
mdcore search "istio auth" --config ~/.mdcore/config-technical.yaml
mdcore search "career goals" --config ~/.mdcore/config-personal.yaml
```

---

## Quick Start

```bash
# 1. Configure (interactive wizard)
mdcore init
# -> asks for vault path, owner name, LLM backend, models
# -> detects Ollama + pulled models, gives hardware-appropriate suggestions
# -> writes ~/.mdcore/config.yaml

# 2. Index your vault
mdcore index

# 3. Retrieve context for an LLM conversation
mdcore search "kubernetes ingress routing"
# -> writes <vault>/mdcore-output/2026-04-26-kubernetes-ingress-routing.md
# -> open file, copy contents -> paste into Claude/ChatGPT/Gemini

# 4. Ingest any document into your vault
mdcore ingest --file my-session-summary.md   # LLM session summary
mdcore ingest --file oss-strategy.md         # standalone research doc
mdcore ingest                                # paste content directly
# -> mdcore classifies, routes to right folder, proposes changes -> approve
```

---

## Architecture

```
YOUR MARKDOWN VAULT (any folder of .md files)
        |
        v
   mdcore core
   +----------+  +----------+  +------------+
   | Indexer  |  |Retriever |  |  Ingester  |
   +----------+  +----------+  +------------+
   +----------+  +----------+  +------------+
   |  Writer  |  |LLM Layer |  |VectorStore |
   +----------+  +----------+  +------------+
        |
   (copy-paste by user)
        |
        v
ANY SUBSCRIPTION LLM (Claude / ChatGPT / Gemini / Others)
```

mdcore never talks to your subscription LLM directly. It prepares context (Flow A) and processes output from it (Flow B). The user is always the bridge.

---

## Where LLM Calls Happen

Every call goes to your configured `llm.model` (or `synthesise_model` where noted). Token usage logged at INFO level to `~/.mdcore/logs/mdcore.log` after every call.

### Flow A - `mdcore search <topic>`

| Phase | LLM call? | Model used | Notes |
|---|---|---|---|
| Keyword pre-filter | No | - | BM25 scoring, no LLM |
| Vector search | No | - | Embedding lookup only |
| Chunk stitching + formatting | No | - | Pure text assembly |
| **Synthesis** | **Yes** | `synthesise_model` | Reformats raw excerpts into a briefing. Skip with `--raw` |

`mdcore search <topic> --raw` makes Flow A fully LLM-free.

### Flow B - `mdcore ingest`

| Phase | LLM call? | Model used | Condition |
|---|---|---|---|
| Embedding + vector search | No | - | Always |
| **Classification** | **Conditional** | `llm.model` | Only when similarity score is between `similarity_threshold_low` and `similarity_threshold_high` |
| **Folder routing** | **Yes (NEW only)** | `llm.model` | When action=NEW, LLM picks target folder from semantic candidate list |
| **Proposal generation** | **Yes** | `llm.model` | Always - generates human-readable summary before approval |

### `mdcore map` / `mdcore index`

No LLM calls.

---

## Observability

Token usage logged after every call:
```
INFO llm - tokens [gemini-2.5-flash-lite] in=312 out=89 total=401
```

Optional LangSmith tracing - add to `~/.mdcore/config.yaml`:
```yaml
llm:
  langsmith_api_key: <your-key>
  langsmith_project: mdcore
```
Traces every LLM call at `smith.langchain.com` with full prompt, response, latency, and token counts.

---

## Configuration Reference

See `config.yaml.example` for the full annotated config. Key sections:

| Section | Key fields | Purpose |
|---|---|---|
| `vault` | `path`, `owner_name` | Vault root path, owner identity for multi-person vaults |
| `indexer` | `chunk_size`, `heading_levels` | Chunking strategy and quality filters |
| `embeddings` | `backend`, `local_model` | Local (Ollama) or API-backed embeddings |
| `retriever` | `top_k`, `similarity_threshold` | Candidate retrieval, assembly, signposting |
| `ingester` | `similarity_threshold_high/low` | Classification thresholds, conflict detection |
| `writer` | `append_position`, `backup` | Append position, frontmatter injection, backups |
| `llm` | `model`, `synthesise_model` | Primary LLM (classify/propose) + synthesis model (search) |
| `cli` | `theme`, `verbose` | Terminal UI behaviour |

---

## Hardware Tiers

| Hardware | LLM Model | Embedding Model |
|---|---|---|
| Apple M2 Air 16GB | `qwen3.5:4b` | `nomic-embed-text` |
| i5 + RTX 4070 | `qwen3:8b` | `bge-m3` |
| Low-end / no GPU | `gpt-4o-mini` / `claude-haiku-4-5` | `text-embedding-3-small` |

---

## Project Structure

```
mdcore/
+-- cli/commands.py              # Typer commands, Rich rendering
+-- core/
|   +-- indexer/                 # VaultScanner, ManifestManager, TextSplitter, ...
|   +-- retriever/               # KeywordPreFilter, VectorSearcher, ChunkStitcher, ...
|   +-- ingester/                # ClassificationEngine, ConflictDetector, FolderRouter, ...
|   +-- writer/                  # BackupManager, FrontmatterInjector, FileWriter, ...
+-- llm/llm_layer.py             # classify(), propose(), synthesise(), route_folder()
+-- store/vector_store.py        # ChromaDB wrapper
+-- config/                      # Pydantic models + YAML loader
+-- utils/                       # Logging, file utilities
```

---

## What mdcore Is Not

- Not a chatbot or RAG question-answering agent
- Not an API wrapper around subscription LLMs
- Not a note-taking application
- Not an always-on background service
- **Never writes anything without your explicit approval**

---

*mdcore - Markdown CORE AI v1.0.0*
