"""
Richfield Fertilisers Pvt. Ltd. — Pricing Agent
=================================================
Stack : Python + CrewAI + Groq (LLaMA 3.3-70b)
Scope : 25 kg bag grades, Maharashtra distributor price list w.e.f. 22-09-2026

Pricing rules
─────────────
1. Selling price must be ≥ distributor_rate × (1 + min_margin_pct/100)   [configurable]
2. Selling price must be ≤ MRP                                             [hard ceiling]
3. GST (5%) is added on top of the ex-GST selling price for farmer billing
4. Cash discount tiers are factored into effective margin calculation
5. SKUs with zero sales in last 30 days are flagged slow-moving → markdown

Install:
    pip install crewai crewai-tools python-dotenv litellm
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



# ──────────────────────────────────────────────────────────────────────────────
# Configuration — edit these to change global business rules
# ──────────────────────────────────────────────────────────────────────────────

CONFIG = {
    "min_margin_pct":       20,      # minimum margin % above production cost
    "mrp_headroom_pct":     80,      # how far (%) to push price between floor and MRP
    "slow_moving_days":     30,      # flag if no sales within this many days
    "gst_pct":              5,       # GST % applied on top of ex-GST selling price
    "markdown_pct":         10,      # how much to markdown a slow-moving SKU (%)
    "cash_discount_tiers": {         # % discount off selling price based on payment timing
        "advance":  7.0,
        "1_15d":    5.0,
        "16_30d":   4.0,
        "31_45d":   2.5,
    },
}

# ──────────────────────────────────────────────────────────────────────────────
# LLM
# ──────────────────────────────────────────────────────────────────────────────

llm = LLM(
    model="groq/llama-3.3-70b-versatile",
    temperature=0.2,
    api_key=os.getenv("GROQ_API_KEY"),
)

# ──────────────────────────────────────────────────────────────────────────────
# Richfield Product Catalogue — 25 kg bag grades (Maharashtra, w.e.f. 22-09-2026)
# distributor_rate = net rate from price list (ex-GST, your cost)
# mrp             = printed MRP (hard ceiling, ex-GST basis used internally)
# current_price   = what you are currently selling at (ex-GST); starts at MRP
# stock_bags      = bags currently in warehouse
# sales_last_30d  = bags sold in last 30 days  (update from your sales system)
# last_sale_date  = ISO date string of last sale (for slow-moving detection)
# ──────────────────────────────────────────────────────────────────────────────

PRODUCTS = {
    "RF-001": {
        "name":             "00-60-20",
        "production_cost":    3650.0,
        "pack":             "25 kg bag",
        "category":         "NPK",
        "distributor_rate": 5650.00,
        "mrp":              9000.00,
        "current_price":    8000.00,
        "gst_pct":          5,
        "stock_bags":       80,
        "sales_last_30d":   35,
        "last_sale_date":   "2026-03-03",
    },
    "RF-002": {
        "name":             "00:00:50 + 18% S",
        "production_cost":    1600.0,
        "pack":             "25 kg bag",
        "category":         "Straight",
        "distributor_rate": 2475.00,
        "mrp":              4400.00,
        "current_price":    3800.00,
        "gst_pct":          5,
        "stock_bags":       150,
        "sales_last_30d":   0,
        "last_sale_date":   "2026-01-28",   # slow-moving
    },
    "RF-003": {
        "name":             "00:52:34",
        "production_cost":    3000.0,
        "pack":             "25 kg bag",
        "category":         "NPK",
        "distributor_rate": 4650.00,
        "mrp":              7900.00,
        "current_price":    7000.00,
        "gst_pct":          5,
        "stock_bags":       20,
        "sales_last_30d":   28,
        "last_sale_date":   "2026-03-04",
    },
    "RF-004": {
        "name":             "12:61:00",
        "production_cost":    2500.0,
        "pack":             "25 kg bag",
        "category":         "NPK",
        "distributor_rate": 3875.00,
        "mrp":              5700.00,
        "current_price":    5200.00,
        "gst_pct":          5,
        "stock_bags":       45,
        "sales_last_30d":   20,
        "last_sale_date":   "2026-03-01",
    },
    "RF-005": {
        "name":             "13:00:45",
        "production_cost":    2200.0,
        "pack":             "25 kg bag",
        "category":         "NPK",
        "distributor_rate": 3400.00,
        "mrp":              5800.00,
        "current_price":    5000.00,
        "gst_pct":          5,
        "stock_bags":       30,
        "sales_last_30d":   18,
        "last_sale_date":   "2026-02-28",
    },
    "RF-006": {
        "name":             "13:40:13",
        "production_cost":    2450.0,
        "pack":             "25 kg bag",
        "category":         "NPK",
        "distributor_rate": 3750.00,
        "mrp":              5800.00,
        "current_price":    5400.00,
        "gst_pct":          5,
        "stock_bags":       90,
        "sales_last_30d":   0,
        "last_sale_date":   "2026-01-20",   # slow-moving
    },
    "RF-007": {
        "name":             "16:08:24 + T.E.",
        "production_cost":    2000.0,
        "pack":             "25 kg bag",
        "category":         "NPK+TE",
        "distributor_rate": 3100.00,
        "mrp":              5300.00,
        "current_price":    4800.00,
        "gst_pct":          5,
        "stock_bags":       55,
        "sales_last_30d":   22,
        "last_sale_date":   "2026-03-02",
    },
    "RF-008": {
        "name":             "Urea Phosphate",
        "production_cost":    2400.0,
        "pack":             "25 kg bag",
        "category":         "Straight",
        "distributor_rate": 3675.00,
        "mrp":              5500.00,
        "current_price":    5000.00,
        "gst_pct":          5,
        "stock_bags":       40,
        "sales_last_30d":   15,
        "last_sale_date":   "2026-02-25",
    },
    "RF-009": {
        "name":             "19:19:19 + 1.5MgO + T.E.",
        "production_cost":    2050.0,
        "pack":             "25 kg bag",
        "category":         "NPK+TE",
        "distributor_rate": 3125.00,
        "mrp":              4900.00,
        "current_price":    4500.00,
        "gst_pct":          5,
        "stock_bags":       120,
        "sales_last_30d":   55,
        "last_sale_date":   "2026-03-04",
    },
    "RF-010": {
        "name":             "20:20:20",
        "production_cost":    2100.0,
        "pack":             "25 kg bag",
        "category":         "NPK",
        "distributor_rate": 3225.00,
        "mrp":              5300.00,
        "current_price":    4800.00,
        "gst_pct":          5,
        "stock_bags":       75,
        "sales_last_30d":   30,
        "last_sale_date":   "2026-03-03",
    },
    "RF-011": {
        "name":             "Cal. Nitrate",
        "production_cost":    1000.0,
        "pack":             "25 kg bag",
        "category":         "Straight",
        "distributor_rate": 1500.00,
        "mrp":              2800.00,
        "current_price":    2400.00,
        "gst_pct":          5,
        "stock_bags":       200,
        "sales_last_30d":   0,
        "last_sale_date":   "2026-01-10",   # slow-moving
    },
    "RF-012": {
        "name":             "Rich Magnesium Nitrate",
        "production_cost":    1200.0,
        "pack":             "25 kg bag",
        "category":         "MN",
        "distributor_rate": 1875.00,
        "mrp":              3000.00,
        "current_price":    2700.00,
        "gst_pct":          5,
        "stock_bags":       50,
        "sales_last_30d":   12,
        "last_sale_date":   "2026-02-20",
    },
    "RF-013": {
        "name":             "Pot. Mag. Sulphate",
        "production_cost":    1700.0,
        "pack":             "25 kg bag",
        "category":         "MN",
        "distributor_rate": 2650.00,
        "mrp":              4300.00,
        "current_price":    3800.00,
        "gst_pct":          5,
        "stock_bags":       35,
        "sales_last_30d":   10,
        "last_sale_date":   "2026-02-15",
    },
    "RF-014": {
        "name":             "Potassium Schonite",
        "production_cost":    1300.0,
        "pack":             "25 kg bag",
        "category":         "MN",
        "distributor_rate": 2026.00,
        "mrp":              3300.00,
        "current_price":    2900.00,
        "gst_pct":          5,
        "stock_bags":       65,
        "sales_last_30d":   8,
        "last_sale_date":   "2026-02-10",
    },
}

# Pricing history log (in-memory; replace with DB in production)
PRICE_HISTORY: list[dict] = []


# ──────────────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────────────

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def days_since(date_str: str) -> int:
    """Return number of days since a given ISO date string."""
    try:
        then = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - then).days
    except Exception:
        return 999


# ──────────────────────────────────────────────────────────────────────────────
# Tools
# ──────────────────────────────────────────────────────────────────────────────

@tool("fetch_product_data")
def fetch_product_data(product_id: str) -> str:
    """
    Fetches full product details for a Richfield fertiliser SKU.
    Returns distributor rate, MRP, current selling price, GST %, stock, and sales data.
    """
    p = PRODUCTS.get(product_id)
    if not p:
        return json.dumps({"error": f"{product_id} not found in catalogue"})
    return json.dumps({"product_id": product_id, **p})


@tool("fetch_demand_and_slow_moving_status")
def fetch_demand_and_slow_moving_status(product_id: str) -> str:
    """
    Analyses demand velocity and checks if the product is slow-moving.
    A product is flagged slow-moving if it has had zero sales in the last 30 days.
    Returns: sales_last_30d, days_since_last_sale, is_slow_moving, days_of_stock.
    """
    p = PRODUCTS.get(product_id)
    if not p:
        return json.dumps({"error": f"{product_id} not found"})

    days_no_sale = days_since(p["last_sale_date"])
    is_slow      = days_no_sale >= CONFIG["slow_moving_days"] or p["sales_last_30d"] == 0
    dos          = round((p["stock_bags"] / p["sales_last_30d"] * 30), 1) if p["sales_last_30d"] > 0 else 999

    return json.dumps({
        "product_id":         product_id,
        "sales_last_30d":     p["sales_last_30d"],
        "days_since_last_sale": days_no_sale,
        "is_slow_moving":     is_slow,
        "days_of_stock":      dos,
        "stock_bags":         p["stock_bags"],
    })


@tool("calculate_richfield_price")
def calculate_richfield_price(product_id: str) -> str:
    """
    Calculates the optimal selling price (ex-GST) for a Richfield fertiliser SKU.

    Rules applied:
    1. Min price  = distributor_rate × (1 + min_margin_pct / 100)
    2. Max price  = MRP  (hard ceiling — never exceeded)
    3. Slow-moving products get a markdown of 10% off current price
    4. Healthy products are priced to maximise margin within the MRP ceiling
    5. GST (5%) is calculated separately on top for farmer billing

    Returns: recommended_price_exgst, gst_amount, farmer_price_incl_gst,
             margin_pct, margin_rs, status, reason
    """
    p = PRODUCTS.get(product_id)
    if not p:
        return json.dumps({"error": f"{product_id} not found"})

    dist_rate  = p["distributor_rate"]
    mrp        = p["mrp"]
    gst_pct    = p["gst_pct"]
    min_margin = CONFIG["min_margin_pct"]
    days_no_sale = days_since(p["last_sale_date"])
    is_slow    = days_no_sale >= CONFIG["slow_moving_days"] or p["sales_last_30d"] == 0

    # Floor and ceiling
    min_price  = round(dist_rate * (1 + min_margin / 100), 2)
    max_price  = mrp   # hard ceiling

    reasons = []
    status  = "healthy"

    if is_slow:
        # Markdown slow-moving stock to stimulate sales
        markdown_price = round(p["current_price"] * (1 - CONFIG["markdown_pct"] / 100), 2)
        recommended    = max(min_price, min(markdown_price, max_price))
        reasons.append(f"Slow-moving ({days_no_sale}d no sale) → markdown {CONFIG['markdown_pct']}%")
        status = "slow_moving"
    else:
        # Push price toward MRP to maximise margin, but stay within ceiling
        # Target: 80% of the gap between min_price and MRP
        headroom   = CONFIG["mrp_headroom_pct"] / 100
        target     = round(min_price + (max_price - min_price) * headroom, 2)
        recommended = min(target, max_price)
        reasons.append(f"Active product → targeting {CONFIG['mrp_headroom_pct']}% of MRP headroom")

    # Final clamp
    recommended = max(min_price, min(recommended, max_price))
    recommended = round(recommended, 2)

    # GST and farmer price
    gst_amount       = round(recommended * gst_pct / 100, 2)
    farmer_price     = round(recommended + gst_amount, 2)

    # Margin calculations
    margin_rs        = round(recommended - dist_rate, 2)
    margin_pct       = round((margin_rs / recommended) * 100, 1)

    # Effective margin after typical cash discount (advance tier = 7%)
    advance_discount = round(recommended * CONFIG["cash_discount_tiers"]["advance"] / 100, 2)
    effective_margin = round(margin_rs - advance_discount, 2)
    effective_margin_pct = round((effective_margin / recommended) * 100, 1)

    return json.dumps({
        "product_id":              product_id,
        "product_name":            p["name"],
        "production_cost":         production_cost,
        "current_rate":            current_rate,
        "recommended_rate_exgst":  recommended,
        "mrp":                     mrp,
        "min_allowed":             min_rate,
        "gst_pct":                 gst_pct,
        "gst_amount":              gst_amount,
        "distributor_pays_incl_gst": distributor_pays,
        "margin_rs":               margin_rs,
        "margin_pct":              margin_pct,
        "effective_margin_after_advance_discount_rs": effective_margin,
        "effective_margin_pct":    effective_margin_pct,
        "status":                  status,
        "reason":                  " | ".join(reasons),
        "timestamp":               utcnow(),
    })


@tool("apply_cash_discount")
def apply_cash_discount(product_id: str, payment_timing: str) -> str:
    """
    Calculates the effective margin and amount receivable after applying the
    cash discount tier for a given payment timing.

    payment_timing options: 'advance', '1_15d', '16_30d', '31_45d'

    Returns: gross_price, discount_pct, discount_rs, net_receivable, net_margin_rs, net_margin_pct
    """
    p = PRODUCTS.get(product_id)
    if not p:
        return json.dumps({"error": f"{product_id} not found"})

    tier = CONFIG["cash_discount_tiers"].get(payment_timing)
    if tier is None:
        return json.dumps({"error": f"Invalid payment_timing '{payment_timing}'. Use: advance, 1_15d, 16_30d, 31_45d"})

    selling_price  = p["current_price"]
    discount_rs    = round(selling_price * tier / 100, 2)
    net_receivable = round(selling_price - discount_rs, 2)
    net_margin_rs  = round(net_receivable - p["distributor_rate"], 2)
    net_margin_pct = round((net_margin_rs / net_receivable) * 100, 1) if net_receivable > 0 else 0

    return json.dumps({
        "product_id":       product_id,
        "product_name":     p["name"],
        "payment_timing":   payment_timing,
        "gross_price":      selling_price,
        "discount_pct":     tier,
        "discount_rs":      discount_rs,
        "net_receivable":   net_receivable,
        "distributor_rate": p["distributor_rate"],
        "net_margin_rs":    net_margin_rs,
        "net_margin_pct":   net_margin_pct,
        "viable":           net_margin_rs > 0,
    })


@tool("apply_price_update")
def apply_price_update(product_id: str, new_price: float) -> str:
    """
    Applies a new ex-GST selling price for a product.
    Validates against minimum margin floor and MRP ceiling before applying.
    Logs the change to PRICE_HISTORY.
    """
    p = PRODUCTS.get(product_id)
    if not p:
        return json.dumps({"error": f"{product_id} not found"})

    dist_rate = p["distributor_rate"]
    mrp       = p["mrp"]
    min_price = round(dist_rate * (1 + CONFIG["min_margin_pct"] / 100), 2)

    if new_price < min_price:
        return json.dumps({
            "error":    f"Rejected — ₹{new_price} is below minimum margin floor (₹{min_price})",
            "min_allowed": min_price,
        })
    if new_price > mrp:
        return json.dumps({
            "error":  f"Rejected — ₹{new_price} exceeds MRP ceiling (₹{mrp})",
            "mrp":    mrp,
        })

    old_price       = p["distributor_rate"]
    production_cost = p["production_cost"]
    PRODUCTS[product_id]["distributor_rate"] = new_price

    change_pct = round(((new_price - old_price) / old_price) * 100, 1)
    margin_rs  = round(new_price - production_cost, 2)
    margin_pct = round((margin_rs / new_price) * 100, 1)
    gst_amount = round(new_price * p["gst_pct"] / 100, 2)

    entry = {
        "product_id":   product_id,
        "product_name": p["name"],
        "old_price":    old_price,
        "new_price":    new_price,
        "change_pct":   change_pct,
        "margin_rs":    margin_rs,
        "margin_pct":   margin_pct,
        "gst_amount":   gst_amount,
        "distributor_pays": round(new_price + gst_amount, 2),
        "updated_at":   utcnow(),
    }
    PRICE_HISTORY.append(entry)

    return json.dumps({"status": "✅ Price updated", **entry})




# ──────────────────────────────────────────────────────────────────────────────
# Dynamic Config Tool  — LLM reasons about optimal parameters per product
# ──────────────────────────────────────────────────────────────────────────────

@tool("suggest_pricing_config")
def suggest_pricing_config(product_id: str) -> str:
    """
    Asks the LLM to suggest optimised pricing parameters for a specific product
    based on its current state: stock level, sales velocity, days since last sale,
    margin headroom, and category.

    Returns suggested values for:
      - min_margin_pct      (floor protection, 10–40%)
      - mrp_headroom_pct    (pricing aggression, 20–95%)
      - markdown_pct        (slow-mover discount, 5–30%)
    along with reasoning for each.

    These suggestions are used by calculate_richfield_price for this product only
    and do NOT overwrite global CONFIG.
    """
    p = PRODUCTS.get(product_id)
    if not p:
        return json.dumps({"error": f"{product_id} not found"})

    if _groq_client is None:
        print("Groq client unavailable, suggest_pricing_config will return defaults without LLM reasoning")
        return json.dumps({
            "product_id":       product_id,
            "min_margin_pct":   CONFIG["min_margin_pct"],
            "mrp_headroom_pct": CONFIG["mrp_headroom_pct"],
            "markdown_pct":     CONFIG["markdown_pct"],
            "reasoning":        "Groq client unavailable — using global CONFIG defaults",
            "source":           "fallback",
        })

    days_no_sale = days_since(p["last_sale_date"])
    is_slow      = days_no_sale >= CONFIG["slow_moving_days"] or p["sales_last_30d"] == 0
    daily_rate   = p["sales_last_30d"] / 30 if p["sales_last_30d"] > 0 else 0
    dos          = round(p["stock_bags"] / daily_rate, 1) if daily_rate > 0 else 999
    prod_cost    = p["production_cost"]
    mrp          = p["mrp"]
    curr_rate    = p["distributor_rate"]
    curr_margin  = round((curr_rate - prod_cost) / curr_rate * 100, 1) if curr_rate > 0 else 0
    max_possible_margin = round((mrp - prod_cost) / mrp * 100, 1)

    prompt = f"""You are the pricing strategist at Richfield Fertilisers Pvt. Ltd., Nashik.
Analyse this product and suggest optimised pricing parameters.

PRODUCT: {p["name"]} ({product_id}) — Category: {p["category"]}
  Production cost : ₹{prod_cost:,.0f}
  Current rate    : ₹{curr_rate:,.0f}  (current margin: {curr_margin}%)
  MRP (ceiling)   : ₹{mrp:,.0f}  (max possible margin: {max_possible_margin}%)
  Stock           : {p["stock_bags"]} bags  ({dos} days of stock)
  Sales last 30d  : {p["sales_last_30d"]} bags  ({daily_rate:.1f}/day)
  Days since sale : {days_no_sale} days
  Slow-moving     : {is_slow}

PARAMETERS TO SUGGEST (with reasoning):
1. min_margin_pct (10–40%): The minimum acceptable margin % on the distributor rate.
   - High-demand products can sustain higher floors
   - Slow/dead stock may need lower floor to enable aggressive markdown
2. mrp_headroom_pct (20–95%): How far to push rate toward MRP.
   - High demand + healthy stock = push higher (80–90%)
   - Overstock or slow = pull back (30–50%)
   - Slow-moving = irrelevant (markdown overrides this)
3. markdown_pct (5–30%): How much to discount a slow-moving product.
   - Recent slowdown (30–60d) = gentle 8–12%
   - Long dead stock (>90d) = aggressive 20–30%
   - Not applicable if product is healthy

Respond ONLY with a JSON object, no markdown, no explanation outside JSON:
{{
  "min_margin_pct": <integer>,
  "mrp_headroom_pct": <integer>,
  "markdown_pct": <integer>,
  "reasoning": {{
    "min_margin_pct": "<one sentence>",
    "mrp_headroom_pct": "<one sentence>",
    "markdown_pct": "<one sentence>"
  }}
}}"""

    try:
        resp = _groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
        )
        raw  = resp.choices[0].message.content.strip()
        # Strip markdown fences if present
        raw  = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)

        # Clamp values to safe ranges
        data["min_margin_pct"]   = max(10, min(40, int(data.get("min_margin_pct",   CONFIG["min_margin_pct"]))))
        data["mrp_headroom_pct"] = max(20, min(95, int(data.get("mrp_headroom_pct", CONFIG["mrp_headroom_pct"]))))
        data["markdown_pct"]     = max(5,  min(30, int(data.get("markdown_pct",     CONFIG["markdown_pct"]))))
        data["product_id"]       = product_id
        data["source"]           = "llm"
        return json.dumps(data)

    except Exception as e:
        return json.dumps({
            "product_id":       product_id,
            "min_margin_pct":   CONFIG["min_margin_pct"],
            "mrp_headroom_pct": CONFIG["mrp_headroom_pct"],
            "markdown_pct":     CONFIG["markdown_pct"],
            "reasoning":        f"LLM call failed ({e}) — using global CONFIG defaults",
            "source":           "fallback",
        })


# ──────────────────────────────────────────────────────────────────────────────
# Pricing Agent
# ──────────────────────────────────────────────────────────────────────────────

pricing_agent = Agent(
    role="Richfield Fertilisers Pricing Strategist",
    goal=(
        "Optimise the selling price of every 25 kg bag grade so that: "
        f"(1) Richfield margin is at least {CONFIG['min_margin_pct']}% above production cost, "
        "(2) price never exceeds MRP, "
        "(3) slow-moving products receive a markdown to stimulate sales, "
        "(4) cash discount impact on effective margin is always considered, "
        "(5) GST is correctly factored into every farmer-facing price."
    ),
    backstory=(
        "You are the Head of Pricing at Richfield Fertilisers Pvt. Ltd., Nashik. "
        "You deeply understand the Maharashtra fertiliser distribution market. "
        "You balance profitability (maximise margin above distributor rate) with "
        "market competitiveness (stay within MRP) and inventory health (markdown slow movers). "
        "You never set a price below the minimum margin floor and never exceed MRP. "
        "Your decisions are always data-driven, explainable, and GST-compliant."
    ),
    tools=[
        fetch_product_data,
        fetch_demand_and_slow_moving_status,
        suggest_pricing_config,
        calculate_richfield_price,
        apply_cash_discount,
        apply_price_update,
    ],
    llm=llm,
    verbose=True,
    allow_delegation=False,
    max_iter=15,
)


# ──────────────────────────────────────────────────────────────────────────────
# Task Factory
# ──────────────────────────────────────────────────────────────────────────────

def create_pricing_task(product_ids: list[str]) -> Task:
    id_list = ", ".join(product_ids)
    return Task(
        description=f"""
        Perform a full pricing optimisation for these Richfield 25 kg bag grades: {id_list}

        For EACH product, follow these steps in order:
        1. fetch_product_data              — get distributor rate, MRP, current price, stock
        2. fetch_demand_and_slow_moving_status — check if slow-moving (no sales in 30 days)
        3. suggest_pricing_config          — get LLM-optimised min_margin_pct, mrp_headroom_pct,
                                             and markdown_pct for THIS product specifically.
                                             Use the returned values instead of global CONFIG
                                             when calling calculate_richfield_price.
        4. calculate_richfield_price       — get recommended ex-GST price using the suggested config
        5. apply_cash_discount             — calculate effective margin for 'advance' payment tier
        6. If recommended price differs from current price by more than 2%,
           call apply_price_update to apply the new price
        7. Record your reasoning and the config values the LLM suggested

        Configuration in effect:
        - Minimum margin: {CONFIG['min_margin_pct']}% above distributor rate
        - Slow-moving threshold: {CONFIG['slow_moving_days']} days without a sale
        - GST rate: {CONFIG['gst_pct']}%
        - Markdown for slow movers: {CONFIG['markdown_pct']}%
        """,
        expected_output=(
            "A complete pricing report table with one row per product:\n"
            "Product ID | Name | Dist. Rate (₹) | Current Price (₹) | "
            "Recommended (₹) | MRP (₹) | Change% | Margin% | GST (₹) | "
            "Farmer Price incl. GST (₹) | Status | Reason"
        ),
        agent=pricing_agent,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────────────────────

def run_pricing_optimization(product_ids: Optional[list] = None) -> str:
    if product_ids is None:
        product_ids = list(PRODUCTS.keys())

    print(f"\n{'='*65}")
    print(f"  🌿  Richfield Pricing Agent — {datetime.now().strftime('%d-%m-%Y %H:%M')}")
    print(f"  Products : {', '.join(product_ids)}")
    print(f"  Min margin: {CONFIG['min_margin_pct']}%  |  GST: {CONFIG['gst_pct']}%  |  Slow-moving: {CONFIG['slow_moving_days']}d")
    print(f"{'='*65}\n")

    task = create_pricing_task(product_ids)
    crew = Crew(
        agents=[pricing_agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )
    result = crew.kickoff()

    print(f"\n{'='*65}")
    print("  ✅  Pricing Optimisation Complete")
    print(f"{'='*65}\n")
    print(result)
    return str(result)


# ──────────────────────────────────────────────────────────────────────────────
# Config update helper (used by API to apply user-set min margin)
# ──────────────────────────────────────────────────────────────────────────────

def update_config(min_margin_pct: Optional[int] = None,
                  slow_moving_days: Optional[int] = None,
                  mrp_headroom_pct: Optional[int] = None):
    if min_margin_pct is not None:
        CONFIG["min_margin_pct"] = min_margin_pct
    if slow_moving_days is not None:
        CONFIG["slow_moving_days"] = slow_moving_days
    if mrp_headroom_pct is not None:
        CONFIG["mrp_headroom_pct"] = mrp_headroom_pct


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run_pricing_optimization()
