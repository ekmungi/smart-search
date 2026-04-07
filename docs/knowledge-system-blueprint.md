# Knowledge System Blueprint — Session Handoff

> This document captures everything needed to continue building the LLM Wiki knowledge system.
> It is designed to be pasted (or referenced) at the start of a new Claude Code session so the
> agent has full context without re-discovery.

---

## 1. What We're Building

A personal knowledge system following [Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f). Instead of RAG (re-searching raw documents every query), the LLM **incrementally builds and maintains a persistent wiki** — a structured, interlinked collection of markdown files that compounds in value over time.

**Key insight:** "Humans abandon wikis because the maintenance burden grows faster than the value. LLMs don't get bored, don't forget to update a cross-reference, and can touch 15 files in one pass."

- **Human role:** curate sources, direct analysis, ask questions, think about meaning
- **LLM role:** summarize, cross-reference, file, maintain consistency

## 2. The Actual Vault Structure (PARA)

The vault is an Obsidian vault on a Windows machine. It follows the PARA organizational method. Here is the real structure as described by the vault owner:

### Projects/

Active, time-bound work with clear deliverables. Multiple project folders, each containing:

- **Project main MD file** — high-level project overview/description
- **`resources/`** — all project documents organized appropriately (PDFs, DOCX, PPTX, XLSX, etc.)
- **`tasks/`** — individual task files (`task_name.md` per task)

*Note: Some of this structure isn't perfectly maintained yet.*

### Areas/

Ongoing responsibilities and personal tracking, NOT tied to specific projects:

- Career progression tracking
- Product roadmap (the overall roadmap, not project-specific)
- Random ideas not connected to any project
- Other long-term personal/professional areas

### Resources/

Global reference material. This is the largest and most varied section:

#### Meetings/
Organized by **Olympus fiscal year** (April → March):
- **FY26** = April 2025 → March 2026
- **FY27** = April 2026 → March 2027 (current)

Inside each FY folder:
```
Resources/Meetings/
├── FY26/
│   ├── Q1/
│   │   ├── 2025-04-15-product-review.md          ← meeting notes (your notes)
│   │   ├── 2025-04-22-regulatory-sync.md
│   │   └── transcripts/
│   │       ├── 2025-04-15-product-review-transcript.md  ← from transcription tool
│   │       └── 2025-04-22-regulatory-sync-transcript.md
│   ├── Q2/
│   ├── Q3/
│   └── Q4/
├── FY27/
│   ├── Q1/
│   │   ├── meeting-notes.md
│   │   └── transcripts/
│   ├── Q2/
│   ├── Q3/
│   └── Q4/
```

**Meeting notes** are MD files you write (or your transcription tool generates).
**Transcripts** are MD files from your custom transcription software, linked from the meeting notes.

The transcription tool outputs paired files: a notes MD + a linked transcript MD.

#### Stakeholders/
One MD file per stakeholder containing:
- Their professional information (title, org, role)
- Personal preferences and communication style
- Useful information for connecting with them personally
- Currently NOT linked to meeting notes (a key gap)

#### Other Resource Folders
- **User Interviews / Research** — user research recordings and notes
- **Congress Notes** — conference/congress attendance notes
- **Clinical and Scientific Literature** — organized by topic subfolder
- **Product Information** — IFUs (Instructions for Use), technical documents, videos
- **Products/** — list of products as individual MD files (Notion-like database view)
- **Versions/** — product subfolders with version number MD files per product
- **Features/** — feature description MD files, linked to versions → products

*Note: Products/Versions/Features form a linked hierarchy: Feature → Version → Product. The Products/ folder may be redundant with the entity-based approach.*

### Archives/

Frozen content. Not processed, not updated. Excluded from all compilation work.

---

## 3. Karpathy's Architecture (What We Need)

From the [full gist + video summary](https://github.com/ekmungi/smart-search/blob/main/docs/llm-wiki-karpathy-with-summary.md):

### Three Layers

| Layer | Karpathy | Our System |
|-------|----------|------------|
| **Raw Sources** | `raw/` — immutable source files, never modified | PARA vault: Projects/, Areas/, Resources/ — existing files stay as-is |
| **The Wiki** | `wiki/` — LLM-generated/maintained markdown | `_knowledge/` folder at vault root |
| **The Schema** | `claw.md` — tells the LLM how to operate | `_knowledge/SCHEMA.md` + Jeeves skill definitions |

### Three Operations

| Operation | What It Does | Our Implementation |
|-----------|-------------|-------------------|
| **Ingest** | Read source → write summary → update entity/concept pages → update index/log. Touches 10-15 files. | `process-meeting` skill (meetings pilot) |
| **Query** | Read `index.md` first → find relevant pages → synthesize answer. Good answers filed back as wiki pages. | `obsidian-knowledge` with Tier 0 (index.md first) |
| **Lint** | Health check: contradictions, stale claims, orphan pages, missing cross-references, data gaps | Future skill (not in pilot) |

### Two Special Files

| File | Purpose |
|------|---------|
| `index.md` | Content-oriented catalog. Every wiki page listed with one-line summary. LLM reads this FIRST on every query. Updated on every ingest. |
| `log.md` | Append-only chronological record. Each entry: `## [YYYY-MM-DD] ingest \| Source Title`. Parseable with grep. Never edited, only appended. |

### Karpathy's Exact Wiki Structure

```
wiki/
├── sources/      ← per-source summary pages ("what did the wiki learn from this source?")
├── entities/     ← pages for specific things (products, people, regulations, companies)
├── concepts/     ← pages for abstract topics (regulatory strategy, clinical evidence)
├── analysis/     ← filed query results, comparisons, explorations ("queries compound")
└── hot.md        ← rolling ~500-word context cache of most recent important context
```

---

## 4. Our Adapted `_knowledge/` Structure

Mapping Karpathy's structure to our PARA vault:

```
_knowledge/                          ← Karpathy's "wiki/" — vault-level, cross-cutting
├── index.md                         ← Master catalog (read FIRST on every query)
├── log.md                           ← Append-only operation history
├── SCHEMA.md                        ← Conventions, templates, cross-link syntax
├── hot.md                           ← Rolling context cache (~500 words of "what's happening now")
├── sources/                         ← Per-source ingestion records
│   ├── meetings/                    ← One page per processed meeting
│   │   ├── 2026-03-15-fda-pre-sub.md    ← "What the wiki learned from this meeting"
│   │   └── 2026-04-01-partner-call.md
│   ├── literature/                  ← One page per ingested paper/article
│   └── interviews/                  ← One page per ingested interview
├── entities/                        ← Pages for specific things
│   ├── products/
│   │   ├── cams.md                  ← Aggregates from meetings, roadmaps, tech docs
│   │   └── endovision.md
│   ├── people/
│   │   ├── dr-klaus-muller.md       ← Links TO stakeholder file + meeting history
│   │   └── dr-anna-weber.md
│   ├── companies/
│   │   └── competitor-acme-ai.md
│   ├── regulations/
│   │   ├── fda-510k.md              ← Discussion timeline across meetings
│   │   └── eu-mdr.md
│   └── studies/
│       └── cleopatra-iii-trial.md
├── concepts/                        ← Pages for abstract topics
│   ├── regulatory-pathways-ai-devices.md
│   ├── clinical-evidence-requirements.md
│   └── ai-in-endoscopy-market.md
└── analysis/                        ← Filed query results (explorations compound)
    ├── cams-regulatory-comparison-us-eu.md    ← Analysis that was worth keeping
    └── competitor-landscape-q1-fy27.md
```

### Why Each Subfolder Matters

**`sources/`** — The "contribution record." When a meeting is processed, a source page documents:
what entities were found, what concepts were discussed, what wiki pages were updated, what was
new vs. already known. This creates the link chain: source page → entity pages → other source
pages mentioning same entity. Without this, entity pages link directly to raw meeting notes,
skipping the wiki's own perspective on what it learned.

**`entities/`** — Organized by type (products, people, companies, regulations, studies).
Each page aggregates everything the wiki knows from ALL sources. A product page like `cams.md`
draws from meetings, roadmaps, technical docs, and regulatory plans. Discussion timelines show
how knowledge evolved chronologically. Sub-organized by type because the vault has hundreds of
entities and flat listing becomes unwieldy.

**`concepts/`** — Abstract topics that span multiple entities. "Regulatory Pathways for AI Devices"
synthesizes knowledge about FDA 510(k), EU MDR, and MHRA across all sources. These are reference
articles that get richer over time.

**`analysis/`** — Filed query results. When Jeeves synthesizes an answer worth keeping (a regulatory
comparison, a competitive landscape analysis, a strategic recommendation), it's filed here instead
of disappearing into chat history. Next time a related question comes up, the analysis already exists.
This is Karpathy's "explorations add up" feedback loop.

**`hot.md`** — Rolling ~500-word context cache. Different from Jeeves's `learnings.md` (curated
knowledge) or `preferences.md` (user preferences). This is "what's happening RIGHT NOW" — recent
decisions, current sprint focus, active threads, upcoming deadlines. The LLM reads it on every
session to orient itself. Updated by `process-meeting` and `session-notes`.

### Cross-Linking Graph

Every page type links to every other, creating the dense graph that Obsidian visualizes:

```
Meeting Note (Resources/Meetings/)
    ↕ wiki-links
Source Page (_knowledge/sources/meetings/)
    ↕ wiki-links
Entity Pages (_knowledge/entities/*/)
    ↕ wiki-links
Concept Pages (_knowledge/concepts/)
    ↕ wiki-links
Analysis Pages (_knowledge/analysis/)
    ↕ wiki-links
Stakeholder Files (Resources/Stakeholders/)
    ↕ wiki-links
Project Files (Projects/*/)
```

**Bidirectional links are critical.** When process-meeting adds a link from a meeting note to
an entity page, it also adds a backlink from the entity page to the meeting (via the source page).
This is what makes the Obsidian graph view light up.

---

## 5. Smart-search: The Search Layer

**Decision: keep smart-search** (not QMD).

- Smart-search: ~130MB RAM, CPU-only, no GPU needed
- QMD: ~4-6GB RAM, expects GPU — 30x heavier
- On a standard laptop without discrete GPU, smart-search is the only option that stays responsive

Smart-search provides:
- 14-format conversion via MarkItDown (PDF, DOCX, PPTX, XLSX, etc.)
- Hybrid search: BM25 + vector (Snowflake Arctic Embed M v2.0) + RRF + TinyBERT reranking
- 11 MCP tools for Claude Code/Jeeves
- File watching (Watchdog) with debounced re-indexing
- Tauri desktop app

**Future improvements to port from QMD:**
1. Query expansion (generate 2-3 query variants before search)
2. Collection/path context (attach PARA folder metadata to results)
3. Position-aware blending (tune RRF weighting per document type)

**Repos:**
- Smart-search: `ekmungi/smart-search`
- Jeeves: `ekmungi/jeeves`

---

## 6. Jeeves: The Agent Layer

Jeeves is a Claude Code plugin with 8 specialized agents and 22 domain skills for a Global AI
Product Manager in healthcare/medical devices (Olympus). It orchestrates research, analysis, and
document creation. Smart-search is one of its tools.

### New Skills to Build (Meetings Pilot)

**Phase 1: vault-audit**
- Walk entire vault, discover real structure
- Report folder names, file types, frontmatter conventions
- Deep dive into Meetings/ and Stakeholders/
- Discover transcription tool output format
- Produces structured report that informs all subsequent skills

**Phase 2: process-meeting (Karpathy's Ingest)**
Takes a meeting (notes MD + transcript) and produces three outputs, touching 10-15 files:

*Output 1 — Enhanced Meeting Note:*
- Structured frontmatter (date, attendees, projects, meeting_type, transcript link)
- Wiki-links to stakeholder files, project files
- Related meetings discovery (semantic search + frontmatter overlap + entity co-occurrence)
- `## Related Meetings` section

*Output 2 — Tasks/Action Items:*
- Extracted action items (who, what, when)
- Linked to meeting note, project, assignee
- Via task-creator skill

*Output 3 — Knowledge Entries:*
- Creates/updates source page in `_knowledge/sources/meetings/`
- Creates/updates entity pages in `_knowledge/entities/`
- Creates/updates concept pages in `_knowledge/concepts/`
- Appends to `_knowledge/log.md`
- Updates `_knowledge/index.md`
- Updates `_knowledge/hot.md` with latest context

**Phase 3: task-creator**
- Companion to process-meeting
- Creates task entries linked to meeting, project, assignee
- Also invocable standalone

**Phase 4: Update existing skills**
- `obsidian-knowledge` → Tier 0: read `index.md` first → entity/concept pages → smart-search → Grep
- `meeting-prep` → pull from `_knowledge/entities/people/` for attendee profiles + discussion timelines
- `session-notes` → trigger knowledge ingestion after writing session summary

### Existing Skills (Working)
meeting-prep, partnership-evaluation, market-research, technical-research, daily-briefing,
project-docs, prioritization, product-requirements, roadmap-planning, session-notes, smart-search,
obsidian-knowledge, clinical-expertise, regulatory-intelligence, and others.

### Memory System
- `~/.claude/jeeves/memory/preferences.md` — vault path, user preferences
- `~/.claude/jeeves/memory/learnings.md` — curated cross-session knowledge
- `~/.claude/jeeves/memory/learnings-staging.md` — pending review

---

## 7. Phased Implementation Plan

### Phase 1: Discover (vault-audit)
- Build `jeeves/skills/vault-audit/SKILL.md`
- Run on vault → produces structural report
- Learn: actual folder names, frontmatter conventions, transcription tool format, stakeholder file structure
- Update CLAUDE.md routing table
- **Must complete before anything else**

### Phase 2: Scaffold (_knowledge/ structure)
- Create `_knowledge/` folder at vault root
- Create `index.md`, `log.md`, `SCHEMA.md`, `hot.md`
- Create subdirectories: `sources/meetings/`, `entities/products/`, `entities/people/`, `entities/companies/`, `entities/regulations/`, `entities/studies/`, `concepts/`, `analysis/`
- SCHEMA.md defines: page templates, frontmatter format, cross-link conventions, naming rules
- Adapt based on vault-audit findings

### Phase 3: Meetings Ingest (process-meeting)
- Build `jeeves/skills/process-meeting/SKILL.md`
- Process one meeting end-to-end → validate output quality
- Verify: 10-15 files touched, source page created, entity pages updated, stakeholders linked
- Scale to batch processing of recent meetings (start with current quarter)
- Build task-creator as companion

### Phase 4: Query Enhancement
- Update `obsidian-knowledge` with Tier 0 (index.md → entity pages → smart-search → Grep)
- Update `meeting-prep` to pull from `_knowledge/entities/people/` for attendee profiles
- Test: meeting prep should be dramatically richer with knowledge layer
- Enable "file answer as analysis page" for valuable query results

### Phase 5: Expand Beyond Meetings
- Process stakeholder files → entity pages in `_knowledge/entities/people/`
- Process product files → entity pages in `_knowledge/entities/products/`
- Process literature → source pages + concept pages
- Process user interviews → source pages + entity/concept pages
- Each new source type follows the same Ingest pattern

### Phase 6: Maintenance (Lint)
- Build wiki-lint skill
- Contradictions, stale claims, orphan pages, missing cross-references
- Surface findings in daily-briefing

---

## 8. Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Search engine | Smart-search (keep) | 130MB RAM vs QMD's 4-6GB. Local-first, no GPU. |
| `_knowledge/` location | Vault root | Cross-cutting across all PARA categories |
| Entity organization | Typed subdirectories (`entities/products/`, `entities/people/`) | Hundreds of entities; flat listing unwieldy |
| Source pages | Yes, in `_knowledge/sources/` | Creates the missing link in the cross-reference graph |
| Analysis pages | Yes, in `_knowledge/analysis/` | Enables "explorations add up" feedback loop |
| `hot.md` | Yes | Rolling context cache for session orientation |
| Pilot scope | Meetings folder only | Highest immediate value; validates pattern before expanding |
| Vault-audit first | Always | Never assume structure; discover, then adapt |

---

## 9. Related Resources

- **Karpathy's gist:** https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- **Full gist + video summary:** `docs/llm-wiki-karpathy-with-summary.md` in this repo
- **Implementation plan (detailed):** `docs/meetings-pilot-plan.md` in this repo
- **System design (HTML):** `docs/system-design/index.html` (GitHub Pages)
- **Smart-search repo:** `ekmungi/smart-search`
- **Jeeves repo:** `ekmungi/jeeves`
