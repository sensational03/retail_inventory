# Changelog

All notable changes to the **Richfield Fertilisers — Multi-Agent Pricing System** are documented here.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) conventions.

---

## [Unreleased]

### Planned
- PostgreSQL / MongoDB integration to replace in-memory state
- Sales trend charts and historical pricing graphs
- Email / WhatsApp notifications for critical stock levels
- Marathi / Hindi UI localisation
- Unit and integration tests for all three agents

---

## [1.0.0] — 2025-09-22

### Added
- **Pricing Agent** — sets optimal distributor rates, applies markdowns to slow-moving stock, enforces GST compliance across all 14 × 25 kg bag grades
- **Inventory Agent** — classifies stock levels (Critical / Low / Healthy / Overstock / Dead Stock), calculates reorder quantities with configurable Days-of-Stock targets
- **Supplier Agent** — scores and selects from 6 suppliers (Deepak Fertilisers, Coromandel, SQM India, Haifa Chemicals, K+S Minerals, Yara India), raises purchase orders, flags supply risks
- **FastAPI backend** (`api.py`) exposing 12 REST + SSE endpoints on port 8000
- **React + TypeScript dashboard** (Vite, port 5173) with three live-updating tabs: Pricing, Inventory, Supplier
- **CrewAI ReAct loop** for multi-step agent reasoning using Groq LLaMA 3.3-70b
- **Per-product LLM config optimisation** — dynamic adjustment of margin targets, stock thresholds, and procurement strategy
- **SSE streaming** for real-time agent log output in the UI
- **GST compliance** — 5% GST on distributor rates; 18% GST on supplier purchase orders
- Product catalogue: 14 grades (RF-001 to RF-014), Maharashtra distributor price list effective 22-Sep-2025
- Supplier scoring formula (40% reliability, 30% lead-time fit, 30% price score)
- MIT licence

### Architecture
```
React Dashboard (Vite + TypeScript)
        |  REST + SSE
FastAPI Backend (api.py :8000)
        |
        |-- pricing_agent.py     <- CrewAI agent + 6 tools
        |-- inventory_agent.py   <- CrewAI agent + 6 tools
        +-- supplier_agent.py    <- CrewAI agent + 6 tools
                |
        Shared in-memory state
        PRODUCTS / PRICE_HISTORY / REORDER_LOG / PO_LOG
```

---

## Versioning

This project uses [Semantic Versioning](https://semver.org/):

- **MAJOR** — breaking API or agent-interface changes
- **MINOR** — new features, new agents, or new dashboard tabs
- **PATCH** — bug fixes, documentation updates, dependency bumps
