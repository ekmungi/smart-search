# Plan: Retrieval Architecture — Layered Solution Design

## What This Plan Delivers

An **interactive HTML architecture page** (`docs/retrieval-architecture.html`) that maps out:
- The user scenarios (with real examples)
- The layered solution (what handles what)
- The boundaries between Quick Search, Smart Search MCP, and Claude Code
- What exists today vs what's missing at each layer

This is a design artifact — no code changes. The goal is to align on architecture before writing a line of code.

---

## The Four Layers

### Layer 1: File Discovery (Quick Search UI)
**Job:** "Find me that file I vaguely remember"

| Scenario | Example | What's Needed |
|---|---|---|
| Vague file recall | "That Medtronic polyp-sizing paper" | Filename + path search, fuzzy matching |
| Topic browse | "User research files from last few months" | Folder-aware search, date filtering |
| Project resources | "The AI roadmap I shared with Solutions" | PARA-aware path matching |
| Literature lookup | "Papers about cardiac ablation" | Semantic search over doc titles + abstracts |

**What exists today:** Chunk-level hybrid search. Returns snippets, not files.
**What's missing:** File-level result mode, filename/path FTS, date awareness.
**Who handles it:** Smart Search (Quick Search overlay)

### Layer 2: Document Exploration (Claude Code)
**Job:** "Dig deeper into this specific document"

| Scenario | Example | What's Needed |
|---|---|---|
| Read a found file | "Open that polyp study and summarize it" | `read_note()` — already exists |
| Drill into sections | "What does the Methods section say?" | Section-aware chunk retrieval within a doc |
| Extract specific info | "What sample size did they use?" | Focused search within a single document |

**What exists today:** `read_note()` reads full file. `knowledge_search()` can filter by folder but not by specific file.
**What's missing:** `source_paths` filter param (search within specific docs).
**Who handles it:** Claude Code + Smart Search MCP tools

### Layer 3: Cross-Document Intelligence
**Job:** "Find connections between documents I didn't ask about"

| Scenario | Example | What's Needed |
|---|---|---|
| Meeting-to-paper link | "Were there meetings about this research topic?" | Cross-type document matching |
| Multi-source assembly | "What do we know about X across papers, meetings, and notes?" | Pre-computed relationships by topic |
| Timeline awareness | "What happened first — the meeting or the paper?" | Date-aware document ordering |
| People connections | "Which meetings involved Mike about this topic?" | Entity extraction (people, dates) |

**What exists today:** `find_related()` computes on-the-fly similarity via averaged embeddings. No persistent relationships. No entity extraction.
**What's missing:** Pre-computed document graph, entity extraction (people, dates, topics), cross-type search.
**Who handles it:** NEW capability — could be a Smart Search index-time feature OR a separate agent layer

### Layer 4: Synthesis (Claude Code LLM)
**Job:** "Make sense of all this for me"

| Scenario | Example | What's Needed |
|---|---|---|
| Summarize findings | "Summarize the polyp study and related meetings" | Layer 1-3 surface the docs, LLM synthesizes |
| Compare sources | "How do the meeting notes differ from the paper?" | Multiple docs in context |
| Generate output | "Write a brief for the team based on this research" | Full context from all layers |

**What exists today:** Claude Code can read and synthesize — this layer works IF Layers 1-3 provide the right context.
**What's missing:** Nothing at this layer. The bottleneck is Layers 1-3 not surfacing the right documents.
**Who handles it:** Claude Code (LLM)

---

## Architecture Diagram (to be rendered in HTML)

```
┌─────────────────────────────────────────────────────────┐
│                    USER INTENT                          │
│  "Find the user research files, check if there were    │
│   meetings about this, summarize what we know"         │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 4: SYNTHESIS (Claude Code LLM)                   │
│  Orchestrates Layers 1-3, synthesizes final answer      │
│  Tools: read_note, knowledge_search, knowledge_related  │
│  Guided by: skill.md / agent.md                         │
└────────────┬────────────────────────────────────────────┘
             │ calls tools
             ▼
┌──────────────────┐  ┌──────────────────┐  ┌─────────────┐
│  LAYER 1         │  │  LAYER 2         │  │  LAYER 3    │
│  FILE DISCOVERY  │  │  DOC EXPLORATION │  │  CONNECTIONS│
│                  │  │                  │  │             │
│  Quick Search UI │  │  knowledge_search│  │  Document   │
│  + MCP tool      │  │  (source_paths)  │  │  Graph      │
│                  │  │  + read_note     │  │  (pre-built)│
│  Returns: FILES  │  │  Returns: CHUNKS │  │  Returns:   │
│  (1 per doc)     │  │  (within 1 doc)  │  │  RELATIONS  │
│                  │  │                  │  │             │
│  ┌────────────┐  │  │  ┌────────────┐  │  │  ┌────────┐│
│  │File-level  │  │  │  │Source-path │  │  │  │Doc     ││
│  │aggregation │  │  │  │filtering   │  │  │  │embeddings│
│  │+ path FTS  │  │  │  │+ reranker  │  │  │  │+ graph ││
│  └────────────┘  │  │  └────────────┘  │  │  └────────┘│
└──────────────────┘  └──────────────────┘  └─────────────┘
             │                 │                    │
             └─────────────────┴────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────┐
│  SHARED FOUNDATION: Smart Search Index                  │
│                                                         │
│  LanceDB (chunk embeddings) + SQLite (metadata + FTS5)  │
│  + Document embeddings table (NEW)                      │
│  + Document relationships table (NEW)                   │
│  + Files FTS5 index (NEW)                               │
└─────────────────────────────────────────────────────────┘
```

---

## Quick Search vs Claude Code — Boundary Definition

| Aspect | Quick Search (UI) | Claude Code (MCP) |
|---|---|---|
| **Interaction** | Single query → instant results | Multi-turn conversation |
| **Result type** | Files (titles, paths, previews) | Chunks, full docs, synthesized answers |
| **Latency budget** | <200ms (must feel instant) | 1-10s acceptable (agentic loops) |
| **Intelligence** | Smart ranking, no LLM | LLM-driven iterative search |
| **User action** | Click to open file | Ask follow-up questions |
| **Diversity need** | HIGH — show many different files | VARIABLE — broad then deep |

---

## User Journey Example (rendered as interactive flow in HTML)

**User says to Claude Code:** "Find the user research files we've done recently and check if there were meetings about this."

```
STEP 1: Claude calls Layer 1 (File Discovery)
  → knowledge_search(query="user research", result_type="files", limit=10)
  → Returns 10 documents: 3 PDFs, 2 DOCX, 5 MD notes
  → Claude evaluates: "These 3 look like user research files"

STEP 2: Claude calls Layer 2 (Doc Exploration)
  → knowledge_search(query="user research findings",
                      source_paths=[pdf1, pdf2, docx1], limit=5)
  → Returns best chunks from those 3 files
  → Claude reads key findings

STEP 3: Claude calls Layer 3 (Connections)
  → knowledge_related(note_path=pdf1)
  → Returns: meeting_note_march.md (sim: 0.82),
             meeting_mike_april.md (sim: 0.76)
  → Claude: "I found 2 related meeting notes"

STEP 4: Claude calls Layer 2 again
  → read_note("meeting_note_march.md")
  → read_note("meeting_mike_april.md")

STEP 5: Claude synthesizes (Layer 4)
  → "You had 3 user research files. The March meeting with the team
     discussed early findings. Mike's April meeting covered the
     follow-up actions. Here's a summary..."
```

---

## HTML Page Structure

The interactive page will include:

1. **Layer diagram** — visual boxes showing the 4 layers with arrows
2. **Scenario cards** — clickable cards showing user scenarios, which layers are involved, what's missing
3. **User journey flow** — step-by-step walkthrough of the example above, highlighting which layer handles each step
4. **Gap analysis** — red/green indicators showing what exists vs what's missing per layer
5. **Technology map** — which existing components (LanceDB, FTS5, ONNX, etc.) serve which layer

Style: matches existing `docs/search-pipeline.html` (dark theme, GitHub-style).

---

## Implementation

Single file: `docs/retrieval-architecture.html`
No dependencies. Opens in any browser. Committed to the branch for retrieval on other machines.
