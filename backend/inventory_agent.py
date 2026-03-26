"""
Richfield Fertilisers Pvt. Ltd. — Inventory Agent
===================================================
Stack : Python + CrewAI + Groq (LLaMA 3.3-70b)
Scope : 25 kg bag grades, warehouse stock management

Inventory rules
───────────────
1. Critical stock  : days_of_stock < 15  → urgent reorder
2. Low stock       : days_of_stock 15–30 → schedule reorder
3. Healthy stock   : days_of_stock 30–90 → monitor
4. Overstock       : days_of_stock > 90  → pause production, consider markdown
5. Dead stock      : days_of_stock > 180 AND slow_moving → escalate to pricing agent

Reorder quantity formula
────────────────────────
  daily_rate   = sales_last_30d / 30
  reorder_qty  = (target_dos - current_dos) × daily_rate
  safety_stock = daily_rate × safety_stock_days
  total_order  = reorder_qty + safety_stock  (rounded up to nearest 10)
"""

import os
import json
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv
load_dotenv()

try:
    from groq import Groq as _Groq
    _groq_client = _Groq(api_key=os.getenv('GROQ_API_KEY', ''))
except Exception:
    _groq_client = None

from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool

from pricing_agent import PRODUCTS, CONFIG, days_since



# ──────────────────────────────────────────────────────────────────────────────
# Inventory Configuration
# ──────────────────────────────────────────────────────────────────────────────

INVENTORY_CONFIG = {
    "critical_dos_threshold":   15,    # days of stock — urgent reorder
    "low_dos_threshold":        30,    # days of stock — schedule reorder
    "overstock_dos_threshold":  90,    # days of stock — pause production
    "dead_stock_dos_threshold": 180,   # days of stock AND slow moving — escalate
    "target_dos":               60,    # target days of stock to maintain
    "safety_stock_days":        10,    # extra buffer days added to every order
    "warehouse_capacity_bags":  2000,  # total warehouse capacity across all SKUs
}

# Reorder log (in-memory)
REORDER_LOG: list[dict] = []

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


def classify_stock_status(dos: float) -> str:
    if dos < INVENTORY_CONFIG["critical_dos_threshold"]:
        return "critical"
    elif dos < INVENTORY_CONFIG["low_dos_threshold"]:
        return "low"
    elif dos < INVENTORY_CONFIG["overstock_dos_threshold"]:
        return "healthy"
    elif dos < INVENTORY_CONFIG["dead_stock_dos_threshold"]:
        return "overstock"
    else:
        return "dead_stock"


# ──────────────────────────────────────────────────────────────────────────────
# Tools
# ──────────────────────────────────────────────────────────────────────────────

@tool("get_inventory_status")
def get_inventory_status(product_id: str) -> str:
    """
    Returns full inventory status for a product:
    stock_bags, sales_last_30d, daily_sales_rate, days_of_stock,
    stock_status (critical/low/healthy/overstock/dead_stock),
    days_since_last_sale, is_slow_moving, inventory_value_rs.
    """
    p = PRODUCTS.get(product_id)
    if not p:
        return json.dumps({"error": f"{product_id} not found"})

    stock        = p["stock_bags"]
    sales_30d    = p["sales_last_30d"]
    daily_rate   = round(sales_30d / 30, 2) if sales_30d > 0 else 0.0
    dos          = round(stock / daily_rate, 1) if daily_rate > 0 else 999
    days_no_sale = days_since(p["last_sale_date"])
    is_slow      = days_no_sale >= CONFIG["slow_moving_days"] or sales_30d == 0
    status       = classify_stock_status(dos)
    inv_value    = round(stock * p["distributor_rate"], 2)

    return json.dumps({
        "product_id":           product_id,
        "product_name":         p["name"],
        "category":             p["category"],
        "stock_bags":           stock,
        "sales_last_30d":       sales_30d,
        "daily_sales_rate":     daily_rate,
        "days_of_stock":        dos,
        "stock_status":         status,
        "days_since_last_sale": days_no_sale,
        "is_slow_moving":       is_slow,
        "inventory_value_rs":   inv_value,
        "warehouse_capacity":   INVENTORY_CONFIG["warehouse_capacity_bags"],
    })


@tool("get_warehouse_summary")
def get_warehouse_summary(dummy: str = "") -> str:
    """
    Returns warehouse-wide summary:
    total_bags, total_inventory_value, utilisation_pct,
    and lists of product IDs by status (critical/low/healthy/overstock/dead_stock).
    """
    total_bags  = 0
    total_value = 0.0
    status_counts: dict = {"critical": [], "low": [], "healthy": [], "overstock": [], "dead_stock": []}

    for pid, p in PRODUCTS.items():
        stock     = p["stock_bags"]
        sales_30d = p["sales_last_30d"]
        daily     = sales_30d / 30 if sales_30d > 0 else 0
        dos       = round(stock / daily, 1) if daily > 0 else 999
        status    = classify_stock_status(dos)

        total_bags  += stock
        total_value += stock * p["distributor_rate"]
        status_counts[status].append(pid)

    cap      = INVENTORY_CONFIG["warehouse_capacity_bags"]
    util_pct = round(total_bags / cap * 100, 1)

    return json.dumps({
        "total_bags":            total_bags,
        "total_inventory_value": round(total_value, 2),
        "warehouse_capacity":    cap,
        "utilisation_pct":       util_pct,
        "status_breakdown":      status_counts,
        "products_critical":     status_counts["critical"],
        "products_low":          status_counts["low"],
        "products_overstock":    status_counts["overstock"],
        "products_dead_stock":   status_counts["dead_stock"],
        "timestamp":             utcnow(),
    })


@tool("calculate_reorder_quantity")
def calculate_reorder_quantity(product_id: str) -> str:
    """
    Calculates how many bags to reorder for a product.

    Formula:
      daily_rate   = sales_last_30d / 30
      reorder_qty  = (target_dos - current_dos) × daily_rate
      safety_stock = daily_rate × safety_stock_days
      total_order  = reorder_qty + safety_stock  (rounded up to nearest 10)

    Returns: reorder_qty, safety_stock, total_order_bags, order_value_rs, urgency.
    """
    p = PRODUCTS.get(product_id)
    if not p:
        return json.dumps({"error": f"{product_id} not found"})

    stock     = p["stock_bags"]
    sales_30d = p["sales_last_30d"]

    if sales_30d == 0:
        return json.dumps({
            "product_id":       product_id,
            "product_name":     p["name"],
            "message":          "No recent sales — reorder not recommended. Escalate to pricing agent for markdown.",
            "reorder_qty":      0,
            "total_order_bags": 0,
            "urgency":          "none",
        })

    daily_rate   = sales_30d / 30
    dos          = stock / daily_rate
    target_dos   = INVENTORY_CONFIG["target_dos"]
    safety_days  = INVENTORY_CONFIG["safety_stock_days"]

    reorder_qty  = max(0, (target_dos - dos) * daily_rate)
    safety_stock = daily_rate * safety_days
    total_order  = int(((reorder_qty + safety_stock) // 10 + 1) * 10)
    order_value  = round(total_order * p["production_cost"], 2)

    if dos < INVENTORY_CONFIG["critical_dos_threshold"]:
        urgency = "URGENT — stockout in under 15 days"
    elif dos < INVENTORY_CONFIG["low_dos_threshold"]:
        urgency = "HIGH — reorder within 7 days"
    elif dos < INVENTORY_CONFIG["target_dos"]:
        urgency = "MEDIUM — schedule reorder this week"
    else:
        urgency = "LOW — stock adequate"

    return json.dumps({
        "product_id":           product_id,
        "product_name":         p["name"],
        "current_stock":        stock,
        "daily_sales_rate":     round(daily_rate, 2),
        "current_dos":          round(dos, 1),
        "target_dos":           target_dos,
        "reorder_qty":          round(reorder_qty),
        "safety_stock":         round(safety_stock),
        "total_order_bags":     total_order,
        "order_value_rs":       order_value,
        "days_until_stockout":  round(dos, 1),
        "urgency":              urgency,
    })


@tool("flag_overstock_products")
def flag_overstock_products(dummy: str = "") -> str:
    """
    Scans all products and returns those with excess stock (dos > 90 days).
    Includes capital tied up in excess stock and recommended action.
    """
    overstock = []
    for pid, p in PRODUCTS.items():
        sales_30d    = p["sales_last_30d"]
        daily        = sales_30d / 30 if sales_30d > 0 else 0
        dos          = round(p["stock_bags"] / daily, 1) if daily > 0 else 999
        days_no_sale = days_since(p["last_sale_date"])
        is_dead      = dos > INVENTORY_CONFIG["dead_stock_dos_threshold"] and sales_30d == 0

        if dos > INVENTORY_CONFIG["overstock_dos_threshold"]:
            excess = round(p["stock_bags"] - INVENTORY_CONFIG["target_dos"] * daily)
            tied   = round(max(0, excess) * p["production_cost"], 2)
            overstock.append({
                "product_id":   pid,
                "product_name": p["name"],
                "stock_bags":   p["stock_bags"],
                "dos":          dos,
                "status":       "dead_stock" if is_dead else "overstock",
                "excess_bags":  max(0, excess),
                "capital_tied": tied,
                "action":       "PAUSE production + MARKDOWN via pricing agent" if is_dead
                                else "Pause new production orders",
            })

    return json.dumps({
        "overstock_products": overstock,
        "count":              len(overstock),
        "timestamp":          utcnow(),
    })


@tool("log_reorder_recommendation")
def log_reorder_recommendation(product_id: str, total_order_bags: float, urgency: str) -> str:
    """
    Logs a reorder recommendation to REORDER_LOG.
    Always call this after calculate_reorder_quantity to record the decision.
    """
    p = PRODUCTS.get(product_id)
    if not p:
        return json.dumps({"error": f"{product_id} not found"})

    entry = {
        "product_id":       product_id,
        "product_name":     p["name"],
        "total_order_bags": int(total_order_bags),
        "order_value_rs":   round(int(total_order_bags) * p["production_cost"], 2),
        "urgency":          urgency,
        "recommended_at":   utcnow(),
        "status":           "pending",
    }
    REORDER_LOG.append(entry)
    return json.dumps({"status": "logged", **entry})




# ──────────────────────────────────────────────────────────────────────────────
# Dynamic Config Tool — LLM reasons about optimal inventory parameters
# ──────────────────────────────────────────────────────────────────────────────

@tool("suggest_inventory_config")
def suggest_inventory_config(product_id: str) -> str:
    """
    Asks the LLM to suggest optimised inventory parameters for a specific product
    based on its category, sales velocity, current stock level, and supplier lead time.

    Returns suggested values for:
      - target_dos        (ideal days of stock to maintain, 30–120)
      - safety_stock_days (buffer days on top of reorder qty, 5–21)
    along with reasoning for each.

    These are used by calculate_reorder_quantity for this product only
    and do NOT overwrite global INVENTORY_CONFIG.
    """
    p = PRODUCTS.get(product_id)
    if not p:
        return json.dumps({"error": f"{product_id} not found"})

    if _groq_client is None:
        return json.dumps({
            "product_id":       product_id,
            "target_dos":       INVENTORY_CONFIG["target_dos"],
            "safety_stock_days":INVENTORY_CONFIG["safety_stock_days"],
            "reasoning":        "Groq client unavailable — using global defaults",
            "source":           "fallback",
        })

    daily_rate   = p["sales_last_30d"] / 30 if p["sales_last_30d"] > 0 else 0
    dos          = round(p["stock_bags"] / daily_rate, 1) if daily_rate > 0 else 999
    days_no_sale = days_since(p["last_sale_date"])
    is_slow      = days_no_sale >= CONFIG["slow_moving_days"] or p["sales_last_30d"] == 0

    prompt = f"""You are the Warehouse Manager at Richfield Fertilisers Pvt. Ltd., Nashik.
Suggest optimised inventory parameters for this product.

PRODUCT: {p["name"]} ({product_id}) — Category: {p["category"]}
  Current stock      : {p["stock_bags"]} bags
  Current DoS        : {dos} days
  Sales last 30d     : {p["sales_last_30d"]} bags  ({daily_rate:.1f}/day)
  Days since sale    : {days_no_sale} days
  Slow-moving        : {is_slow}
  Production cost    : ₹{p["production_cost"]:,.0f}/bag
  Inventory value    : ₹{p["stock_bags"] * p["distributor_rate"]:,.0f}

CONTEXT:
- NPK grades (RF-001 to RF-010) are seasonal — high demand Kharif (June-Oct) and Rabi (Nov-Feb)
- Straight grades and micronutrients (RF-011 to RF-014) move slower year-round
- Current month context: March (post-Rabi, pre-Kharif — moderate demand)

PARAMETERS TO SUGGEST:
1. target_dos (30–120 days): Ideal days of stock to maintain.
   - Fast-moving NPK: 45–60d (don't over-invest capital in slow products)
   - Slow-moving/specialty: 60–90d (less frequent deliveries, harder to source)
   - Dead stock: 30d (stop accumulating, let it deplete)
2. safety_stock_days (5–21 days): Buffer days added to every reorder.
   - Short lead time supplier (5–7d): 7–10 days safety
   - Long lead time supplier (12–14d): 14–21 days safety
   - Slow-moving product: minimal safety (5–7d) — don't build buffer on non-selling stock

Respond ONLY with a JSON object, no markdown:
{{
  "target_dos": <integer>,
  "safety_stock_days": <integer>,
  "reasoning": {{
    "target_dos": "<one sentence>",
    "safety_stock_days": "<one sentence>"
  }}
}}"""

    try:
        resp = _groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=250,
        )
        raw  = resp.choices[0].message.content.strip().replace("```json","").replace("```","").strip()
        data = json.loads(raw)
        data["target_dos"]         = max(30, min(120, int(data.get("target_dos",        INVENTORY_CONFIG["target_dos"]))))
        data["safety_stock_days"]  = max(5,  min(21,  int(data.get("safety_stock_days", INVENTORY_CONFIG["safety_stock_days"]))))
        data["product_id"]         = product_id
        data["source"]             = "llm"
        return json.dumps(data)

    except Exception as e:
        return json.dumps({
            "product_id":        product_id,
            "target_dos":        INVENTORY_CONFIG["target_dos"],
            "safety_stock_days": INVENTORY_CONFIG["safety_stock_days"],
            "reasoning":         f"LLM failed ({e}) — using global defaults",
            "source":            "fallback",
        })


# ──────────────────────────────────────────────────────────────────────────────
# Agent
# ──────────────────────────────────────────────────────────────────────────────

inventory_agent = Agent(
    role="Richfield Fertilisers Inventory Manager",
    goal=(
        "Monitor warehouse stock levels for all 25 kg bag grades and ensure: "
        f"(1) no product falls below {INVENTORY_CONFIG['critical_dos_threshold']} days of stock, "
        f"(2) target of {INVENTORY_CONFIG['target_dos']} days of stock is maintained, "
        "(3) overstock products are flagged and production is paused, "
        "(4) dead stock is escalated for markdown, "
        "(5) every reorder is logged with quantity and urgency."
    ),
    backstory=(
        "You are the Warehouse Manager at Richfield Fertilisers Pvt. Ltd., Nashik. "
        "You have 15 years of experience managing fertiliser inventory across Maharashtra. "
        "You know that running out of NPK grades during Kharif or Rabi season means "
        "losing distributors permanently. You balance capital efficiency (don't overstock) "
        "with service level (never stockout). You always quantify reorder needs precisely."
    ),
    tools=[
        get_inventory_status,
        get_warehouse_summary,
        suggest_inventory_config,
        calculate_reorder_quantity,
        flag_overstock_products,
        log_reorder_recommendation,
    ],
    llm=llm,
    verbose=True,
    allow_delegation=False,
    max_iter=20,
)


# ──────────────────────────────────────────────────────────────────────────────
# Task Factory
# ──────────────────────────────────────────────────────────────────────────────

def create_inventory_task(product_ids: list) -> Task:
    id_list = ", ".join(product_ids)
    return Task(
        description=f"""
        Perform a full inventory audit for: {id_list}

        Step 1: Call get_warehouse_summary for overall picture.

        Step 2: For EACH product:
          a. Call get_inventory_status.
          b. If critical or low: call calculate_reorder_quantity, then log_reorder_recommendation.
          c. If healthy: note adequate, no action.
          d. If overstock or dead_stock: note for escalation.

        Step 3: Call flag_overstock_products.

        Step 4: Produce final summary with:
          - Warehouse utilisation %
          - Urgent reorder list (with quantities and values)
          - Overstock list (with capital tied up)
          - Total pending reorder value

        Thresholds:
        - Critical: < {INVENTORY_CONFIG['critical_dos_threshold']} days
        - Low: < {INVENTORY_CONFIG['low_dos_threshold']} days
        - Healthy: {INVENTORY_CONFIG['low_dos_threshold']}–{INVENTORY_CONFIG['overstock_dos_threshold']} days
        - Overstock: > {INVENTORY_CONFIG['overstock_dos_threshold']} days
        - Target: {INVENTORY_CONFIG['target_dos']} days
        """,
        expected_output=(
            "Inventory Audit Report with:\n"
            "1. Warehouse summary (bags, value, utilisation)\n"
            "2. Reorder list: Product | DoS | Qty | Value | Urgency\n"
            "3. Overstock list: Product | DoS | Excess | Capital tied\n"
            "4. Total reorder value"
        ),
        agent=inventory_agent,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────────────────────

def run_inventory_audit(product_ids: Optional[list] = None) -> str:
    if product_ids is None:
        product_ids = list(PRODUCTS.keys())

    print(f"\n{'='*65}")
    print(f"  📦  Richfield Inventory Agent — {datetime.now().strftime('%d-%m-%Y %H:%M')}")
    print(f"  Products : {', '.join(product_ids)}")
    print(f"{'='*65}\n")

    task = create_inventory_task(product_ids)
    crew = Crew(agents=[inventory_agent], tasks=[task], process=Process.sequential, verbose=True)
    result = crew.kickoff()

    print(f"\n{'='*65}")
    print("  ✅  Inventory Audit Complete")
    print(f"{'='*65}\n")
    return str(result)


def update_inventory_config(
    target_dos: Optional[int] = None,
    critical_dos_threshold: Optional[int] = None,
    overstock_dos_threshold: Optional[int] = None,
    safety_stock_days: Optional[int] = None,
):
    if target_dos is not None:
        INVENTORY_CONFIG["target_dos"] = target_dos
    if critical_dos_threshold is not None:
        INVENTORY_CONFIG["critical_dos_threshold"] = critical_dos_threshold
    if overstock_dos_threshold is not None:
        INVENTORY_CONFIG["overstock_dos_threshold"] = overstock_dos_threshold
    if safety_stock_days is not None:
        INVENTORY_CONFIG["safety_stock_days"] = safety_stock_days


if __name__ == "__main__":
    run_inventory_audit()
