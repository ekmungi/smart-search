# Session Start Prompt — Knowledge System Build

> Paste this entire prompt at the start of a new Claude Code session.
> It provides full context for building the LLM Wiki knowledge system.

---

## Prompt

```
You are continuing work on building an LLM Wiki knowledge system for my Obsidian vault.
This follows Karpathy's LLM Wiki pattern (persistent, compounding wiki maintained by LLMs
instead of RAG). Full context is in two files you should read FIRST:

1. Read `docs/knowledge-system-blueprint.md` in the smart-search repo — this is the
   comprehensive blueprint with my actual vault structure, the adapted _knowledge/
   architecture, all design decisions, and the phased implementation plan.

2. Read `docs/llm-wiki-karpathy-with-summary.md` in the smart-search repo — this is
   Karpathy's original gist plus video implementation summary.

## My Setup

- **Obsidian vault** on Windows machine (path in ~/.claude/jeeves/memory/preferences.md)
- **Jeeves** (ekmungi/jeeves) — Claude Code plugin with 8 agents + 22 skills for AI Product
  Management in healthcare/medical devices (Olympus)
- **Smart-search** (ekmungi/smart-search) — local semantic search engine, ~130MB RAM,
  hybrid BM25+vector+reranking, 11 MCP tools, Tauri desktop app
- **PARA structure**: Projects/ (active work), Areas/ (ongoing responsibilities),
  Resources/ (reference material), Archives/ (frozen)

## Vault Structure Highlights

- **Meetings**: Resources/Meetings/FY27/Q1/ — meeting notes + transcripts/ subfolder.
  Olympus fiscal year: April→March. FY27 = Apr 2026→Mar 2027.
- **Stakeholders**: Resources/Stakeholders/ — one MD per stakeholder (info, preferences,
  communication style). NOT yet linked to meetings.
- **Products/Versions/Features**: Linked hierarchy in Resources. Feature→Version→Product.
- **Custom transcription tool**: Outputs paired files (notes MD + linked transcript MD).

## What We're Building

A `_knowledge/` folder at vault root implementing Karpathy's wiki layer:

```
_knowledge/
├── index.md          ← Master catalog (LLM reads FIRST on every query)
├── log.md            ← Append-only operation history
├── SCHEMA.md         ← Conventions and templates
├── hot.md            ← Rolling ~500-word context cache
├── sources/          ← Per-source ingestion records
│   └── meetings/     ← "What did the wiki learn from this meeting?"
├── entities/         ← Typed: products/, people/, companies/, regulations/, studies/
├── concepts/         ← Abstract topic pages
└── analysis/         ← Filed query results ("explorations add up")
```

## Phased Plan

**Phase 1 (NOW): vault-audit** — Build `jeeves/skills/vault-audit/SKILL.md`. Walk the
vault, discover actual folder names, file formats, frontmatter conventions, transcription
tool output format. This MUST complete before anything else.

**Phase 2: Scaffold** — Create `_knowledge/` structure with index.md, log.md, SCHEMA.md,
hot.md, and all subdirectories.

**Phase 3: process-meeting** — Build `jeeves/skills/process-meeting/SKILL.md`. Karpathy's
Ingest operation for meetings. Takes notes MD + transcript → produces 3 outputs:
(1) Enhanced meeting note with frontmatter + stakeholder/project wiki-links + related
meetings discovery, (2) Tasks via task-creator, (3) Knowledge entries (source page +
entity pages + concept pages + index/log updates + hot.md).

**Phase 4: Query enhancement** — Update obsidian-knowledge with Tier 0 (read index.md
first → entity pages → smart-search → Grep). Update meeting-prep to use _knowledge/
entity profiles.

**Phase 5: Expand** — Process stakeholders, products, literature, interviews.

**Phase 6: Lint** — Periodic health checks.

## Key Design Decisions

- Search: smart-search (keep, 130MB RAM vs QMD's 4-6GB)
- Entity pages: typed subdirectories (entities/products/, entities/people/, etc.)
- Source pages: yes, in sources/ — creates the cross-reference graph link
- Analysis pages: yes — queries compound into knowledge
- hot.md: yes — rolling context cache for session orientation
- Vault-audit first: always discover before assuming

## Start Phase 1

Please read the two reference documents mentioned above, then build the vault-audit skill.
The skill should be a Jeeves skill file at `jeeves/skills/vault-audit/SKILL.md` and should
also update `jeeves/CLAUDE.md` to add vault-audit to the routing table.

After building the skill, I'll run it on my vault and share the results so we can proceed
to Phase 2.
```

---

## Notes for Using This Prompt

- **Both repos must be accessible** in the session (smart-search and jeeves)
- The prompt tells the agent to read the blueprint and Karpathy gist first
- It starts with Phase 1 (vault-audit) — adjust the "Start Phase X" section if resuming
  from a later phase
- After vault-audit produces results, paste those results into the session so the agent
  can adapt Phase 2+ to the real vault structure
- The `_knowledge/` structure may evolve based on vault-audit findings
