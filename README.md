# Richfield Fertilisers — Multi-Agent Pricing System

AI-powered pricing, inventory, and procurement system for Richfield Fertilisers Pvt. Ltd., Nashik.  
Manages 14 × 25 kg bag grades across the Maharashtra distributor network.

Built with **Python + CrewAI + Groq (LLaMA 3.3-70b)** for the agent layer and **React + TypeScript + FastAPI** for the dashboard.

---

## What it does

Three specialised AI agents work in sequence:

| Agent | Role | Responsibility |
|-------|------|----------------|
| **Pricing Agent** | Head of Pricing | Sets optimal distributor rates, applies markdowns to slow movers, ensures GST compliance |
| **Inventory Agent** | Warehouse Manager | Classifies stock levels, calculates reorder quantities, flags overstock and dead stock |
| **Supplier Agent** | Procurement Manager | Scores and selects suppliers, raises purchase orders, flags supply risks |

Each agent uses the LLM both for reasoning (via CrewAI's ReAct loop) and for **per-product config optimisation** — dynamically adjusting margin targets, stock thresholds, and procurement strategy based on each product's individual state.

---

## Architecture

```
React Dashboard (Vite + TypeScript)
        │  REST + SSE
FastAPI Backend (api.py :8000)
        │
        ├── pricing_agent.py     ← CrewAI agent + 6 tools
        ├── inventory_agent.py   ← CrewAI agent + 6 tools
        └── supplier_agent.py    ← CrewAI agent + 6 tools
                │
        Shared in-memory state
        PRODUCTS / PRICE_HISTORY / REORDER_LOG / PO_LOG
```

**Agent handoff:**
```
Pricing Agent  →  flags slow movers, updates distributor rates
Inventory Agent →  classifies stock, writes REORDER_LOG (pending)
Supplier Agent  →  reads REORDER_LOG, raises POs, marks entries (ordered)
```

---

## Product Catalogue

14 × 25 kg bag grades, Maharashtra distributor price list w.e.f. 22-09-2025:

| ID | Grade | Distributor Rate | MRP |
|----|-------|-----------------|-----|
| RF-001 | 00-60-20 | ₹5,650 | ₹9,000 |
| RF-002 | 00:00:50 + 18% S | ₹2,475 | ₹4,400 |
| RF-003 | 00:52:34 | ₹4,650 | ₹7,900 |
| RF-004 | 12:61:00 | ₹3,875 | ₹5,700 |
| RF-005 | 13:00:45 | ₹3,400 | ₹5,800 |
| RF-006 | 13:40:13 | ₹3,750 | ₹5,800 |
| RF-007 | 16:08:24 + T.E. | ₹3,100 | ₹5,300 |
| RF-008 | Urea Phosphate | ₹3,675 | ₹5,500 |
| RF-009 | 19:19:19 + 1.5MgO + T.E. | ₹3,125 | ₹4,900 |
| RF-010 | 20:20:20 | ₹3,225 | ₹5,300 |
| RF-011 | Cal. Nitrate | ₹1,500 | ₹2,800 |
| RF-012 | Rich Magnesium Nitrate | ₹1,875 | ₹3,000 |
| RF-013 | Pot. Mag. Sulphate | ₹2,650 | ₹4,300 |
| RF-014 | Potassium Schonite | ₹2,025 | ₹3,300 |

---

## Pricing Formulas

```
production_cost  = per-product (set in PRODUCTS dict)
floor_rate       = production_cost / (1 - min_margin_pct / 100)
target_rate      = floor + (MRP - floor) × mrp_headroom_pct / 100

Healthy product  → recommended = max(current_rate, min(target, MRP))
Slow-moving      → recommended = max(floor, current_rate × (1 - markdown_pct / 100))

gst_amount       = recommended × 5%
distributor_pays = recommended + gst_amount
margin_pct       = (recommended - production_cost) / recommended × 100
```

---

## Inventory Formulas

```
daily_rate       = sales_last_30d / 30
days_of_stock    = stock_bags / daily_rate

reorder_qty      = (target_dos - current_dos) × daily_rate
safety_stock     = daily_rate × safety_stock_days
total_order      = reorder_qty + safety_stock  → rounded up to nearest 10
order_value      = total_order × production_cost
```

Stock status thresholds: Critical < 15d · Low < 30d · Healthy 30–90d · Overstock > 90d · Dead Stock > 180d + no sales

---

## Supplier Scoring

```
score = (0.40 × reliability / 10)
      + (0.30 × lead_time_fit)     ← 1.0 if fits before stockout, 0.3 if not
      + (0.30 × price_score)       ← 1.0 = cheapest, 0.0 = most expensive

order_value   = quantity × supplier.price_per_bag
gst_18pct     = order_value × 18%
total_payable = order_value + gst_18pct
```

6 suppliers mapped: Deepak Fertilisers (Pune), Coromandel (Hyderabad), SQM India (Mumbai), Haifa Chemicals (Chennai), K+S Minerals (Delhi), Yara India (Bangalore).

---

## File Structure

```
richfield-pricing-agent/
│
├── backend/
│   ├── pricing_agent.py      # Pricing agent — 6 tools, PRODUCTS data, CONFIG
│   ├── inventory_agent.py    # Inventory agent — 6 tools, INVENTORY_CONFIG
│   ├── supplier_agent.py     # Supplier agent — 6 tools, SUPPLIERS catalogue
│   ├── api.py                # FastAPI backend — REST endpoints + SSE stream
│   ├── requirements.txt      # Python dependencies
│   └── .env                  # API keys (not committed — see below)
│
└── frontend/
    ├── src/
    │   ├── App.tsx            # Root component — tab routing, SSE connection
    │   └── PricingAgentUI.tsx # Full dashboard — Pricing, Inventory, Supplier tabs
    ├── index.html
    ├── package.json
    └── tsconfig.json
```

---

## Setup

### Prerequisites
- Python 3.12
- Node.js 18+
- A free [Groq API key](https://console.groq.com)

### Backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

Create `backend/.env`:
```
GROQ_API_KEY=your_groq_api_key_here
CREWAI_TRACING_ENABLED=false
```

Start the API:
```bash
uvicorn api:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

---

## requirements.txt

```
crewai
crewai-tools
fastapi
uvicorn[standard]
sse-starlette
python-dotenv
litellm
groq
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/products` | All 14 products with pricing snapshots |
| GET | `/products/{id}` | Single product detail |
| POST | `/optimize` | Trigger Pricing Agent (streams via SSE) |
| POST | `/config` | Update pricing config live |
| GET | `/inventory` | Full inventory snapshot |
| POST | `/inventory/audit` | Trigger Inventory Agent |
| POST | `/inventory/config` | Update inventory thresholds |
| GET | `/suppliers` | Supplier catalogue + PO log + risk scan |
| POST | `/suppliers/procure` | Trigger Supplier Agent |
| GET | `/suggest/{product_id}` | LLM config suggestions for one product |
| GET | `/history` | Price change audit log |
| GET | `/stream` | SSE event stream (real-time UI updates) |

---

## Dashboard

Three tabs, all live-updating via SSE:

**💰 Pricing Agent** — distributor rate table, recommended rates, margin %, GST breakdown, configurable min margin and MRP headroom, per-product LLM config suggestions in detail pane

**📦 Inventory Agent** — stock levels with colour-coded DoS meters (red/orange/green/purple), reorder quantities and values, urgency labels, reorder log, configurable target DoS

**🚚 Supplier Agent** — supplier cards with reliability scores, lead times, MOQ, payment terms — supply risk flags (single source, lead time risk, low reliability) — purchase orders table with full GST breakdown

---

## LLM Usage

Each agent makes direct Groq API calls for per-product config optimisation (temperature 0.1, separate from the CrewAI reasoning loop):

| Agent | Tool | Optimises |
|-------|------|-----------|
| Pricing | `suggest_pricing_config` | min_margin_pct, mrp_headroom_pct, markdown_pct |
| Inventory | `suggest_inventory_config` | target_dos, safety_stock_days |
| Supplier | `suggest_supplier_strategy` | order_now, quantity_buffer_pct, prioritise, split_order |

Suggestions are per-product and non-destructive — they never overwrite global config and fall back silently to defaults if the LLM call fails.

---

## Notes

- All data is in-memory. Restart the backend to reset state.
- Replace `PRODUCTS` dict with a real database for production use.
- Replace mock `last_sale_date` and `sales_last_30d` with live sales system data.
- The 60% production cost estimate per product should be replaced with actual cost data from your ERP.

---

*Built for Richfield Fertilisers Pvt. Ltd., Nashik — Maharashtra fertiliser distribution network*
