# ctxkit — Retrieval Design and Quality Evaluation Guide
**Context Assembly, Output Format, and User-Driven Quality Tuning**

Version: 1.0.0 | Last Updated: April 2026 | Applies to: ctxkit v1.0.0

---

## Table of Contents

1. [What ctxkit Retrieval Actually Is](#1-what-ctxkit-retrieval-actually-is)
2. [Retrieval Design](#2-retrieval-design)
   - 2.1 [The Retrieval Pipeline](#21-the-retrieval-pipeline)
   - 2.2 [Chunk Stitching](#22-chunk-stitching)
   - 2.3 [Output Assembly](#23-output-assembly)
3. [Output Format](#3-output-format)
   - 3.1 [Context Block Structure](#31-context-block-structure)
   - 3.2 [Source Citations](#32-source-citations)
   - 3.3 [Breadcrumb Metadata](#33-breadcrumb-metadata)
4. [Chunking Strategy](#4-chunking-strategy)
   - 4.1 [Why Chunking Matters for This Design](#41-why-chunking-matters-for-this-design)
   - 4.2 [Chunking Rules for ctxkit](#42-chunking-rules-for-ctxkit)
   - 4.3 [Metadata Every Chunk Must Carry](#43-metadata-every-chunk-must-carry)
5. [User-Driven Quality Evaluation](#5-user-driven-quality-evaluation)
   - 5.1 [Philosophy](#51-philosophy)
   - 5.2 [How to Evaluate a Context Block](#52-how-to-evaluate-a-context-block)
   - 5.3 [The Symptom-to-Fix Guide](#53-the-symptom-to-fix-guide)
6. [Configuration Parameters That Affect Output Quality](#6-configuration-parameters-that-affect-output-quality)
7. [Updated Config Reference](#7-updated-config-reference)
8. [Real Example — Istio Details.md](#8-real-example--istio-detailsmd)

---

## 1. What ctxkit Retrieval Actually Is

ctxkit is not a RAG question-answering agent. This distinction is fundamental to every design decision in this document.

A RAG agent answers your question using your knowledge base. You ask, the agent retrieves, the LLM reasons, you get an answer. You never see the retrieval step.

ctxkit is a context packager. You ask, ctxkit retrieves and assembles everything relevant from your vault, and you carry that assembled context into a subscription LLM conversation yourself. The subscription LLM does the reasoning. ctxkit does the knowledge delivery.

This means the output of `ctxkit search` is not an answer. It is a structured, cited, up-to-1000-word package of everything in your vault that is relevant to your query — ready to paste into Claude, ChatGPT, or Gemini as the opening context block of a conversation.

The subscription LLM never needs to know ctxkit exists. From its perspective, you have simply arrived well-prepared.

---

## 2. Retrieval Design

### 2.1 The Retrieval Pipeline

```
ctxkit search "Bruno ingress path adaptor"
         │
         ▼
KeywordPreFilter
  — keyword match against file titles and folder paths in index metadata
  — narrows candidate pool before vector search
  — pure string matching, milliseconds, no ML
         │
         ▼
VectorSearcher
  — embeds the query using the configured embedding model
  — cosine similarity search against ChromaDB
  — returns top K=15 chunks with similarity scores
  — K=15 (not 6) to ensure enough raw material for 1000-word assembly
         │
         ▼
ChunkGrouper
  — groups retrieved chunks by source file
  — within each source file, sorts chunks by their position in the document
    (chunk_index metadata field)
  — preserves document reading order within each source
         │
         ▼
ChunkStitcher
  — within each source file group, detects adjacent or near-adjacent chunks
  — stitches them into coherent passages rather than disconnected fragments
  — see section 2.2 for stitching rules
         │
         ▼
SourceRanker
  — ranks source files by aggregate relevance score
  — aggregate score = weighted sum of individual chunk similarity scores
    within that source, normalised by chunk count
  — highest ranked source appears first in the output
         │
         ▼
ContextAssembler
  — assembles output from ranked sources
  — fills up to the configured word budget (default 1000 words)
  — sources that do not fit within budget go into the signpost list
  — attaches breadcrumb metadata to each passage
         │
         ▼
ContextFormatter
  — renders the assembled context as a structured markdown block
  — includes source citations, breadcrumbs, word count, signpost list
  — outputs to terminal via Rich
         │
    User copies and pastes into subscription LLM
```

---

### 2.2 Chunk Stitching

Chunk stitching is the step that makes ctxkit output feel like extracted knowledge rather than search result fragments. Without stitching, a query about "Bruno ingress path" might return three disconnected chunks from Istio Details.md that make no sense individually. With stitching, those chunks are assembled into the coherent passage they came from.

**Stitching rules:**

Two chunks from the same source file are stitched together if their `chunk_index` values are adjacent (index N and index N+1) or near-adjacent (index N and index N+2, with one intervening chunk).

Near-adjacent stitching includes the intervening chunk even if it did not score highly in retrieval — because dropping it would create a jarring discontinuity in the assembled text.

Stitched passages are treated as a single unit for word count and source attribution purposes.

**Stitching does not happen across source files.** Each source file produces its own passage block, cited separately.

**Stitching limit:** A single stitched passage is capped at 400 words. Beyond this, the passage is split and the second half is moved to the signpost list. This prevents a single large document from consuming the entire context budget.

---

### 2.3 Output Assembly

Assembly fills the context block up to the word budget in source rank order:

```
word_budget = config.retriever.context_block_max_words  # default 1000

for each source in ranked_sources:
    if passage.word_count fits within remaining budget:
        include passage in primary context
        subtract from remaining budget
    else if remaining budget > 100 words:
        truncate passage to fit, append "..." and signpost note
        break
    else:
        add source to signpost list with section hints
```

Sources in the signpost list are listed with their most relevant section headings (from chunk breadcrumb metadata) and a suggested follow-up query, so the subscription LLM can ask you to fetch them if needed.

---

## 3. Output Format

### 3.1 Context Block Structure

```markdown
## Context package: [your query]
*Assembled by ctxkit · [N] sources · [word count] words · [timestamp]*

---

### [1] [Folder path / Filename]
*Sections: [heading breadcrumbs of included chunks]*

[Assembled passage text — coherent, stitched, cited inline]

---

### [2] [Folder path / Filename]
*Sections: [heading breadcrumbs of included chunks]*

[Assembled passage text]

---

## Also available — fetch if the LLM needs to go deeper

| Source | Relevant sections | Suggested query |
|---|---|---|
| Lloyds Related / Istio Details.md | CRDs section, Egress Path | `ctxkit search "Istio CRDs AuthorizationPolicy"` |
| Lloyds Related / CMAS-CBS Integration / Health / health-readiness-contract.md | Readiness contract | `ctxkit search "readiness contract CBS"` |

---
*Paste this block at the start of your LLM conversation as opening context.*
*The LLM can ask you to run any of the suggested queries above to fetch deeper context.*
```

---

### 3.2 Source Citations

Every passage in the context block is attributed to its source file using the full vault-relative path. This serves two purposes:

The subscription LLM knows exactly where the information came from and can reference it in its responses ("according to your health-check-design-guide...").

You can open the source file directly if you need to verify or expand on anything the LLM raises.

Citations use the full relative path from vault root, not just the filename. This matters when multiple files share similar names across different folders.

---

### 3.3 Breadcrumb Metadata

Every chunk stored in ChromaDB carries heading breadcrumb metadata captured at index time:

```
source_file: Lloyds Related/Istio Details.md
folder_path: Lloyds Related
filename: Istio Details.md
heading_breadcrumb: "The Two Ingress Paths into Your Adaptor > Path 1 — Bruno (dev testing)"
chunk_index: 6
word_count: 187
last_indexed: 2026-04-20T14:32:00
```

The `heading_breadcrumb` is constructed by the TextSplitter at index time. When a chunk is split, the splitter walks back through the document structure to find the nearest parent heading(s) and records them as the breadcrumb. This requires heading-aware splitting — not pure token-count splitting.

This breadcrumb is what enables the context block to show "Sections: The Two Ingress Paths > Path 1 — Bruno" rather than just the filename, giving the subscription LLM precise structural context.

---

## 4. Chunking Strategy

### 4.1 Why Chunking Matters for This Design

The context packager design places more demand on chunking quality than a typical RAG agent because:

Multiple chunks from the same file will appear in the same output. If chunks are incoherent fragments, stitching cannot recover them.

Breadcrumb metadata must be accurate. If the splitter loses track of heading structure, breadcrumbs are wrong, and the subscription LLM receives misleading source attribution.

The word budget is a hard limit. Chunks that are too large consume the budget prematurely. Chunks that are too small produce fragmented output that does not reach the budget.

A file like Istio Details.md — 1,500 words covering 9 distinct sections — is a concrete stress test of all three concerns.

---

### 4.2 Chunking Rules for ctxkit

**Split on headings first, token count second.**

The primary split boundary is a markdown heading (`##` or `###`). Each heading section becomes a candidate chunk. If a heading section exceeds the maximum chunk size, it is then split by token count with overlap. If a heading section is below the minimum chunk size, it is merged with the next sibling section under the same parent heading.

This means the Istio Details CRD section — which is long — gets split into multiple chunks, all carrying the same `CRDs — The Configuration Language` breadcrumb. The Bruno ingress section — which is self-contained — becomes a single chunk with its own breadcrumb.

**Chunk size targets:**

| Parameter | Default | Notes |
|---|---|---|
| `chunk_size` | 512 tokens | Target size for token-count splits within a section |
| `chunk_overlap` | 64 tokens | Overlap between token-count splits within a section |
| `min_chunk_words` | 50 words | Sections below this are merged with next sibling |
| `max_chunk_words` | 400 words | Sections above this are split by token count |

**Tables are kept intact.** A markdown table is never split mid-table. If a table would exceed the chunk size, it is kept as a single oversized chunk rather than split. The summary table in Istio Details.md is a good example — splitting it would make both halves meaningless.

**Code blocks are kept intact** on the same principle.

---

### 4.3 Metadata Every Chunk Must Carry

The TextSplitter and IndexWriter must store the following per chunk. These fields drive stitching, breadcrumbs, and the signpost list:

```python
{
    "source_file": "Lloyds Related/Istio Details.md",      # vault-relative path
    "folder_path": "Lloyds Related",                        # parent folder(s)
    "filename": "Istio Details.md",                         # file title
    "heading_breadcrumb": "The Two Ingress Paths > Path 1", # heading chain
    "chunk_index": 6,                                        # position in document
    "chunk_total": 11,                                       # total chunks in file
    "word_count": 187,                                       # words in this chunk
    "is_table": False,                                       # table flag
    "is_code": False,                                        # code block flag
    "last_indexed": "2026-04-20T14:32:00"                   # index timestamp
}
```

---

## 5. User-Driven Quality Evaluation

### 5.1 Philosophy

Automated RAG evaluation frameworks (RAGAS, TruLens, DeepEval) are designed for systems where an LLM answers questions and you measure faithfulness and relevance of the answer. ctxkit is not that system. The output is a context block for human review, not an LLM-generated answer.

The right evaluation model for ctxkit is therefore user-driven. You run a search, you read the context block, and you judge whether it would have saved you the 10 minutes of manual context-setting you currently spend at the start of every LLM conversation.

That judgment — yes this is good enough / no this is missing something / no this is the wrong content — is the ground truth. No automated metric can substitute for it.

What ctxkit provides to support this judgment is a structured symptom-to-fix guide. When the output is not good enough, the guide tells you exactly which configuration parameter to adjust and in which direction.

---

### 5.2 How to Evaluate a Context Block

After running `ctxkit search`, ask yourself four questions in order:

**Question 1 — Is the word count close to the target (1000 words)?**

If significantly under target (below 600 words), the vault does not have enough content on this topic, or retrieval is being too conservative. Go to the symptom guide: "Output is too short."

If at or near target (800–1000 words), proceed to question 2.

**Question 2 — Are the right sources cited?**

You should be able to look at the source list and recognise every file as genuinely relevant to your query. If you see files that are clearly unrelated, retrieval is picking up noise. Go to the symptom guide: "Wrong sources appearing."

If all sources look right, proceed to question 3.

**Question 3 — Is the content within each source passage accurate and coherent?**

Read each passage. Does it make sense as extracted text? Does it cover the aspect of the topic you were asking about? If passages feel fragmented, disconnected, or truncated mid-thought, chunking or stitching is the problem. Go to the symptom guide: "Passages feel fragmented."

**Question 4 — Would this context block give a subscription LLM enough to have a useful conversation?**

This is the ultimate test. If you pasted this block into Claude or ChatGPT and started a conversation, would you still need to spend time re-explaining things? If yes, something is missing. Go to the symptom guide: "Context feels incomplete despite good sources."

---

### 5.3 The Symptom-to-Fix Guide

---

#### Symptom: Output is too short — well under 1000 words

**What it means:** ctxkit is not finding enough relevant content, or the word budget is being hit by very few large chunks that consume it quickly.

**Diagnosis steps:**

Run `ctxkit status` and check the chunk count for the files you expected to see. If they have very few chunks (1–2), the files may be getting treated as single large units.

Check whether the expected files appear at all. If they do not, the similarity threshold may be too high and is rejecting valid matches.

**Fixes — try in order:**

Lower `retriever.similarity_threshold` in config from default 0.65 to 0.55. This allows less similar but still relevant content through.

```yaml
retriever:
  similarity_threshold: 0.55   # was 0.65
```

Increase `retriever.top_k` from 15 to 20. More raw candidates means more material to assemble from.

```yaml
retriever:
  top_k: 20   # was 15
```

If specific files you know are relevant never appear, check that they passed the minimum word count filter. Run `ctxkit index --verbose` to see which files were skipped during indexing.

Lower `indexer.min_word_count` from 50 to 30 if you have short but valuable notes.

```yaml
indexer:
  min_word_count: 30   # was 50
```

---

#### Symptom: Output is too long and padded — exceeds 1000 words with irrelevant content

**What it means:** Retrieval is too permissive. Low-relevance content is passing the similarity threshold and getting assembled.

**Fixes — try in order:**

Raise `retriever.similarity_threshold` from 0.65 to 0.72. This tightens the relevance bar.

```yaml
retriever:
  similarity_threshold: 0.72   # was 0.65
```

Reduce `retriever.top_k` from 15 to 10. Fewer candidates means less noise in the assembly pool.

```yaml
retriever:
  top_k: 10   # was 15
```

If a specific folder keeps contributing irrelevant results, add it to `retriever.excluded_folders` or move its contents to the noise folder.

---

#### Symptom: Wrong sources appearing — files that are clearly unrelated to the query

**What it means:** The embedding model is finding surface-level lexical similarity rather than semantic relevance, or your vault has content that shares vocabulary with your query topic without being genuinely related.

**Diagnosis steps:**

Check whether the wrong files share keywords with your query even though they are on a different topic. For example, querying "health check design" might pull in a personal health note if one exists in your vault, because the word "health" appears in both.

**Fixes — try in order:**

Enable or strengthen `retriever.keyword_prefilter`. If it is off, turn it on. The keyword pre-filter uses folder path and filename matching to narrow candidates before vector search — this eliminates cross-domain false positives that share vocabulary.

```yaml
retriever:
  keyword_prefilter: true
  keyword_prefilter_min_score: 0.3   # require at least weak keyword signal
```

Move genuinely unrelated content to the noise folder. If you have personal health notes mixed with technical notes at the same folder level, reorganise them into distinct domain folders so the folder path signal is cleaner.

Raise `retriever.similarity_threshold` to 0.75. Wrong-source results almost always have lower similarity scores than correct-source results. A tighter threshold cuts them first.

If the wrong source keeps appearing despite a high threshold, check whether its content actually overlaps semantically with your query topic. If it does, that is not a retrieval error — the content genuinely matches and belongs in the results.

---

#### Symptom: Passages feel fragmented — text cuts off mid-thought or jumps abruptly

**What it means:** Chunks are too small, or stitching is not connecting adjacent chunks that belong together.

**Diagnosis steps:**

Check `indexer.chunk_size` in config. If it is below 300 tokens, chunks may be too granular for coherent stitching.

Check whether the fragmented passages come from a single large file covering multiple topics (like Istio Details.md). Multi-topic files require heading-aware splitting to produce coherent chunks.

**Fixes — try in order:**

Increase `indexer.chunk_size` from 512 to 600 tokens. Larger chunks produce more self-contained passages.

```yaml
indexer:
  chunk_size: 600   # was 512
  chunk_overlap: 80  # increase overlap proportionally
```

Increase `retriever.stitch_distance` from 2 to 3. This allows stitching to bridge up to 3 chunk positions, connecting passages that are a little further apart in the document.

```yaml
retriever:
  stitch_distance: 3   # was 2
```

After changing chunk size, you must re-index the affected files. Chunk size changes invalidate existing chunks. Run `ctxkit index` to pick up the delta.

---

#### Symptom: Context feels incomplete — right sources, but missing specific detail you know exists

**What it means:** The specific section you need is in the vault but is not being retrieved. Either it is not scoring highly enough, or it is being displaced by other chunks from the same file.

**Diagnosis steps:**

Run the search with `--verbose` flag to see individual chunk scores:

```bash
ctxkit search "Bruno ingress path" --verbose
```

Check whether the expected chunk appears in the raw results with a reasonable score but gets displaced during assembly by higher-scoring chunks from the same file.

**Fixes — try in order:**

Your query may be too broad. Narrow it to include specific terms that appear in the section you need. Instead of "Bruno ingress path adaptor", try "Bruno VPN ILB private IP ingress".

Increase `retriever.max_chunks_per_source` from its default. Currently ctxkit caps how many chunks from a single source file can appear in the final assembly to prevent one large file dominating the output. If the file you need is comprehensive and multi-section, raise this cap.

```yaml
retriever:
  max_chunks_per_source: 4   # was 2
```

If the specific content is in a section that is consistently missed, check its breadcrumb metadata by running `ctxkit index --inspect "Istio Details.md"`. This shows how the file was chunked and what breadcrumbs were assigned. If the heading was not captured correctly, the chunk may be scoring against the wrong semantic signal.

---

#### Symptom: Good output today, noticeably worse next week with no vault changes

**What it means:** Index drift. Files have been modified outside of a `ctxkit index` run, or the manifest is out of sync.

**Fix:**

Run `ctxkit status`. It will report how many files have been modified since the last index. If the number is above your configured `manifest.drift_warning_threshold`, run:

```bash
ctxkit index
```

This is the most common cause of gradual quality degradation in practice. Make `ctxkit index` a weekly habit, or run it after any significant vault editing session.

---

#### Symptom: Query about a multi-section file only returns one section

**What it means:** For broad queries about a comprehensive document (like "explain Istio on GCP"), you want content from multiple sections of the file. But the retriever may be capping per-source chunks and excluding the rest.

**Fix:**

For this type of broad orientation query, use a more explicit query that signals you want a comprehensive overview:

```bash
ctxkit search "Istio GCP overview architecture complete"
```

The word "overview" and "complete" increase the semantic signal for comprehensive coverage.

Also raise `retriever.max_chunks_per_source`:

```yaml
retriever:
  max_chunks_per_source: 6   # was 2 — allows comprehensive file coverage
```

And raise `retriever.top_k` to ensure more chunks from the same file survive the initial retrieval:

```yaml
retriever:
  top_k: 20
```

---

#### Symptom: Signpost list is always empty — no "also available" suggestions

**What it means:** Either all relevant content is fitting within the word budget (good), or retrieval top K is too low and not finding secondary relevant sources.

If you know there should be related content in other files that is not appearing even in the signpost list:

```yaml
retriever:
  top_k: 20              # increase raw candidate count
  similarity_threshold: 0.55   # lower bar to catch secondary relevant sources
```

---

#### Symptom: Signpost list is always full — many items that never get promoted to primary context

**What it means:** Your vault has rich relevant content but the word budget is too tight to include it. Consider increasing the budget.

```yaml
retriever:
  context_block_max_words: 1500   # was 1000
  signpost_max_items: 5           # reduce signpost noise
```

Note: paste size into LLM conversations has practical limits. Above 1500 words, some subscription LLM interfaces become unwieldy. Test at 1200 words first before going higher.

---

## 6. Configuration Parameters That Affect Output Quality

Quick reference mapping every quality symptom to its controlling parameter:

| Parameter | Default | Effect of increasing | Effect of decreasing |
|---|---|---|---|
| `retriever.top_k` | 15 | More candidates, richer assembly, more noise risk | Fewer candidates, faster, may miss relevant content |
| `retriever.similarity_threshold` | 0.65 | Tighter relevance, fewer but more accurate results | Looser relevance, more results, more noise |
| `retriever.context_block_max_words` | 1000 | Longer output, more content | Shorter output, less content |
| `retriever.max_chunks_per_source` | 2 | More coverage per file, less source diversity | Less coverage per file, more source diversity |
| `retriever.stitch_distance` | 2 | More stitching, more coherent passages, risk of over-merging | Less stitching, more fragments |
| `retriever.signpost_max_items` | 8 | More suggestions in also-available list | Fewer suggestions |
| `indexer.chunk_size` | 512 | Larger chunks, more coherent passages, less granular retrieval | Smaller chunks, more granular retrieval, more fragmentation risk |
| `indexer.chunk_overlap` | 64 | Less risk of split concepts, larger index | More risk of split concepts, smaller index |
| `indexer.min_word_count` | 50 | More files excluded from index | More files included, more noise risk |

---

## 7. Updated Config Reference

Full retriever section of `~/.ctxkit/config.yaml` with all new parameters documented:

```yaml
# ─────────────────────────────
# RETRIEVER
# ─────────────────────────────
retriever:
  # Candidate retrieval
  keyword_prefilter: true               # run keyword pass before vector search
  keyword_prefilter_min_score: 0.3      # minimum keyword match signal required
  top_k: 15                             # raw chunks returned by vector search
  similarity_threshold: 0.65            # minimum similarity score to include

  # Assembly
  context_block_max_words: 1000         # hard cap on primary context word count
  max_chunks_per_source: 2              # max chunks included per source file
  stitch_distance: 2                    # max chunk index gap to stitch together
  stitch_max_words: 400                 # max words in a single stitched passage

  # Signpost list
  signpost_max_items: 8                 # max items in also-available list
  signpost_include_section_hints: true  # show heading breadcrumbs in signpost

  # Output
  output_format: markdown               # markdown | plain
  include_word_count: true              # show word count in context block header
  include_timestamp: true               # show assembly timestamp
  include_source_paths: true            # show full vault-relative paths
  verbose: false                        # show individual chunk scores (debug)

# ─────────────────────────────
# INDEXER (chunking parameters)
# ─────────────────────────────
indexer:
  min_word_count: 50                    # files below this are skipped
  min_structure_signals: 1             # minimum headings or paragraphs
  chunk_size: 512                       # target tokens per chunk
  chunk_overlap: 64                     # token overlap between chunks
  max_chunk_words: 400                  # chunks above this are split further
  heading_aware_splitting: true         # split on headings before token count
  preserve_tables: true                 # never split mid-table
  preserve_code_blocks: true            # never split mid-code-block
  heading_levels: [2, 3]               # heading levels used as split boundaries
  batch_size: 32                        # files processed per batch
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
```

---

## 8. Real Example — Istio Details.md

This section documents how the full Istio Details.md file (1,500 words, 9 sections) should be indexed and retrieved under ctxkit's design.

**How it should be chunked:**

With `heading_aware_splitting: true` and `heading_levels: [2, 3]`, the file produces the following chunks:

| Chunk | Heading breadcrumb | Approx words | Notes |
|---|---|---|---|
| 1 | Istiod — The Brain | 180 | Self-contained section |
| 2 | Your Gateway Setup | 220 | Self-contained section |
| 3 | CRDs > Gateway, VirtualService | 210 | Long section split at token limit |
| 4 | CRDs > DestinationRule through Sidecar CRD | 200 | Continuation of CRD section |
| 5 | Two Ingress Paths > Path 1 — Bruno | 190 | Self-contained subsection |
| 6 | Two Ingress Paths > Path 2 — Orchestrator | 160 | Self-contained subsection |
| 7 | Inside the Adaptor Pod | 200 | Self-contained section |
| 8 | Egress Path — SOAP to On-Prem | 210 | Self-contained section |
| 9 | Where Each Concern Lives — Summary | 120 | Table — kept intact |

**How specific queries should retrieve from this file:**

| Query | Expected primary chunk | Expected chunk index |
|---|---|---|
| "Bruno ingress path VPN adaptor" | Path 1 — Bruno | 5 |
| "Orchestrator in-mesh sidecar call" | Path 2 — Orchestrator | 6 |
| "AuthorizationPolicy SPIFFE identity" | CRDs chunk 2 | 4 |
| "egress gateway SOAP on-prem" | Egress Path | 8 |
| "Istiod xDS config push" | Istiod — The Brain | 1 |
| "explain Istio on GCP overview" | Multiple chunks — 1,2,3,5,7,8 | stitched |

**What the context block looks like for "Bruno ingress path adaptor":**

```markdown
## Context package: Bruno ingress path adaptor
*Assembled by ctxkit · 1 source · 412 words · 2026-04-24 09:14*

---

### [1] Lloyds Related / Istio Details.md
*Sections: Your Gateway Setup · The Two Ingress Paths > Path 1 — Bruno*

**Your Gateway Setup**
You have a dedicated `istio-gateway` namespace containing three gateway pods.
`istio-ingressgateway-ilb` is the one your Adaptor uses. It sits behind a GCP 
Internal Load Balancer, which means it has a private IP only. It is not reachable 
from the public internet. Only callers inside the VPC — or connected to it via 
VPN — can reach it. This is exactly right for a payment adaptor in a regulated 
environment.

**Path 1 — Bruno (dev testing)**
Bruno runs on your org laptop inside the corporate VPN. The VPN puts you inside 
the GCP VPC network, giving you access to the ILB's private IP. The journey is:

Bruno → HTTPS → GCP ILB (private IP, SSL termination) → 
`istio-ingressgateway-ilb` pod → VirtualService routing evaluated here, 
URI rewritten here, mTLS originated here → Adaptor pod iptables intercepts → 
Envoy sidecar terminates mTLS, validates caller identity → plain HTTP on 
localhost:8080 → Spring Boot.

By the time the request reaches Spring Boot it is plain HTTP on localhost. 
The URI has already been rewritten. Spring Boot has no knowledge of the ILB, 
the gateway, the VPN, or the original public path.

---

## Also available — fetch if the LLM needs to go deeper

| Source | Relevant sections | Suggested query |
|---|---|---|
| Lloyds Related / Istio Details.md | CRDs — VirtualService, AuthorizationPolicy | `ctxkit search "Istio VirtualService DestinationRule"` |
| Lloyds Related / Istio Details.md | Inside the Adaptor Pod | `ctxkit search "Istio Envoy sidecar adaptor pod"` |

---
*Paste this block at the start of your LLM conversation as opening context.*
```

---

*ctxkit — Context Portability and Knowledge Ingestion Tool*
*Retrieval Design and Quality Evaluation Guide v1.0.0*
