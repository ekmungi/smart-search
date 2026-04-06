# Meetings Pilot: Vault Audit → Wiki Compilation

## Context

Build an LLM-powered knowledge compilation system starting with the Meetings folder. The vault is on Anant's Windows machine and we've never seen its actual structure. Anant has custom transcription software that outputs paired files (notes MD + linked transcript MD). Step 1 must discover the real vault structure before we can do anything useful.

## Karpathy's LLM Wiki Pattern (from [gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f))

The system we're building follows Karpathy's three-layer architecture:

### Three Layers
1. **Raw Sources** — Immutable source documents. In our case: meeting transcripts, PDFs, DOCX files, the vault's existing MD notes. These never get modified.
2. **The Wiki** — LLM-generated/maintained markdown files: summary pages, entity pages, concept pages, comparisons, cross-references. This is the `_knowledge/` folder. The compounding artifact.
3. **The Schema** — Configuration document defining wiki structure, conventions, and workflows. This is `_knowledge/SCHEMA.md` plus the Jeeves skill definitions.

### Three Operations
1. **Ingest** — User drops new source (e.g., processes a meeting). LLM reads it, writes/updates summary page, modifies relevant wiki pages (entity pages, concept pages), updates `index.md`, appends to `log.md`. **Typically touches 10-15 pages per source.**
2. **Query** — User asks a question. LLM reads `index.md` first to locate relevant pages, searches wiki, synthesizes answer with citations. **Answers can become new wiki pages** — queries compound into knowledge.
3. **Lint** — Periodic health check: contradictions across pages, stale claims, orphan pages (no incoming links), missing cross-references, data gaps.

### Two Special Files
- **`index.md`** — Content-oriented catalog. Every wiki page listed with one-line summary, organized by category. LLM reads this FIRST on every query to know what knowledge exists. Updated on every ingest.
- **`log.md`** — Append-only chronological record. Each entry: `## [YYYY-MM-DD] ingest | Source Title`. Parseable by simple tools. Never edited, only appended.

### Key Insight
> "Humans abandon wikis because the maintenance burden grows faster than the value. LLMs don't get bored, don't forget to update a cross-reference, and can touch 15 files in one pass."

Human role: curate sources, direct analysis, ask questions, think about meaning.
LLM role: summarize, cross-reference, file, maintain consistency.

### Recommended Tools
- **qmd** — Local markdown search (BM25 + vector + LLM reranking). We're using smart-search instead (lower RAM, already integrated).
- **Obsidian graph view** — Visualize wiki connectivity
- **Dataview** — Query over page frontmatter
- **Git** — Wiki as markdown repo for history

---

---

## Step 1: Build `vault-audit` Skill

**File:** `jeeves/skills/vault-audit/SKILL.md`

A Jeeves skill that walks the entire Obsidian vault and produces a structured report. Covers the full vault (not just meetings) so future work has a map.

**The skill does:**
- Read vault path from `~/.claude/jeeves/memory/preferences.md`
- Walk directory tree (top 3 levels), count files by type per folder
- Sample 3-5 MD files per major folder: read frontmatter, note structure/headings
- **Meetings deep dive:** find meeting folders, sample the transcription tool's output format (notes MD + linked transcript), report frontmatter fields, linking pattern, naming convention
- **Stakeholders deep dive:** find stakeholder folder, sample files, report structure
- Output a structured report to vault (or console)

**Also update:** `jeeves/CLAUDE.md` — add `vault-audit` to routing table

### What we learn from the audit
- Actual folder names and paths
- Existing frontmatter conventions (so we extend, not conflict)
- Transcription tool's output format (what wiki-compile needs to work with)
- Current cross-linking state (what's connected, what's orphaned)

---

## Step 2: Process Meetings Folder (After Audit)

**Depends on audit results.** Specifics will be adjusted once we see the real data.

### 2a. Templates (if needed)
- Create/update templates based on what the transcription tool already generates and what exists
- Templates extend existing conventions — don't break what works

### 2b. Build `process-meeting` Skill — Karpathy's "Ingest" Operation
**File:** `jeeves/skills/process-meeting/SKILL.md`

This IS Karpathy's ingest operation, applied to meetings. Takes a meeting (notes MD + transcript) and produces three outputs. **Should touch 10-15 files per meeting** (the meeting note itself, stakeholder pages, entity pages, index.md, log.md, project references).

**Output 1 — Linked Meeting Summary:**
- Enhances the existing notes file with structured frontmatter (attendees, projects, meeting_type)
- Adds wiki-links to stakeholder files (looked up from vault)
- Adds wiki-links to related project files
- Adds wiki-link to transcript (if not already present)
- Structures decisions and key discussion points
- Uses vault-audit knowledge to find the right folders and files to link to
- **Finds and links related meetings** (see below)

**Related Meetings Discovery:**
After extracting the meeting's topics and entities, search for other meetings that discussed similar things:
- **Semantic search** via smart-search: query key topics against all meeting notes. "Regulatory pathway for CAMS" finds meetings about "FDA strategy" or "510(k) submission" even with different wording.
- **Structured overlap**: match frontmatter — same `attendees`, same `projects`, overlapping `tags`. Two meetings with the same stakeholder about the same project are almost certainly related.
- **Entity co-occurrence**: if two meetings mention the same entities (stakeholders + topics), they're related.

Adds a `## Related Meetings` section to the note:
```markdown
## Related Meetings
- [[2026-03-15-product-review]] — Also discussed CAMS regulatory timeline (same attendees: Dr. Muller)
- [[2026-02-28-fda-strategy]] — Prior discussion of 510(k) pathway (same topic: regulatory)
```

Optionally updates those related meetings with a backlink (bidirectional).

**This is where `_knowledge/` entity pages become powerful.** Instead of re-searching every time, entity pages accumulate a chronological thread. Example — the entity page for "FDA 510(k) — CAMS" lists ALL meetings where this was discussed:
```markdown
# FDA 510(k) — CAMS
## Discussion Timeline
- [[2026-01-10]] — Noted Competitor X got 510(k) in 6 months
- [[2026-02-28]] — Decided to pursue 510(k) over De Novo
- [[2026-03-15]] — Dr. Muller raised IRB timeline concern
- [[2026-04-01]] — Updated: submission target Q3 2026
```
Each processed meeting appends to this timeline. Over time: a complete narrative thread per topic, assembled automatically from individual meetings.

**Output 2 — Tasks/Action Items** (works with `task-creator` skill):
- Extracts action items from the meeting (who, what, when)
- Creates tasks linked to the meeting note (wiki-link back to source)
- Links tasks to the relevant PARA Project folder
- Assigns owner (links to stakeholder file)
- Format TBD by audit (could be Obsidian tasks plugin format, Dataview format, or standalone task MDs)

**Output 3 — Knowledge Entries** (Karpathy's wiki layer):
- Extracts learnings, facts, and insights from the meeting
- Appends to `_knowledge/log.md`: `## [YYYY-MM-DD] ingest | Meeting: [title]` with source link and what was learned
- Updates or creates entity pages in `_knowledge/entities/` (stakeholders, products, regulations mentioned)
- Updates `_knowledge/index.md` with new/updated entries and one-line summaries
- This is incremental — each processed meeting adds to the knowledge graph, doesn't replace it
- **Answers to queries can also become wiki pages** — when Jeeves answers a question using wiki content, the answer itself can be filed as a new wiki page (Karpathy's "query → knowledge" loop)

### 2c. Build `task-creator` Skill
**File:** `jeeves/skills/task-creator/SKILL.md`

Companion to process-meeting. Handles task creation and tracking:
- Creates task entries from action items extracted by process-meeting
- Links each task to: source meeting, project, assignee (stakeholder)
- Respects existing task format in the vault (discovered by audit)
- Can also be invoked standalone: `jeeves:task-creator` to create tasks from any context

### 2d. Set Up `_knowledge/` Structure (Karpathy Layer)
- Create `_knowledge/` folder at vault root (if not exists)
- Create `_knowledge/index.md` — master catalog of all knowledge entries
- Create `_knowledge/log.md` — append-only chronological record of ingestion events
- Create `_knowledge/entities/` — entity pages (stakeholders, products, regulations, etc.)
- Create `_knowledge/SCHEMA.md` — conventions for entity page format, cross-link syntax
- process-meeting populates these incrementally as meetings are processed

### 2e. Link Stakeholders ↔ Meetings
- Add meeting history wiki-links to stakeholder files
- Add stakeholder wiki-links to meeting notes
- Bidirectional: Obsidian graph view lights up
- Stakeholder entities also get pages in `_knowledge/entities/` linking to their stakeholder file

### 2f. Karpathy's "Query" Operation — Update `obsidian-knowledge`
The existing `obsidian-knowledge` skill becomes the Query operation. Changes:
- **Read `_knowledge/index.md` FIRST** on every query (Karpathy's key pattern — the index is the entry point)
- Then search entity/concept pages in `_knowledge/`
- Then fall through to smart-search semantic search → Grep/Glob
- When an answer is synthesized from wiki content, **optionally file the answer as a new wiki page** (compounding queries into knowledge)

### 2g. Karpathy's "Lint" Operation — Future Skill
Not built in this pilot, but designed for:
- Contradictions across entity pages
- Stale claims (source data changed but wiki page not updated)
- Orphan pages (no incoming wiki-links)
- Missing cross-references (entity mentioned in text but not linked)
- `index.md` completeness (all wiki pages listed)

### 2h. Update Existing Skills
- `meeting-prep` — add structured frontmatter queries for attendees/projects; pull from `_knowledge/entities/` for stakeholder context
- `obsidian-knowledge` — implement Tier 0 from 2f above (index.md first → entity pages → smart-search → Grep)
- `CLAUDE.md` — add vault-audit, process-meeting, task-creator to routing table

---

## Files to Create

| File | Purpose |
|------|---------|
| `jeeves/skills/vault-audit/SKILL.md` | Vault structure discovery — **build first** |
| `jeeves/skills/process-meeting/SKILL.md` | Process meeting → summary + tasks + knowledge |
| `jeeves/skills/task-creator/SKILL.md` | Create and link tasks from action items |
| Vault: `_knowledge/index.md` | Master catalog of knowledge entries |
| Vault: `_knowledge/log.md` | Chronological ingestion record |
| Vault: `_knowledge/SCHEMA.md` | Conventions for entity pages and cross-links |

## Files to Modify

| File | Change |
|------|--------|
| `jeeves/CLAUDE.md` | Add vault-audit, process-meeting, task-creator to routing table |
| `jeeves/skills/meeting-prep/SKILL.md` | Structured frontmatter queries + `_knowledge/` entity lookups |
| `jeeves/skills/obsidian-knowledge/SKILL.md` | Add Tier 0 (`_knowledge/` direct read) + meeting-aware search |

---

## Verification

1. Run `jeeves:vault-audit` → produces report with real folder names, file formats, frontmatter, transcription tool output format
2. Run `jeeves:process-meeting` on one transcript pair → produces: enhanced summary with stakeholder links, task entries, `_knowledge/log.md` entry + entity page updates
3. Check `_knowledge/` → index.md has new entry, log.md has ingestion record, entities/ has stakeholder page
4. Run `jeeves:meeting-prep` for a known attendee → finds structured meeting history + stakeholder profile from `_knowledge/entities/`
