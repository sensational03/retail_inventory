"""
Richfield Fertilisers — Pricing Agent API
==========================================
FastAPI backend with REST endpoints + SSE real-time stream.

Run:
    uvicorn api:app --reload --port 8000
"""

import os
import json
import asyncio
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from pricing_agent import (
    PRODUCTS,
    PRICE_HISTORY,
    CONFIG,
    run_pricing_optimization,
    update_config,
    days_since,
    suggest_pricing_config,
)
from inventory_agent import (
    INVENTORY_CONFIG,
    REORDER_LOG,
    classify_stock_status,
    run_inventory_audit,
    update_inventory_config,
    suggest_inventory_config,
)
from supplier_agent import (
    SUPPLIERS,
    PO_LOG,
    run_supplier_procurement,
    suggest_supplier_strategy,
)

load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# In-memory state
# ──────────────────────────────────────────────────────────────────────────────

activity_log:  list[dict] = []
active_jobs:   dict[str, str] = {}
sse_clients:   list[asyncio.Queue] = []


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def broadcast(event_type: str, data: dict):
    payload = {"type": event_type, "data": data, "timestamp": utcnow()}
    activity_log.append({
        "tag":       event_type,
        "message":   data.get("message", ""),
        "timestamp": utcnow(),
    })
    if len(activity_log) > 300:
        activity_log.pop(0)
    for q in sse_clients:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Richfield Pricing Agent API",
    description="Pricing optimisation for Richfield Fertilisers Pvt. Ltd.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────────

class OptimizeRequest(BaseModel):
    product_ids:    Optional[list[str]] = None
    min_margin_pct: Optional[int]       = None   # override config at runtime


class PriceOverrideRequest(BaseModel):
    product_id: str
    new_price:  float
    reason:     Optional[str] = "Manual override"


class ConfigUpdateRequest(BaseModel):
    min_margin_pct:   Optional[int] = None
    slow_moving_days: Optional[int] = None
    mrp_headroom_pct: Optional[int] = None


# ──────────────────────────────────────────────────────────────────────────────
# Helper — build product snapshot for API responses
# ──────────────────────────────────────────────────────────────────────────────

def build_product_snapshot(product_id: str) -> dict:
    p = PRODUCTS.get(product_id)
    if not p:
        return {}

    current_rate = p["distributor_rate"]   # current rate Richfield charges distributors
    mrp          = p["mrp"]
    gst_pct      = p["gst_pct"]
    min_margin      = CONFIG["min_margin_pct"]
    production_cost = p["production_cost"]   # per-product actual cost
    days_no_sale    = days_since(p["last_sale_date"])
    is_slow         = days_no_sale >= CONFIG["slow_moving_days"] or p["sales_last_30d"] == 0

    # Minimum rate Richfield must charge to meet margin requirement
    min_rate = round(production_cost / (1 - min_margin / 100), 2)

    # Recommended distributor rate
    if is_slow:
        rec    = round(current_rate * (1 - CONFIG["markdown_pct"] / 100), 2)
        rec    = max(min_rate, min(rec, mrp))
        status = "slow_moving"
        reason = f"Slow-moving ({days_no_sale}d no sale) → markdown {CONFIG['markdown_pct']}% on distributor rate"
    else:
        headroom = CONFIG["mrp_headroom_pct"] / 100
        target   = round(min_rate + (mrp - min_rate) * headroom, 2)
        # Healthy products: never recommend below current rate (only optimise upward)
        rec      = max(current_rate, min(target, mrp))
        status   = "healthy"
        reason   = f"Active product → targeting {CONFIG['mrp_headroom_pct']}% of headroom between cost floor and MRP"

    rec = round(max(min_rate, min(rec, mrp)), 2)

    # Richfield margin on current rate
    margin_rs   = round(current_rate - production_cost, 2)
    margin_pct  = round((margin_rs / current_rate) * 100, 1) if current_rate > 0 else 0
    # Richfield margin on recommended rate
    rec_margin  = round(((rec - production_cost) / rec) * 100, 1) if rec > 0 else 0
    gst_amount  = round(rec * gst_pct / 100, 2)
    distributor_pays = round(rec + gst_amount, 2)

    # Effective margin after advance cash discount (Richfield gives 7% off to early-paying distributors)
    adv_discount = round(rec * CONFIG["cash_discount_tiers"]["advance"] / 100, 2)
    eff_margin   = round(((rec - adv_discount - production_cost) / rec) * 100, 1)

    dos = round((p["stock_bags"] / p["sales_last_30d"] * 30), 1) if p["sales_last_30d"] > 0 else 999

    return {
        "product_id":              product_id,
        "name":                    p["name"],
        "pack":                    p["pack"],
        "category":                p["category"],
        "production_cost":         production_cost,
        "mrp":                     mrp,
        "current_rate":            current_rate,
        "recommended_rate":        rec,
        "min_allowed":             min_rate,
        "gst_pct":                 gst_pct,
        "gst_amount":              gst_amount,
        "distributor_pays_incl_gst": distributor_pays,
        "margin_rs":               margin_rs,
        "margin_pct":              margin_pct,
        "recommended_margin_pct":  rec_margin,
        "effective_margin_pct":    eff_margin,
        "stock_bags":              p["stock_bags"],
        "sales_last_30d":          p["sales_last_30d"],
        "days_since_last_sale":    days_no_sale,
        "days_of_stock":           dos,
        "is_slow_moving":          is_slow,
        "status":                  status,
        "reason":                  reason,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Additional schemas
# ──────────────────────────────────────────────────────────────────────────────

class InventoryConfigRequest(BaseModel):
    target_dos:              Optional[int] = None
    critical_dos_threshold:  Optional[int] = None
    overstock_dos_threshold: Optional[int] = None
    safety_stock_days:       Optional[int] = None


class RunInventoryRequest(BaseModel):
    product_ids: Optional[list[str]] = None


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "service": "Richfield Pricing Agent API",
        "version": "2.0.0",
        "products": len(PRODUCTS),
        "config":   CONFIG,
    }


@app.get("/products")
def get_all_products():
    """Return all 25 kg bag grades with current and recommended prices."""
    result = [build_product_snapshot(pid) for pid in PRODUCTS]
    return {"products": result, "count": len(result), "config": CONFIG}


@app.get("/products/{product_id}")
def get_product(product_id: str):
    snap = build_product_snapshot(product_id)
    if not snap:
        raise HTTPException(status_code=404, detail=f"{product_id} not found")
    return snap


@app.get("/history")
def get_history():
    return {"history": list(reversed(PRICE_HISTORY)), "count": len(PRICE_HISTORY)}


@app.get("/activity")
def get_activity():
    return {"activity": list(reversed(activity_log[-50:])), "count": len(activity_log)}


@app.get("/config")
def get_config():
    return CONFIG


@app.post("/config")
def set_config(req: ConfigUpdateRequest):
    """Update global pricing configuration (min margin %, slow-moving threshold)."""
    update_config(
        min_margin_pct=req.min_margin_pct,
        slow_moving_days=req.slow_moving_days,
        mrp_headroom_pct=req.mrp_headroom_pct,
    )
    broadcast("info", {"message": f"⚙ Config updated: {CONFIG}"})
    return {"status": "ok", "config": CONFIG}


@app.post("/optimize")
async def optimize(req: OptimizeRequest, background_tasks: BackgroundTasks):
    """Trigger the Pricing Agent. Streams progress via GET /stream."""
    import uuid
    job_id      = str(uuid.uuid4())[:8]
    product_ids = req.product_ids or list(PRODUCTS.keys())

    # Apply runtime margin override if provided
    if req.min_margin_pct is not None:
        update_config(min_margin_pct=req.min_margin_pct)

    invalid = [pid for pid in product_ids if pid not in PRODUCTS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown product IDs: {invalid}")

    active_jobs[job_id] = "running"
    background_tasks.add_task(_run_agent_job, job_id, product_ids)

    broadcast("agent", {
        "message": f"🌿 Job {job_id} started — {len(product_ids)} product(s) | min margin: {CONFIG['min_margin_pct']}%"
    })
    return {"job_id": job_id, "status": "running", "product_ids": product_ids}


async def _run_agent_job(job_id: str, product_ids: list[str]):
    try:
        broadcast("info", {"message": f"→ Initialising CrewAI crew (job {job_id})"})

        # Stream tool-call previews before the real agent runs
        for pid in product_ids:
            p = PRODUCTS.get(pid, {})
            broadcast("info",  {"message": f"→ fetch_product_data(\"{pid}\")  [{p.get('name', '')}]"})
            await asyncio.sleep(0.25)
            broadcast("info",  {"message": f"→ fetch_demand_and_slow_moving_status(\"{pid}\")"})
            await asyncio.sleep(0.25)
            broadcast("info",  {"message": f"→ calculate_richfield_price(\"{pid}\")"})
            await asyncio.sleep(0.25)
            broadcast("info",  {"message": f"→ apply_cash_discount(\"{pid}\", \"advance\")"})
            await asyncio.sleep(0.2)

        # Run CrewAI in thread (synchronous)
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_pricing_optimization, product_ids)

        # Collect updates and broadcast
        updates = []
        for pid in product_ids:
            snap = build_product_snapshot(pid)
            old  = snap["current_rate"]
            rec  = snap["recommended_rate"]
            diff_pct = abs((rec - old) / old * 100) if old > 0 else 0

            if diff_pct > 2:
                PRODUCTS[pid]["distributor_rate"] = rec
                entry = {
                    "product_id":   pid,
                    "name":         snap["name"],
                    "old_rate":     old,
                    "new_rate":     rec,
                    "adj_pct":      round((rec - old) / old * 100, 1),
                    "margin_pct":   snap["recommended_margin_pct"],
                    "gst_amount":   snap["gst_amount"],
                    "farmer_price": snap["farmer_price_incl_gst"],
                    "status":       snap["status"],
                    "timestamp":    utcnow(),
                    "job_id":       job_id,
                }
                PRICE_HISTORY.append(entry)
                broadcast("update", {
                    "message": f"✓ {pid} ₹{old:,.0f} → ₹{rec:,.0f} ({entry['adj_pct']:+.1f}%) | Richfield margin {snap['recommended_margin_pct']}% | distributor pays ₹{snap['distributor_pays_incl_gst']:,.0f} incl. GST",
                    "entry":   entry,
                })
            else:
                broadcast("info", {"message": f"  {pid} [{snap['name']}] — no change"})

            updates.append(build_product_snapshot(pid))

        active_jobs[job_id] = "complete"
        broadcast("agent", {
            "message": f"✅ Job {job_id} complete — {len(product_ids)} product(s) processed",
            "updates": updates,
        })

    except Exception as e:
        active_jobs[job_id] = "error"
        broadcast("error", {"message": f"❌ Job {job_id} failed: {str(e)}"})


@app.post("/override")
def price_override(req: PriceOverrideRequest):
    """Manually set a selling price (bypasses agent, validates guardrails)."""
    p = PRODUCTS.get(req.product_id)
    if not p:
        raise HTTPException(status_code=404, detail=f"{req.product_id} not found")

    production_cost = p["production_cost"]
    min_rate = round(production_cost / (1 - CONFIG["min_margin_pct"] / 100), 2)
    if req.new_price < min_rate:
        raise HTTPException(status_code=400,
            detail=f"₹{req.new_price} is below min margin floor (₹{min_rate})")
    if req.new_price > p["mrp"]:
        raise HTTPException(status_code=400,
            detail=f"₹{req.new_price} exceeds MRP ceiling (₹{p['mrp']})")

    old = p["distributor_rate"]
    PRODUCTS[req.product_id]["distributor_rate"] = req.new_price
    entry = {
        "product_id": req.product_id,
        "name":       p["name"],
        "old_price":  old,
        "new_price":  req.new_price,
        "adj_pct":    round((req.new_price - old) / old * 100, 1),
        "reason":     req.reason,
        "source":     "manual_override",
        "timestamp":  utcnow(),
    }
    PRICE_HISTORY.append(entry)
    broadcast("warn", {"message": f"⚠ Manual override: {req.product_id} ₹{old:,.0f} → ₹{req.new_price:,.0f} — {req.reason}"})
    return {"status": "ok", "entry": entry}


# ──────────────────────────────────────────────────────────────────────────────
# Inventory endpoints
# ──────────────────────────────────────────────────────────────────────────────

def build_inventory_snapshot() -> dict:
    """Build full inventory snapshot for all products."""
    rows = []
    total_bags  = 0
    total_value = 0.0
    status_counts = {"critical": 0, "low": 0, "healthy": 0, "overstock": 0, "dead_stock": 0}

    for pid, p in PRODUCTS.items():
        stock     = p["stock_bags"]
        sales_30d = p["sales_last_30d"]
        daily     = round(sales_30d / 30, 2) if sales_30d > 0 else 0.0
        dos       = round(stock / daily, 1) if daily > 0 else 999
        status    = classify_stock_status(dos)
        days_no_sale = days_since(p["last_sale_date"])
        is_slow   = days_no_sale >= CONFIG["slow_moving_days"] or sales_30d == 0

        # Reorder qty calc
        if sales_30d > 0:
            target_dos   = INVENTORY_CONFIG["target_dos"]
            safety_days  = INVENTORY_CONFIG["safety_stock_days"]
            reorder_qty  = max(0, (target_dos - dos) * daily)
            safety_stock = daily * safety_days
            total_order  = int(((reorder_qty + safety_stock) // 10 + 1) * 10)
            order_value  = round(total_order * p["production_cost"], 2)
        else:
            total_order = 0
            order_value = 0

        inv_value = round(stock * p["distributor_rate"], 2)
        total_bags  += stock
        total_value += inv_value
        status_counts[status] += 1

        # Urgency
        if dos < INVENTORY_CONFIG["critical_dos_threshold"]:
            urgency = "URGENT"
        elif dos < INVENTORY_CONFIG["low_dos_threshold"]:
            urgency = "HIGH"
        elif dos < INVENTORY_CONFIG["target_dos"]:
            urgency = "MEDIUM"
        else:
            urgency = "LOW"

        rows.append({
            "product_id":           pid,
            "name":                 p["name"],
            "category":             p["category"],
            "stock_bags":           stock,
            "sales_last_30d":       sales_30d,
            "daily_sales_rate":     daily,
            "days_of_stock":        dos,
            "stock_status":         status,
            "inventory_value_rs":   inv_value,
            "days_since_last_sale": days_no_sale,
            "is_slow_moving":       is_slow,
            "reorder_qty":          total_order,
            "reorder_value_rs":     order_value,
            "urgency":              urgency,
        })

    cap      = INVENTORY_CONFIG["warehouse_capacity_bags"]
    util_pct = round(total_bags / cap * 100, 1)

    return {
        "products":            rows,
        "total_bags":          total_bags,
        "total_value_rs":      round(total_value, 2),
        "warehouse_capacity":  cap,
        "utilisation_pct":     util_pct,
        "status_counts":       status_counts,
        "reorder_log":         list(reversed(REORDER_LOG[-20:])),
        "config":              INVENTORY_CONFIG,
    }


@app.get("/inventory")
def get_inventory():
    """Full inventory snapshot for all products."""
    return build_inventory_snapshot()


@app.post("/inventory/config")
def set_inventory_config(req: InventoryConfigRequest):
    update_inventory_config(
        target_dos=req.target_dos,
        critical_dos_threshold=req.critical_dos_threshold,
        overstock_dos_threshold=req.overstock_dos_threshold,
        safety_stock_days=req.safety_stock_days,
    )
    broadcast("info", {"message": f"⚙ Inventory config updated: {INVENTORY_CONFIG}"})
    return {"status": "ok", "config": INVENTORY_CONFIG}


@app.post("/inventory/audit")
async def run_inventory(req: RunInventoryRequest, background_tasks: BackgroundTasks):
    """Trigger the Inventory Agent. Streams progress via /stream."""
    import uuid
    job_id      = str(uuid.uuid4())[:8]
    product_ids = req.product_ids or list(PRODUCTS.keys())

    invalid = [pid for pid in product_ids if pid not in PRODUCTS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown product IDs: {invalid}")

    active_jobs[job_id] = "running"
    background_tasks.add_task(_run_inventory_job, job_id, product_ids)

    broadcast("agent", {"message": f"📦 Inventory audit started (job {job_id}) — {len(product_ids)} products"})
    return {"job_id": job_id, "status": "running"}


async def _run_inventory_job(job_id: str, product_ids: list):
    try:
        broadcast("info", {"message": f"→ Initialising inventory crew (job {job_id})"})
        for pid in product_ids:
            broadcast("info", {"message": f"→ get_inventory_status('{pid}')"})
            await asyncio.sleep(0.2)

        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_inventory_audit, product_ids)

        active_jobs[job_id] = "complete"
        broadcast("agent", {"message": f"✅ Inventory audit complete (job {job_id})"})
    except Exception as e:
        active_jobs[job_id] = "error"
        broadcast("error", {"message": f"❌ Inventory job {job_id} failed: {str(e)}"})


# ──────────────────────────────────────────────────────────────────────────────
# Supplier endpoints
# ──────────────────────────────────────────────────────────────────────────────

def build_supplier_snapshot() -> dict:
    """Build full supplier + PO snapshot."""
    supplier_list = []
    for sid, sup in SUPPLIERS.items():
        supplier_list.append({
            "supplier_id":       sid,
            "name":              sup["name"],
            "location":          sup["location"],
            "reliability_score": sup["reliability_score"],
            "lead_time_days":    sup["lead_time_days"],
            "moq_bags":          sup["moq_bags"],
            "payment_terms":     sup["payment_terms"],
            "products_supplied": sup["products_supplied"],
            "product_count":     len(sup["products_supplied"]),
            "contact":           sup["contact"],
        })

    # Supply risk scan (direct, no LLM)
    risks = []
    for pid, p in PRODUCTS.items():
        sups = [s for s in SUPPLIERS.values() if pid in s["products_supplied"]]
        if not sups:
            risks.append({"product_id": pid, "risk_type": "NO_SUPPLIER",    "severity": "CRITICAL"})
        elif len(sups) == 1:
            risks.append({"product_id": pid, "risk_type": "SINGLE_SOURCE",  "severity": "HIGH"})

    pending_reorders = [r for r in REORDER_LOG if r.get("status") == "pending"]
    total_po_value   = sum(po.get("total_payable_rs", 0) for po in PO_LOG)

    return {
        "suppliers":         supplier_list,
        "supplier_count":    len(supplier_list),
        "purchase_orders":   list(reversed(PO_LOG[-30:])),
        "po_count":          len(PO_LOG),
        "total_po_value_rs": round(total_po_value, 2),
        "pending_reorders":  pending_reorders,
        "supply_risks":      risks,
    }


@app.get("/suppliers")
def get_suppliers():
    """Full supplier catalogue + PO log + risk scan."""
    return build_supplier_snapshot()


@app.post("/suppliers/procure")
async def run_procurement(background_tasks: BackgroundTasks):
    """Trigger the Supplier Agent to process pending reorders."""
    import uuid
    job_id = str(uuid.uuid4())[:8]

    pending = [r for r in REORDER_LOG if r.get("status") == "pending"]
    if not pending:
        return {"message": "No pending reorders — run inventory audit first", "job_id": None}

    active_jobs[job_id] = "running"
    background_tasks.add_task(_run_supplier_job, job_id)

    broadcast("agent", {"message": f"🚚 Supplier procurement started (job {job_id}) — {len(pending)} pending reorders"})
    return {"job_id": job_id, "status": "running", "pending_reorders": len(pending)}


async def _run_supplier_job(job_id: str):
    try:
        broadcast("info", {"message": f"→ Initialising supplier crew (job {job_id})"})
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_supplier_procurement)

        active_jobs[job_id] = "complete"
        po_count = len([po for po in PO_LOG if po.get("status") == "raised"])
        broadcast("agent", {"message": f"✅ Procurement complete (job {job_id}) — {po_count} POs raised"})
    except Exception as e:
        active_jobs[job_id] = "error"
        broadcast("error", {"message": f"❌ Supplier job {job_id} failed: {str(e)}"})



@app.get("/suggest/{product_id}")
def suggest_config(product_id: str):
    """
    Ask the LLM to suggest optimised config parameters for a specific product.
    Returns pricing, inventory, and supplier strategy suggestions.
    Useful for previewing what the agents will use before running them.
    """
    if product_id not in PRODUCTS:
        raise HTTPException(status_code=404, detail=f"{product_id} not found")

    snap   = build_product_snapshot(product_id)
    inv    = build_inventory_snapshot()
    inv_p  = next((p for p in inv["products"] if p["product_id"] == product_id), {})
    dos    = inv_p.get("days_of_stock", 999)

    pricing_raw  = suggest_pricing_config.run(product_id)
    inventory_raw = suggest_inventory_config.run(product_id)
    supplier_raw  = suggest_supplier_strategy.run(product_id, dos)

    try: pricing_sug  = json.loads(pricing_raw)
    except: pricing_sug  = {"error": pricing_raw}
    try: inventory_sug = json.loads(inventory_raw)
    except: inventory_sug = {"error": inventory_raw}
    try: supplier_sug  = json.loads(supplier_raw)
    except: supplier_sug  = {"error": supplier_raw}

    return {
        "product_id":      product_id,
        "product_name":    PRODUCTS[product_id]["name"],
        "pricing":         pricing_sug,
        "inventory":       inventory_sug,
        "supplier":        supplier_sug,
        "current_config":  CONFIG,
        "current_inv_config": INVENTORY_CONFIG,
    }


# ──────────────────────────────────────────────────────────────────────────────
# SSE stream
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/stream")
async def stream_events(request: Request):
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    sse_clients.append(queue)

    async def generator():
        yield {"data": json.dumps({"type": "connected", "message": "Richfield Pricing Agent stream connected"})}
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"data": json.dumps(event)}
                except asyncio.TimeoutError:
                    yield {"data": json.dumps({"type": "ping", "timestamp": utcnow()})}
        finally:
            if queue in sse_clients:
                sse_clients.remove(queue)

    return EventSourceResponse(generator())


# ──────────────────────────────────────────────────────────────────────────────
# Run directly
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
