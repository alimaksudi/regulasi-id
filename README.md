# regulasi-id

Open, AI-native Indonesian financial regulatory platform. Structured database of OJK (Otoritas Jasa Keuangan) regulations with full-text search, amendment tracking, and an MCP server that gives Claude grounded access to Indonesian financial law.

**Live:** https://regulasi.id (planned) | **MCP:** Railway (planned)

---

## What It Solves

OJK publishes hundreds of POJK, SEOJK, and KEOJK documents across 6 regulatory sectors — all as PDFs on jdih.ojk.go.id. Compliance officers at banks and fintechs spend days cross-referencing these to answer basic questions. No structured, searchable, AI-accessible database exists.

regulasi-id solves three problems:

| Audience | Problem | Solution |
|----------|---------|---------|
| Compliance teams | Cross-referencing 5 PDFs to understand one requirement | Consolidated regulation view with amendment diffs |
| Fintech founders | "What licenses do I need for a P2P lending platform?" | Compliance checklist tool per sector/business type |
| AI assistants (Claude) | Hallucinating OJK regulations | MCP server with exact article citations |

---

## Quick Start

```bash
# Web app (from apps/web/)
npm install && npm run dev       # http://localhost:3000

# MCP server (from apps/mcp-server/)
pip install -r requirements.txt
python server.py                 # http://localhost:8000/mcp

# Connect to Claude Code
claude mcp add --transport http regulasi-id http://localhost:8000/mcp

# Data pipeline (from project root)
python -m scripts.worker.run discover --sectors perbankan,fintech
python -m scripts.worker.run process --batch-size 10
```

---

## Architecture

```
Browser / Claude Desktop
        │
        ▼
Next.js Web App (Vercel)     FastMCP Server (Railway)
        │                           │
        └──────────┬────────────────┘
                   ▼
          Supabase (PostgreSQL)
          - works (regulations)
          - document_nodes (articles)
          - abstracts + faqs
          - search_regulations() RPC
                   │
                   ▼
        Data Pipeline (Python)
        jdih.ojk.go.id → PDF → DB
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for full detail.

---

## MCP Tools

```
search_regulations(query, sector?, type?, year_from?, status?, limit?)
get_article(regulation_type, number, year, article_number)
get_regulation_status(regulation_type, number, year)
get_compliance_checklist(sector, business_type?)
list_regulations(sector?, type?, year?, status?, page?)
ping()
```

---

## OJK Regulatory Sectors

| Code | Sector |
|------|--------|
| `perbankan` | Banking |
| `pasar-modal` | Capital Markets |
| `iknb` | Non-Bank Financial Institutions |
| `fintech` | Financial Technology |
| `dana-pensiun` | Pension Funds |
| `perasuransian` | Insurance |

## Regulation Types

| Code | Full Name | Authority Level |
|------|-----------|----------------|
| `UU` | Undang-Undang | Highest |
| `PP` | Peraturan Pemerintah | High |
| `PERPRES` | Peraturan Presiden | High |
| `POJK` | Peraturan OJK | Primary OJK |
| `SEOJK` | Surat Edaran OJK | Circular/guidance |
| `KEOJK` | Keputusan OJK | Decision |

---

## Repository Structure

```
regulasi-id/
├── apps/
│   ├── web/               — Next.js frontend (Vercel)
│   └── mcp-server/        — Python FastMCP server (Railway)
├── packages/
│   └── supabase/
│       └── migrations/    — SQL migration files
├── scripts/               — Data pipeline (crawler → parser → loader)
│   ├── crawler/           — jdih.ojk.go.id scraper
│   ├── parser/            — PDF → structured nodes
│   ├── loader/            — DB import
│   ├── worker/            — Orchestration CLI
│   └── agent/             — AI verification
├── docs/                  — Technical specifications
├── CLAUDE.md              — Primary developer reference
└── ARCHITECTURE.md        — System architecture
```

---

## License

MIT — data from OJK is public information.
