"""
Richfield Fertilisers Pvt. Ltd. — Supplier Agent
=================================================
Stack : Python + CrewAI + Groq (LLaMA 3.3-70b)
Scope : 25 kg bag grades, raw material / supplier management

Supplier agent responsibilities
────────────────────────────────
1. Maintain supplier catalogue with lead times, MOQs, reliability scores
2. For each reorder recommendation from inventory agent:
   - Select best supplier (price × reliability × lead time)
   - Calculate total order value
   - Check if lead time fits before stockout date
   - Flag supply risks (single-source products, low-reliability suppliers)
3. Generate purchase orders with payment terms
4. Track supplier performance over time
"""

import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

try:
    from groq import Groq as _Groq
    _groq_client = _Groq(api_key=os.getenv('GROQ_API_KEY', ''))
except Exception:
    print("nooo — Groq client failed to initialize, supplier strategy tool will use fallback logic")
    _groq_client = None

from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool

from pricing_agent import PRODUCTS, days_since
from inventory_agent import REORDER_LOG, INVENTORY_CONFIG



# ──────────────────────────────────────────────────────────────────────────────
# Supplier Catalogue
# ──────────────────────────────────────────────────────────────────────────────
# reliability_score : 1–10 (10 = always on time, correct qty, good quality)
# lead_time_days    : average days from order to delivery at Nashik warehouse
# moq_bags          : minimum order quantity in bags
# price_per_bag     : raw material cost per 25 kg bag (what Richfield pays supplier)
# payment_terms     : advance / net_15 / net_30
# products_supplied : list of RF product IDs this supplier can supply

SUPPLIERS = {
    "SUP-001": {
        "name":              "Deepak Fertilisers Ltd.",
        "location":          "Pune, Maharashtra",
        "reliability_score": 9.2,
        "lead_time_days":    7,
        "moq_bags":          50,
        "payment_terms":     "net_30",
        "products_supplied": ["RF-001", "RF-003", "RF-004"],
        "price_per_bag": {
            "RF-001": 3500.0,
            "RF-003": 2850.0,
            "RF-004": 2400.0,
        },
        "contact":           "orders@deepakfert.com",
    },
    "SUP-002": {
        "name":              "Coromandel International",
        "location":          "Hyderabad, Telangana",
        "reliability_score": 8.7,
        "lead_time_days":    10,
        "moq_bags":          100,
        "payment_terms":     "net_15",
        "products_supplied": ["RF-004", "RF-005", "RF-006", "RF-007"],
        "price_per_bag": {
            "RF-004": 2450.0,
            "RF-005": 2150.0,
            "RF-006": 2380.0,
            "RF-007": 1950.0,
        },
        "contact":           "supply@coromandel.com",
    },
    "SUP-003": {
        "name":              "SQM India (Speciality Nutrients)",
        "location":          "Mumbai, Maharashtra",
        "reliability_score": 9.5,
        "lead_time_days":    5,
        "moq_bags":          25,
        "payment_terms":     "advance",
        "products_supplied": ["RF-008", "RF-009", "RF-010"],
        "price_per_bag": {
            "RF-008": 2350.0,
            "RF-009": 1980.0,
            "RF-010": 2050.0,
        },
        "contact":           "india@sqm.com",
    },
    "SUP-004": {
        "name":              "Haifa Chemicals India",
        "location":          "Chennai, Tamil Nadu",
        "reliability_score": 8.1,
        "lead_time_days":    14,
        "moq_bags":          200,
        "payment_terms":     "net_30",
        "products_supplied": ["RF-011", "RF-012"],
        "price_per_bag": {
            "RF-011": 950.0,
            "RF-012": 1150.0,
        },
        "contact":           "orders@haifa.in",
    },
    "SUP-005": {
        "name":              "K+S Minerals India",
        "location":          "Delhi",
        "reliability_score": 7.8,
        "lead_time_days":    12,
        "moq_bags":          100,
        "payment_terms":     "net_15",
        "products_supplied": ["RF-013", "RF-014"],
        "price_per_bag": {
            "RF-013": 1650.0,
            "RF-014": 1280.0,
        },
        "contact":           "sales@ks-india.com",
    },
    "SUP-006": {
        "name":              "Yara India Pvt. Ltd.",
        "location":          "Bangalore, Karnataka",
        "reliability_score": 9.0,
        "lead_time_days":    8,
        "moq_bags":          50,
        "payment_terms":     "net_30",
        "products_supplied": ["RF-002", "RF-005", "RF-009", "RF-010"],
        "price_per_bag": {
            "RF-002": 1550.0,
            "RF-005": 2180.0,
            "RF-009": 2020.0,
            "RF-010": 2080.0,
        },
        "contact":           "orders@yara.in",
    },
}

# Purchase order log
PO_LOG: list[dict] = []
PO_COUNTER = {"n": 1000}

# ──────────────────────────────────────────────────────────────────────────────
# LLM
# ──────────────────────────────────────────────────────────────────────────────

llm = LLM(
    model="groq/llama-3.3-70b-versatile",
    temperature=0.2,
    api_key=os.getenv("GROQ_API_KEY"),
)

# ──────────────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────────────

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def score_supplier(sup: dict, product_id: str, days_until_stockout: float) -> float:
    """
    Composite supplier score (higher = better):
      40% reliability, 30% lead_time_fit, 30% price_competitiveness

    lead_time_fit: 1.0 if lead_time < days_until_stockout, 0 if it doesn't fit
    price_competitiveness: relative to cheapest available supplier for same product
    """
    if product_id not in sup["products_supplied"]:
        return 0.0

    # Reliability (normalised 0–1)
    rel = sup["reliability_score"] / 10.0

    # Lead time fit
    lead_time_fits = 1.0 if sup["lead_time_days"] < days_until_stockout else 0.3

    # Price score: gather all supplier prices for this product
    all_prices = [
        s["price_per_bag"][product_id]
        for s in SUPPLIERS.values()
        if product_id in s.get("price_per_bag", {})
    ]
    min_price = min(all_prices) if all_prices else 1
    max_price = max(all_prices) if all_prices else 1
    price_range = max_price - min_price if max_price != min_price else 1
    my_price = sup["price_per_bag"].get(product_id, max_price)
    price_score = 1.0 - (my_price - min_price) / price_range  # 1 = cheapest, 0 = most expensive

    return round(0.40 * rel + 0.30 * lead_time_fits + 0.30 * price_score, 3)


# ──────────────────────────────────────────────────────────────────────────────
# Tools
# ──────────────────────────────────────────────────────────────────────────────

@tool("get_suppliers_for_product")
def get_suppliers_for_product(product_id: str) -> str:
    """
    Returns all suppliers who can supply a given product,
    with their price, lead time, MOQ, reliability score, and payment terms.
    """
    p = PRODUCTS.get(product_id)
    if not p:
        return json.dumps({"error": f"{product_id} not found"})

    result = []
    for sid, sup in SUPPLIERS.items():
        if product_id in sup["products_supplied"]:
            result.append({
                "supplier_id":       sid,
                "supplier_name":     sup["name"],
                "location":          sup["location"],
                "price_per_bag":     sup["price_per_bag"].get(product_id),
                "lead_time_days":    sup["lead_time_days"],
                "moq_bags":          sup["moq_bags"],
                "reliability_score": sup["reliability_score"],
                "payment_terms":     sup["payment_terms"],
                "contact":           sup["contact"],
            })

    if not result:
        return json.dumps({
            "product_id": product_id,
            "warning":    "SINGLE SOURCE RISK — no suppliers found. Manual sourcing required.",
            "suppliers":  [],
        })

    return json.dumps({
        "product_id":    product_id,
        "product_name":  p["name"],
        "suppliers":     result,
        "supplier_count": len(result),
        "is_single_source": len(result) == 1,
    })


@tool("select_best_supplier")
def select_best_supplier(product_id: str, days_until_stockout: float) -> str:
    """
    Scores all available suppliers for a product and recommends the best one.

    Scoring: 40% reliability + 30% lead_time_fit + 30% price_competitiveness
    Lead time fit: penalised if supplier cannot deliver before stockout.

    Returns: recommended supplier, score breakdown, runner-up, risk flags.
    """
    p = PRODUCTS.get(product_id)
    if not p:
        return json.dumps({"error": f"{product_id} not found"})

    candidates = []
    for sid, sup in SUPPLIERS.items():
        if product_id not in sup["products_supplied"]:
            continue
        score = score_supplier(sup, product_id, days_until_stockout)
        candidates.append({
            "supplier_id":       sid,
            "supplier_name":     sup["name"],
            "score":             score,
            "price_per_bag":     sup["price_per_bag"].get(product_id),
            "lead_time_days":    sup["lead_time_days"],
            "moq_bags":          sup["moq_bags"],
            "reliability_score": sup["reliability_score"],
            "payment_terms":     sup["payment_terms"],
            "lead_time_fits":    sup["lead_time_days"] < days_until_stockout,
            "contact":           sup["contact"],
        })

    if not candidates:
        return json.dumps({
            "product_id": product_id,
            "error":      "No suppliers available — CRITICAL supply risk",
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    best   = candidates[0]
    runner = candidates[1] if len(candidates) > 1 else None

    risks = []
    if len(candidates) == 1:
        risks.append("SINGLE SOURCE RISK — only one supplier available")
    if not best["lead_time_fits"]:
        risks.append(f"LEAD TIME RISK — {best['lead_time_days']}d lead time may not beat {days_until_stockout}d stockout")
    if best["reliability_score"] < 8.0:
        risks.append(f"RELIABILITY RISK — score {best['reliability_score']}/10 is below 8.0 threshold")

    return json.dumps({
        "product_id":         product_id,
        "product_name":       p["name"],
        "recommended":        best,
        "runner_up":          runner,
        "all_candidates":     candidates,
        "supply_risks":       risks,
        "risk_count":         len(risks),
    })


@tool("get_pending_reorders")
def get_pending_reorders(dummy: str = "") -> str:
    """
    Returns all pending reorder recommendations from the inventory agent
    that have not yet been converted to purchase orders.
    """
    pending = [r for r in REORDER_LOG if r.get("status") == "pending" and r.get("total_order_bags", 0) > 0]
    return json.dumps({
        "pending_reorders": pending,
        "count":            len(pending),
        "timestamp":        utcnow(),
    })


@tool("create_purchase_order")
def create_purchase_order(
    product_id: str,
    supplier_id: str,
    quantity_bags: float,
    urgency: str,
) -> str:
    """
    Creates a purchase order for a product from a given supplier.
    Validates MOQ, calculates order value, sets expected delivery date.
    Logs the PO to PO_LOG and updates the reorder entry status to 'ordered'.
    """
    p   = PRODUCTS.get(product_id)
    sup = SUPPLIERS.get(supplier_id)

    if not p:
        return json.dumps({"error": f"Product {product_id} not found"})
    if not sup:
        return json.dumps({"error": f"Supplier {supplier_id} not found"})
    if product_id not in sup["products_supplied"]:
        return json.dumps({"error": f"{sup['name']} does not supply {product_id}"})

    qty = int(quantity_bags)
    moq = sup["moq_bags"]
    if qty < moq:
        qty = moq  # auto-bump to MOQ

    price_per_bag = sup["price_per_bag"][product_id]
    order_value   = round(qty * price_per_bag, 2)
    gst_on_po     = round(order_value * 0.18, 2)   # GST 18% on raw material purchase
    total_payable = round(order_value + gst_on_po, 2)

    expected_delivery = (
        datetime.now(timezone.utc) + timedelta(days=sup["lead_time_days"])
    ).strftime("%Y-%m-%d")

    PO_COUNTER["n"] += 1
    po_number = f"PO-RF-{PO_COUNTER['n']}"

    po = {
        "po_number":          po_number,
        "product_id":         product_id,
        "product_name":       p["name"],
        "supplier_id":        supplier_id,
        "supplier_name":      sup["name"],
        "quantity_bags":      qty,
        "price_per_bag":      price_per_bag,
        "order_value_rs":     order_value,
        "gst_18pct":          gst_on_po,
        "total_payable_rs":   total_payable,
        "payment_terms":      sup["payment_terms"],
        "lead_time_days":     sup["lead_time_days"],
        "expected_delivery":  expected_delivery,
        "urgency":            urgency,
        "status":             "raised",
        "raised_at":          utcnow(),
        "contact":            sup["contact"],
    }
    PO_LOG.append(po)

    # Mark matching reorder as ordered
    for r in REORDER_LOG:
        if r["product_id"] == product_id and r["status"] == "pending":
            r["status"]   = "ordered"
            r["po_number"] = po_number
            break

    return json.dumps({"status": "✅ Purchase Order raised", **po})


@tool("get_supply_risk_report")
def get_supply_risk_report(dummy: str = "") -> str:
    """
    Scans all products and identifies supply risks:
    - Single-source products (only one supplier)
    - Products with high-lead-time suppliers relative to days of stock
    - Suppliers with reliability < 8.0
    """
    risks = []
    for pid, p in PRODUCTS.items():
        suppliers_for_pid = [
            (sid, sup) for sid, sup in SUPPLIERS.items()
            if pid in sup["products_supplied"]
        ]

        stock     = p["stock_bags"]
        sales_30d = p["sales_last_30d"]
        daily     = sales_30d / 30 if sales_30d > 0 else 0
        dos       = round(stock / daily, 1) if daily > 0 else 999

        if not suppliers_for_pid:
            risks.append({
                "product_id":   pid,
                "product_name": p["name"],
                "risk_type":    "NO_SUPPLIER",
                "severity":     "CRITICAL",
                "detail":       "No supplier mapped — cannot reorder",
            })
        elif len(suppliers_for_pid) == 1:
            risks.append({
                "product_id":   pid,
                "product_name": p["name"],
                "risk_type":    "SINGLE_SOURCE",
                "severity":     "HIGH",
                "detail":       f"Only one supplier: {suppliers_for_pid[0][1]['name']}",
            })

        for sid, sup in suppliers_for_pid:
            if sup["lead_time_days"] >= dos and dos < 30:
                risks.append({
                    "product_id":   pid,
                    "product_name": p["name"],
                    "risk_type":    "LEAD_TIME_RISK",
                    "severity":     "HIGH",
                    "detail":       f"{sup['name']} lead time {sup['lead_time_days']}d >= current DoS {dos}d",
                })
            if sup["reliability_score"] < 8.0:
                risks.append({
                    "product_id":   pid,
                    "product_name": p["name"],
                    "risk_type":    "LOW_RELIABILITY",
                    "severity":     "MEDIUM",
                    "detail":       f"{sup['name']} reliability {sup['reliability_score']}/10",
                })

    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}
    risks.sort(key=lambda x: severity_order.get(x["severity"], 9))

    return json.dumps({
        "supply_risks": risks,
        "risk_count":   len(risks),
        "critical":     sum(1 for r in risks if r["severity"] == "CRITICAL"),
        "high":         sum(1 for r in risks if r["severity"] == "HIGH"),
        "medium":       sum(1 for r in risks if r["severity"] == "MEDIUM"),
        "timestamp":    utcnow(),
    })




# ──────────────────────────────────────────────────────────────────────────────
# Dynamic Config Tool — LLM reasons about optimal supplier strategy
# ──────────────────────────────────────────────────────────────────────────────

@tool("suggest_supplier_strategy")
def suggest_supplier_strategy(product_id: str, days_until_stockout: float) -> str:
    """
    Asks the LLM to reason about the optimal procurement strategy for a product:
    - Should we order now or wait?
    - How much buffer quantity to add beyond the calculated reorder?
    - Which scoring weight to emphasise (speed vs price vs reliability)?
    - Should we split the order across two suppliers to reduce single-source risk?

    Returns:
      - order_now (bool)
      - quantity_buffer_pct  (% to add on top of calculated qty, 0–30%)
      - prioritise           ("speed" | "price" | "reliability")
      - split_order          (bool — split across 2 suppliers)
      - reasoning            (one sentence per decision)
    """
    p = PRODUCTS.get(product_id)
    if not p:
        return json.dumps({"error": f"{product_id} not found"})

    if _groq_client is None:
        return json.dumps({
            "product_id":          product_id,
            "order_now":           True,
            "quantity_buffer_pct": 0,
            "prioritise":          "reliability",
            "split_order":         False,
            "reasoning":           "Groq client unavailable — using conservative defaults",
            "source":              "fallback",
        })

    # Find available suppliers for this product
    available_sups = [
        {"id": sid, "name": s["name"], "lead_time": s["lead_time_days"],
         "reliability": s["reliability_score"], "price": s["price_per_bag"].get(product_id),
         "moq": s["moq_bags"], "payment": s["payment_terms"]}
        for sid, s in SUPPLIERS.items()
        if product_id in s["products_supplied"]
    ]

    daily_rate = PRODUCTS[product_id]["sales_last_30d"] / 30 if PRODUCTS[product_id]["sales_last_30d"] > 0 else 0

    prompt = f"""You are the Procurement Manager at Richfield Fertilisers Pvt. Ltd., Nashik.
Decide the optimal procurement strategy for this reorder.

PRODUCT: {p["name"]} ({product_id}) — Category: {p["category"]}
  Days until stockout : {days_until_stockout} days
  Daily sales rate    : {daily_rate:.1f} bags/day
  Production cost     : ₹{p["production_cost"]:,.0f}/bag
  Current stock       : {p["stock_bags"]} bags

AVAILABLE SUPPLIERS:
{json.dumps(available_sups, indent=2)}

DECISIONS TO MAKE:
1. order_now (true/false): Should we place the order immediately?
   - true if days_until_stockout < 30 or product is critical NPK during season
   - false if stock is adequate and waiting for better price is viable
2. quantity_buffer_pct (0–30): How much extra % to order beyond calculated qty?
   - 0% if overstock risk or slow-moving
   - 10–15% if single source supplier (hedge against partial delivery)
   - 20–30% if approaching peak season (March = pre-Kharif, build buffer)
3. prioritise ("speed"/"price"/"reliability"):
   - "speed" if days_until_stockout < 20
   - "price" if days_until_stockout > 45 and multiple suppliers available
   - "reliability" if single source or product is high-value NPK
4. split_order (true/false): Split order across 2 suppliers?
   - true only if 2+ suppliers available AND single-source risk is high
   - false if only one supplier or order qty < 2× MOQ

Respond ONLY with JSON, no markdown:
{{
  "order_now": <bool>,
  "quantity_buffer_pct": <integer 0-30>,
  "prioritise": "speed" | "price" | "reliability",
  "split_order": <bool>,
  "reasoning": {{
    "order_now": "<one sentence>",
    "quantity_buffer_pct": "<one sentence>",
    "prioritise": "<one sentence>",
    "split_order": "<one sentence>"
  }}
}}"""

    try:
        resp = _groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=350,
        )
        raw  = resp.choices[0].message.content.strip().replace("```json","").replace("```","").strip()
        data = json.loads(raw)
        data["quantity_buffer_pct"] = max(0, min(30, int(data.get("quantity_buffer_pct", 0))))
        data["product_id"]          = product_id
        data["source"]              = "llm"
        return json.dumps(data)

    except Exception as e:
        return json.dumps({
            "product_id":          product_id,
            "order_now":           True,
            "quantity_buffer_pct": 0,
            "prioritise":          "reliability",
            "split_order":         False,
            "reasoning":           f"LLM failed ({e}) — conservative defaults applied",
            "source":              "fallback",
        })


# ──────────────────────────────────────────────────────────────────────────────
# Agent
# ──────────────────────────────────────────────────────────────────────────────

supplier_agent = Agent(
    role="Richfield Fertilisers Procurement Manager",
    goal=(
        "For every pending reorder from the inventory agent: "
        "(1) identify the best supplier using reliability, lead time, and price, "
        "(2) verify the supplier can deliver before stockout, "
        "(3) raise a purchase order with correct quantity (respecting MOQ), "
        "(4) flag any supply risks (single source, low reliability, long lead time), "
        "(5) ensure total order value and GST are correctly calculated."
    ),
    backstory=(
        "You are the Procurement Manager at Richfield Fertilisers Pvt. Ltd., Nashik. "
        "You manage relationships with 6 suppliers across India and are responsible for "
        "ensuring raw materials arrive before stock runs out. You know that during peak season "
        "even a 2-day delay can mean losing a distributor to a competitor. "
        "You always pick the supplier with the best balance of price, reliability, and speed. "
        "You never raise a PO below MOQ and always check if lead time fits before stockout."
    ),
    tools=[
        get_suppliers_for_product,
        select_best_supplier,
        suggest_supplier_strategy,
        get_pending_reorders,
        create_purchase_order,
        get_supply_risk_report,
    ],
    llm=llm,
    verbose=True,
    allow_delegation=False,
    max_iter=25,
)


# ──────────────────────────────────────────────────────────────────────────────
# Task Factory
# ──────────────────────────────────────────────────────────────────────────────

def create_supplier_task() -> Task:
    return Task(
        description="""
        Process all pending reorder recommendations and manage supplier sourcing.

        Step 1: Call get_pending_reorders to see what inventory agent has flagged.

        Step 2: For EACH pending reorder:
          a. Call get_suppliers_for_product to see who can supply it.
          b. Call suggest_supplier_strategy with product_id and days_until_stockout.
             This tells you: order_now, quantity_buffer_pct, what to prioritise, split_order.
          c. If order_now is false, skip to next product.
          d. Call select_best_supplier — if prioritise is "speed", weight lead time highest;
             if "price", weight price highest; otherwise use default reliability weighting.
          e. Apply quantity_buffer_pct on top of the reorder qty before calling create_purchase_order.
          f. Call create_purchase_order with the best supplier, adjusted quantity, and urgency.
          g. Note any supply risks flagged.

        Step 3: Call get_supply_risk_report for a full risk scan.

        Step 4: Produce a final procurement summary:
          - List of POs raised (PO number, supplier, qty, value, delivery date)
          - Total procurement value (ex-GST and incl. GST)
          - Supply risk summary (critical / high / medium)
          - Any products where lead time may not fit before stockout
        """,
        expected_output=(
            "Procurement Report:\n"
            "1. POs Raised: PO# | Product | Supplier | Qty | Value | Delivery Date\n"
            "2. Total procurement value (ex-GST + GST = total payable)\n"
            "3. Supply risk list: Product | Risk Type | Severity | Detail\n"
            "4. Products at lead-time risk"
        ),
        agent=supplier_agent,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────────────────────

def run_supplier_procurement() -> str:
    print(f"\n{'='*65}")
    print(f"  🚚  Richfield Supplier Agent — {datetime.now().strftime('%d-%m-%Y %H:%M')}")
    print(f"  Pending reorders: {len([r for r in REORDER_LOG if r.get('status') == 'pending'])}")
    print(f"{'='*65}\n")

    task = create_supplier_task()
    crew = Crew(agents=[supplier_agent], tasks=[task], process=Process.sequential, verbose=True)
    result = crew.kickoff()

    print(f"\n{'='*65}")
    print("  ✅  Supplier Procurement Complete")
    print(f"{'='*65}\n")
    return str(result)


if __name__ == "__main__":
    # Demo: run inventory first to create reorders, then supplier
    from inventory_agent import run_inventory_audit
    run_inventory_audit()
    run_supplier_procurement()
