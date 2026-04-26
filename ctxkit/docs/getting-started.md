# Getting Started with ctxkit

**Context Portability and Knowledge Ingestion Tool**

This guide takes you from zero to your first working retrieval and ingestion session.

---

## What you'll have at the end

- ctxkit installed and pointing at your markdown vault
- Your vault indexed and searchable
- A context package retrieved and ready to paste into Claude, ChatGPT, or Gemini
- A session summary ingested back into your vault

---

## Prerequisites

### Python 3.11+

```bash
python3 --version   # must be 3.11 or higher
```

### Ollama (for local embeddings and LLM)

Install from [ollama.com](https://ollama.com), then pull the required models:

```bash
ollama pull nomic-embed-text   # embedding model (~274MB)
ollama pull qwen3.5:4b         # primary LLM — classification + proposals (~2.6GB)
ollama pull phi4-mini          # synthesis model — fast, non-thinking (~2.5GB)
```

> **No GPU? No Ollama?** You can use API-backed embeddings and LLM instead. See the [Config Reference](config-reference.md#embeddings) for OpenAI and Anthropic options. You'll need API keys but no local models.

---

## Step 1 — Install ctxkit

Clone the repo and install into a virtual environment:

```bash
git clone <repo-url>
cd context-portability-tool

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e .
```

Confirm it's working:

```bash
ctxkit --help
```

You should see all six commands listed.

---

## Step 2 — Run the setup wizard

```bash
ctxkit init
```

The wizard asks for the commonly changed settings and gives hardware-aware suggestions:

```
ctxkit init — setup wizard

Detecting Ollama… found  (3 models pulled)
  qwen3.5:4b, phi4-mini, nomic-embed-text
Hardware: Apple Silicon

── Vault ──────────────────────────────────────
Vault path [~/Documents]: /Users/you/your-vault
Owner name (blank for single-person vault) []: Piyush

── LLM backend ────────────────────────────────
  [1] ollama — local, no API cost  [suggested]
  [2] openai — OpenAI API
  [3] anthropic — Anthropic API
  [4] gemini — Google Gemini API
Backend [1]:

── Models ─────────────────────────────────────
Primary model [qwen3.5:4b]:
Synthesis model [phi4-mini]:
Embedding model [nomic-embed-text]:

✓ Config written → ~/.ctxkit/config.yaml

Next steps:
  ctxkit config --validate
  ctxkit index
```

Config is written to `~/.ctxkit/config.yaml`. To edit it later: `ctxkit config`. To validate: `ctxkit config --validate`.

---

## Step 3 — Start Ollama

Ollama must be running before you index or search:

```bash
ollama serve
```

Leave this running in a separate terminal, or set it up as a background service. You can verify it's up:

```bash
curl http://localhost:11434
# → "Ollama is running"
```

---

## Step 4 — Index your vault

```bash
ctxkit index
```

ctxkit will:

1. Scan your vault for eligible markdown files (skipping noise folder, short files, structureless files)
2. Show you a diff of what will be indexed — new, modified, and deleted files
3. Ask for confirmation before touching anything
4. Embed and store every chunk in the local ChromaDB vector store
5. Update the index manifest

**First run on a large vault** (500+ files) will take a few minutes depending on your hardware. Subsequent runs only process files that changed since the last index.

```
┌─────────────────────────────┐
│ Index Delta                 │
├────────────┬────────────────┤
│ [+] New    │ 47 files       │
│ [~] Modified│ 0 files       │
│ [-] Deleted │ 0 files       │
└────────────┴────────────────┘

[A]ll / [C]ancel: A
✓ 47 files indexed in 38.2s
```

**Inspect how a specific file was chunked:**

```bash
ctxkit index --inspect "Istio Details.md"
```

This shows every chunk, its heading breadcrumb, word count, and whether it's a table or code block. Use this when retrieval results feel off.

---

## Step 5 — Retrieve context (Flow A)

This is the core daily workflow. Before starting an LLM conversation, run a search:

```bash
ctxkit search "Bruno ingress path adaptor"
```

ctxkit retrieves the most relevant chunks from your vault, synthesises them into a coherent briefing using the configured `synthesise_model`, and **writes the result to a markdown file inside your vault**:

```
✓ Saved → /your/vault/ctxkit-output/2026-04-25-bruno-ingress-path-adaptor.md  (1 source · synthesised)
```

Output always goes to `<vault.path>/ctxkit-output/`. This folder is created automatically and is always excluded from indexing — ctxkit will never retrieve its own output as vault context.

Open that file — it contains a structured, cited briefing ready to paste into your LLM conversation:

```markdown
# Bruno ingress path adaptor

*2026-04-25 09:14 UTC · 1 source · synthesised by phi4-mini*

> ⚠ Verify claims against raw excerpts below.

## Briefing

Your Gateway Setup has a dedicated `istio-gateway` namespace containing three
gateway pods ... [1]

---

## Raw Excerpts

### [1] Lloyds Related / Istio Details.md
*Sections: Your Gateway Setup · The Two Ingress Paths > Path 1 — Bruno*

...raw text...

---

## Also available — fetch if the LLM needs to go deeper

| Source | Relevant sections | Suggested query |
|---|---|---|
| Lloyds Related / Istio Details.md | CRDs — VirtualService | `ctxkit search "Istio VirtualService DestinationRule"` |
```

**Copy the entire file content and paste it at the start of your LLM conversation.** The subscription LLM never needs to know ctxkit exists — from its perspective you've simply arrived well-prepared.

### Raw mode

If you want the unprocessed excerpts without LLM synthesis (faster, no model needed):

```bash
ctxkit search "topic" --raw
```

Output still writes to a file, but the briefing section is omitted — just the numbered raw excerpts.

### Tips for better search results

- **Be specific.** `"Bruno VPN ILB private IP ingress"` beats `"networking"`.
- **Include domain terms.** Words that appear in your file titles and headings carry extra weight via the keyword pre-filter.
- **Broad orientation queries** work too — add "overview" or "complete" to signal you want multi-section coverage: `"Istio GCP overview complete"`.
- **Owner-qualified queries** work if `vault.owner_name` is set — `"piyush career"` fetches your career notes even if another person's career folder exists in the vault.
- **Tune with `--verbose`** to see individual chunk scores if results look wrong: `ctxkit search "topic" --verbose`

---

## Step 6 — Ingest a session summary (Flow B)

After a meaningful LLM conversation, run this prompt inside your LLM session to generate a structured summary:

```
Please write a session summary for my knowledge base. Format it as markdown with:
- A clear ## heading for the topic
- Subsections covering key decisions, new concepts, and any revised positions
- At least 150 words
- No conversational filler — just the knowledge
```

Save the LLM's response to a file, then run:

```bash
ctxkit ingest --file ~/Desktop/session-summary.md
```

Or paste directly into the terminal:

```bash
ctxkit ingest
# → paste your summary, then Ctrl+D
```

ctxkit will:

1. Validate the summary has enough structure and length
2. Compare it against your indexed knowledge base
3. Decide whether it belongs as an update to an existing file or a new file
4. Detect any conflicting claims against existing content
5. Generate a proposal and show it to you

```
╭─ ctxkit proposal ──────────────────────────────╮
│ PROPOSAL — ctxkit ingestion                    │
│ ─────────────────────────────────────────────  │
│ Action:     UPDATE existing file               │
│ Target:     Career/EM-transition.md            │
│ Confidence: 0.91                               │
│                                                │
│ Changes proposed:                              │
│   • Add new section on Principal Engineer path │
│   • Update career goals to reflect shift away  │
│     from EM track toward Staff/Principal       │
│                                                │
│ Possible conflicts detected:                   │
│   ! Existing:  "Targeting EM roles at product" │
│     Incoming:  "Shifting toward Principal Eng" │
│     → Review before approving (sim: 0.78)      │
│ ─────────────────────────────────────────────  │
╰────────────────────────────────────────────────╯

[A]pprove / [E]dit first / [R]eject:
```

- **[A]pprove** — writes the change, backs up the current file, updates frontmatter, reindexes immediately
- **[E]dit** — redirects you to edit the summary first, then re-run ingest
- **[R]eject** — exits cleanly, nothing is touched

---

## Step 7 — Check index health

```bash
ctxkit status
```

```
┌──────────────────┬────────────────────────────────┐
│ Vault path       │ /Users/you/obsidian-vault       │
│ Eligible files   │ 47                              │
│ Indexed files    │ 47                              │
│ Total chunks     │ 312                             │
│ New (unindexed)  │ 0                               │
│ Modified (stale) │ 3                               │
│ Deleted          │ 0                               │
└──────────────────┴────────────────────────────────┘

⚠ Index drift detected: 3 file(s) out of sync. Run ctxkit index to update.
```

Run `ctxkit index` after any significant vault editing session. A stale index silently returns stale context — the most common cause of gradual quality degradation.

---

## Step 8 — Evaluate output quality

If retrieval results feel off, use the built-in quality checker:

```bash
ctxkit eval "your topic"
```

This runs the search and then displays a four-question evaluation checklist with a link to the symptom-to-fix guide. See `ctxkit-retrieval-and-eval-guide.md` for the full guide covering every symptom and which config parameter fixes it.

---

## Daily workflow summary

```
Morning: ctxkit status              # check for drift
         ctxkit index               # if drift detected

Before LLM session:
         ctxkit search "topic"      # → writes <vault>/ctxkit-output/YYYY-MM-DD-<slug>.md
                                    # open file, copy contents → paste into LLM

         ctxkit search "topic" --raw   # skip synthesis — raw excerpts only

After LLM session:
         ctxkit ingest --file summary.md   # approve → done
```

---

## Hardware notes

| Setup | Recommended config |
|---|---|
| Apple M2 Air 16GB | `backend: ollama`, `model: qwen3.5:4b`, `local_model: nomic-embed-text` |
| Desktop with GPU (RTX 4070) | `backend: ollama`, `model: qwen3:8b`, `local_model: bge-m3` |
| No GPU / any laptop | `backend: openai/anthropic`, `local_model: text-embedding-3-small` (API key required) |
| No GPU, no API key | `backend: huggingface`, `local_model: all-MiniLM-L6-v2` (CPU-only, slower) |

---

## Troubleshooting

**`Config file not found`**
→ Run `cp config.yaml.example ~/.ctxkit/config.yaml` and set `vault.path`.

**`Index is empty. Run ctxkit index first.`**
→ Run `ctxkit index`.

**`connection refused` on first search**
→ Ollama isn't running. Run `ollama serve` in a separate terminal.

**Results are off after editing your vault**
→ Run `ctxkit index` to pick up the changes. The manifest tracks file modification times.

**Short results (under 600 words)**
→ Lower `retriever.similarity_threshold` (default `0.65`, try `0.50` or `0.40`) in your config. See [Config Reference](config-reference.md#retriever).

**Wrong sources appearing**
→ Enable `retriever.keyword_prefilter: true` and raise `retriever.keyword_prefilter_min_score` to `0.5`.
