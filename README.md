# ctxkit — Context Portability and Knowledge Ingestion Tool

**Version:** 1.3.0 | **Status:** Implementation

A local, LLM-agnostic context delivery and knowledge sync tool for users who live across multiple subscription LLMs.

---

## What It Does

`ctxkit` sits between your personal markdown knowledge base and whichever subscription LLM you are using at any given moment (Claude, ChatGPT, Gemini, or any other). It does two things:

**Flow A — Context Retrieval:** Given a topic, it retrieves relevant chunks from your vault, synthesises them into a coherent, cited briefing (using a local LLM), and writes the result to `<vault>/ctxkit-output/`. You open the file, copy it, and paste it as the opening context of your LLM conversation. Zero API calls to your subscription LLM. Zero cost beyond your existing subscription.

**Flow B — Knowledge Ingestion:** Given any document — a session summary from an LLM conversation, a research note, an article, a strategy doc, or any new piece of knowledge — it classifies the content against your existing vault, decides whether to update an existing note or create a new one, routes it to the right folder, detects conflicts, generates a proposal, and — only after your explicit approval — writes the changes to your vault and reindexes automatically.

---

## Documentation

- **[Getting Started](docs/getting-started.md)** — installation, first index, first search, first ingest, daily workflow
- **[Config Reference](docs/config-reference.md)** — every config field documented with defaults, valid values, and tuning guidance
- **[Architecture](docs/architecture.md)** — component design and data flow
- **[Retrieval & Eval Guide](docs/retrieval-and-eval-guide.md)** — symptom-to-fix guide for tuning retrieval quality

---

## Installation

### macOS — Homebrew

```bash
brew tap piyush-tyagi-13/ctxkit
brew install ctxkit
```

### Any platform — shell script (installs uv + ctxkit)

```bash
curl -fsSL https://raw.githubusercontent.com/piyush-tyagi-13/context-portability-tool/master/install/install.sh | bash
```

### Manual (if you already have uv or pipx)

```bash
uv tool install ctxkit-ai       # preferred
# or
pipx install ctxkit-ai
```

### Ollama models (for local inference)

```bash
ollama pull nomic-embed-text   # embeddings
ollama pull qwen3.5:4b         # primary LLM — classification + proposals
ollama pull phi4-mini          # synthesis — fast, non-thinking
```

### After install

```bash
ctxkit init       # interactive setup wizard
ctxkit deps install   # install any backend packages not yet present
ctxkit index      # index your vault
```

---

## Commands

```bash
ctxkit init                           # Interactive setup wizard — create config
ctxkit index                          # Scan vault, show diff, confirm, index delta
ctxkit search <topic>                 # Synthesise briefing → write to <vault>/ctxkit-output/ (Flow A)
ctxkit search <topic> --raw           # Raw excerpts only — skip synthesis
ctxkit search <topic> --verbose       # Show chunk scores alongside results
ctxkit ingest                         # Paste any document — classify, route, propose (Flow B)
ctxkit ingest --file doc.md           # Ingest from a file (session summary, article, notes, etc.)
ctxkit map                            # Generate vault folder map for doc routing
ctxkit status                         # Show index health and drift warnings
ctxkit eval [topic]                   # Run quality evaluation checklist
ctxkit config                         # Open config file in editor
ctxkit config --validate              # Validate config and report errors
```

### Multiple config profiles

```bash
ctxkit search "istio auth" --config ~/.ctxkit/config-technical.yaml
ctxkit search "career goals" --config ~/.ctxkit/config-personal.yaml
```

---

## Quick Start

```bash
# 1. Configure (interactive wizard)
ctxkit init
# → asks for vault path, owner name, LLM backend, models
# → detects Ollama + pulled models, gives hardware-appropriate suggestions
# → writes ~/.ctxkit/config.yaml

# 2. Index your vault
ctxkit index

# 3. Retrieve context for an LLM conversation
ctxkit search "Bruno ingress path adaptor"
# → writes <vault>/ctxkit-output/2026-04-25-bruno-ingress-path-adaptor.md
# → open file, copy contents → paste into Claude/ChatGPT/Gemini

# 4. Ingest any document into your vault
ctxkit ingest --file my-session-summary.md   # LLM session summary
ctxkit ingest --file oss-strategy.md         # standalone research doc
ctxkit ingest                                # paste content directly
# → ctxkit classifies, routes to right folder, proposes changes → approve
```

---

## Architecture

```
YOUR MARKDOWN VAULT
        │
        ▼
   ctxkit core
   ┌──────────┐  ┌──────────┐  ┌────────────┐
   │ Indexer  │  │Retriever │  │  Ingester  │
   └──────────┘  └──────────┘  └────────────┘
   ┌──────────┐  ┌──────────┐  ┌────────────┐
   │  Writer  │  │LLM Layer │  │VectorStore │
   └──────────┘  └──────────┘  └────────────┘
        │
   (copy-paste by user)
        │
        ▼
ANY SUBSCRIPTION LLM (Claude · ChatGPT · Gemini · Others)
```

ctxkit never talks to your subscription LLM directly. It prepares context (Flow A) and processes output from it (Flow B). The user is the bridge.

**LLM calls in Flow A (retrieval):** one local call to `synthesise_model` (default: `phi4-mini` via Ollama) to reformat raw excerpts into a coherent briefing. No calls to your subscription LLM. Skip with `--raw` to make Flow A fully LLM-free.

**LLM calls in Flow B (ingestion):** only when classification is ambiguous (score between low and high thresholds). Clear-match updates and clear new-file cases require no LLM call.

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
ctxkit/
├── cli/commands.py              # Typer commands, Rich rendering
├── core/
│   ├── indexer/                 # VaultScanner, ManifestManager, TextSplitter, ...
│   ├── retriever/               # KeywordPreFilter, VectorSearcher, ChunkStitcher, ...
│   ├── ingester/                # ClassificationEngine, ConflictDetector, ...
│   └── writer/                  # BackupManager, FrontmatterInjector, FileWriter, ...
├── llm/llm_layer.py             # classify() and propose() — single LLM abstraction
├── store/vector_store.py        # ChromaDB wrapper — 4 operations
├── config/                      # Pydantic models + YAML loader
└── utils/                       # Logging, file utilities
```

---

## What ctxkit Is Not

- Not a chatbot or RAG question-answering agent
- Not an API wrapper around subscription LLMs
- Not a note-taking application
- Not an always-on background service
- **Never writes anything without your explicit approval**

---

*ctxkit — Context Portability and Knowledge Ingestion Tool v1.3.0*
