import { useState, useEffect, useRef, useCallback } from "react";

const API_BASE = "http://localhost:8000";
const fmt  = (n) => `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits:2, maximumFractionDigits:2 })}`;
const fmtN = (n) => Number(n).toLocaleString("en-IN");
const uid  = () => Math.random().toString(36).slice(2, 8);
const CATEGORY_COLOR = { NPK:"#00e5ff", "NPK+TE":"#a78bfa", Straight:"#facc15", MN:"#fb923c" };
const DOS_COLOR = (dos) => dos < 15 ? "#f87171" : dos < 30 ? "#fb923c" : dos < 90 ? "#4ade80" : "#a78bfa";
const URGENCY_COLOR = { URGENT:"#f87171", HIGH:"#fb923c", MEDIUM:"#facc15", LOW:"#4ade80", none:"var(--muted)" };
const RISK_COLOR = { CRITICAL:"#f87171", HIGH:"#fb923c", MEDIUM:"#facc15" };

const css = `
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Barlow:wght@300;400;600;700&display=swap');
  *, *::before, *::after { box-sizing:border-box; margin:0; padding:0; }
  :root {
    --bg:#0a0c0f; --panel:#0f1318; --border:#1e2530;
    --accent:#00e5ff; --accent2:#ff6b35; --green:#4ade80; --red:#f87171;
    --yellow:#facc15; --purple:#a78bfa; --muted:#4a5568; --text:#c9d1d9;
    --mono:'Share Tech Mono',monospace; --sans:'Barlow',sans-serif;
  }
  body { background:var(--bg); color:var(--text); font-family:var(--sans); min-height:100vh; }

  .header { border-bottom:1px solid var(--border); padding:14px 24px;
    display:flex; align-items:center; justify-content:space-between;
    background:linear-gradient(90deg,#0d1117,#0f1318); }
  .logo { width:38px; height:38px; border:1.5px solid var(--accent);
    display:flex; align-items:center; justify-content:center;
    font-family:var(--mono); font-size:12px; color:var(--accent); position:relative; flex-shrink:0; }
  .logo::before { content:''; position:absolute; inset:-4px; border:1px solid var(--accent); opacity:0.25; }
  .h-title { font-size:14px; font-weight:700; letter-spacing:0.12em; text-transform:uppercase; color:#f0f6ff; }
  .h-sub   { font-size:10px; color:var(--muted); font-family:var(--mono); margin-top:2px; }
  .h-right { display:flex; align-items:center; gap:18px; }
  .dot { width:7px; height:7px; border-radius:50%; background:var(--green);
    box-shadow:0 0 6px var(--green); animation:pulse 2s infinite; }
  .dot.disconnected { background:var(--red); box-shadow:0 0 6px var(--red); animation:none; }
  .dot.connecting   { background:var(--yellow); box-shadow:0 0 6px var(--yellow); }
  .h-status { display:flex; align-items:center; gap:7px; font-family:var(--mono); font-size:11px; color:var(--muted); }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.35} }

  /* Tabs */
  .tab-bar { display:flex; gap:0; border-bottom:1px solid var(--border); background:#0c0f14; padding:0 24px; }
  .tab { padding:11px 20px; font-family:var(--mono); font-size:11px; text-transform:uppercase;
    letter-spacing:0.1em; cursor:pointer; color:var(--muted); border-bottom:2px solid transparent;
    transition:all 0.15s; user-select:none; }
  .tab:hover { color:var(--text); }
  .tab.active { color:var(--accent); border-bottom-color:var(--accent); }

  /* Config bar */
  .config-bar { display:flex; align-items:center; gap:24px; padding:10px 24px;
    border-bottom:1px solid var(--border); background:#0c0f14; flex-wrap:wrap; }
  .cfg-label { font-family:var(--mono); font-size:10px; color:var(--muted); text-transform:uppercase; letter-spacing:0.1em; }
  .cfg-value { font-family:var(--mono); font-size:13px; color:var(--accent); margin-left:8px; }
  .cfg-input { background:transparent; border:1px solid var(--border); color:var(--accent);
    font-family:var(--mono); font-size:13px; width:60px; padding:3px 7px; border-radius:2px;
    margin-left:8px; outline:none; }
  .cfg-input:focus { border-color:var(--accent); }
  .apply-btn { padding:5px 14px; background:transparent; border:1px solid var(--accent);
    color:var(--accent); font-family:var(--mono); font-size:11px; cursor:pointer;
    text-transform:uppercase; transition:all 0.2s; }
  .apply-btn:hover { background:var(--accent); color:#0a0c0f; }
  .divider { width:1px; height:20px; background:var(--border); margin:0 4px; }

  /* Layout */
  .main { display:grid; grid-template-columns:1fr 300px; height:calc(100vh - 152px); overflow:hidden; }
  .main.no-side { grid-template-columns:1fr; }

  /* Stats */
  .stats-bar { display:flex; gap:1px; background:var(--border); border-bottom:1px solid var(--border); }
  .stat { flex:1; padding:12px 18px; background:var(--panel); }
  .stat-label { font-size:10px; text-transform:uppercase; letter-spacing:0.12em; color:var(--muted); font-family:var(--mono); }
  .stat-value { font-size:20px; font-weight:700; color:#e2e8f0; font-family:var(--mono); margin-top:2px; }
  .stat-sub   { font-size:10px; color:var(--muted); margin-top:1px; }

  /* Table panel */
  .table-panel { overflow-y:auto; border-right:1px solid var(--border); display:flex; flex-direction:column; }
  .tbl-header { padding:12px 18px; display:flex; align-items:center; justify-content:space-between;
    border-bottom:1px solid var(--border); position:sticky; top:0; background:var(--panel); z-index:10; }
  .tbl-title { font-size:10px; text-transform:uppercase; letter-spacing:0.14em; color:var(--muted); font-family:var(--mono); }
  .btn-row { display:flex; gap:7px; }
  .run-btn { padding:7px 16px; background:transparent; border:1px solid var(--accent);
    color:var(--accent); font-family:var(--mono); font-size:11px; letter-spacing:0.08em;
    cursor:pointer; text-transform:uppercase; transition:all 0.2s; }
  .run-btn:hover:not(:disabled) { background:var(--accent); color:#0a0c0f; }
  .run-btn:disabled { opacity:0.4; cursor:not-allowed; }
  .run-btn.running  { border-color:var(--accent2); color:var(--accent2); animation:bPulse 1s infinite; }
  .run-btn.sm { font-size:10px; padding:7px 11px; border-color:var(--muted); color:var(--muted); }
  .run-btn.sm:hover:not(:disabled) { background:var(--muted); color:#0a0c0f; }
  .run-btn.orange { border-color:var(--accent2); color:var(--accent2); }
  .run-btn.orange:hover:not(:disabled) { background:var(--accent2); color:#0a0c0f; }
  .run-btn.purple { border-color:var(--purple); color:var(--purple); }
  .run-btn.purple:hover:not(:disabled) { background:var(--purple); color:#0a0c0f; }
  @keyframes bPulse { 0%,100%{opacity:1} 50%{opacity:0.45} }

  table { width:100%; border-collapse:collapse; }
  thead th { padding:9px 14px; text-align:left; font-size:9px; text-transform:uppercase;
    letter-spacing:0.12em; color:var(--muted); font-family:var(--mono); font-weight:400;
    border-bottom:1px solid var(--border); background:var(--bg); white-space:nowrap; }
  tbody tr { border-bottom:1px solid var(--border); transition:background 0.12s; cursor:pointer; }
  tbody tr:hover { background:#141920; }
  tbody tr.selected { background:#0d1a24; border-left:2px solid var(--accent); }
  tbody tr.flash { animation:rowFlash 1s ease; }
  @keyframes rowFlash { 0%{background:#0d2a1a} 100%{background:transparent} }
  td { padding:12px 14px; font-size:12px; vertical-align:middle; }
  .pid   { font-family:var(--mono); font-size:10px; color:var(--muted); }
  .pname { color:#e2e8f0; font-size:12px; font-weight:500; }
  .cat-chip { display:inline-block; font-family:var(--mono); font-size:9px;
    padding:1px 5px; border-radius:2px; margin-top:2px; background:rgba(255,255,255,0.05); }
  .mono { font-family:var(--mono); }
  .price-up   { color:var(--green); font-family:var(--mono); font-weight:600; }
  .price-down { color:var(--red);   font-family:var(--mono); font-weight:600; }
  .price-same { color:var(--text);  font-family:var(--mono); }
  .badge { display:inline-block; padding:2px 6px; border-radius:2px; font-family:var(--mono); font-size:10px; font-weight:600; }
  .badge-up   { background:rgba(74,222,128,0.12); color:var(--green); }
  .badge-down { background:rgba(248,113,113,0.12); color:var(--red); }
  .badge-flat { background:rgba(148,163,184,0.08); color:var(--muted); }
  .loading-msg { text-align:center; padding:40px; font-family:var(--mono); font-size:11px; color:var(--muted); }

  /* Side panel */
  .side { display:flex; flex-direction:column; overflow:hidden; }
  .feed-wrap { flex:1; overflow:hidden; display:flex; flex-direction:column; border-bottom:1px solid var(--border); }
  .panel-hdr { padding:12px 14px; border-bottom:1px solid var(--border); display:flex; align-items:center; justify-content:space-between; }
  .panel-title { font-size:10px; text-transform:uppercase; letter-spacing:0.14em; color:var(--muted); font-family:var(--mono); }
  .feed-list { flex:1; overflow-y:auto; }
  .feed-item { padding:9px 14px; border-bottom:1px solid rgba(30,37,48,0.5); animation:fSlide 0.3s ease; }
  @keyframes fSlide { from{opacity:0;transform:translateY(-5px)} to{opacity:1;transform:translateY(0)} }
  .feed-time { font-family:var(--mono); font-size:9px; color:var(--muted); }
  .feed-msg  { font-size:11px; line-height:1.45; margin-top:2px; }
  .tag { display:inline-block; font-family:var(--mono); font-size:9px; padding:1px 5px; border-radius:2px; margin-right:4px; }
  .tag-info   { background:rgba(0,229,255,0.1);  color:var(--accent); }
  .tag-update { background:rgba(74,222,128,0.1); color:var(--green); }
  .tag-warn   { background:rgba(248,113,113,0.1);color:var(--red); }
  .tag-agent  { background:rgba(255,107,53,0.1); color:var(--accent2); }
  .tag-error  { background:rgba(248,113,113,0.2);color:var(--red); }
  .hist-wrap { height:220px; display:flex; flex-direction:column; }
  .hist-list  { flex:1; overflow-y:auto; }
  .hist-item  { padding:9px 14px; border-bottom:1px solid rgba(30,37,48,0.5); display:flex; justify-content:space-between; }
  .hist-id   { font-family:var(--mono); font-size:10px; color:var(--accent); }
  .hist-name { font-size:11px; color:var(--muted); margin-top:1px; }
  .hist-time { font-family:var(--mono); font-size:9px; color:var(--muted); margin-top:2px; }
  .empty-msg { padding:18px 14px; font-family:var(--mono); font-size:10px; color:var(--muted); }

  /* Detail pane */
  .detail { position:fixed; right:300px; top:152px; bottom:0; width:270px;
    background:#0d1117; border-left:1px solid var(--border);
    padding:18px; overflow-y:auto; animation:slideIn 0.2s ease; z-index:30; }
  @keyframes slideIn { from{opacity:0;transform:translateX(18px)} to{opacity:1;transform:translateX(0)} }
  .d-id   { font-family:var(--mono); font-size:10px; color:var(--accent); }
  .d-name { font-size:14px; font-weight:600; color:#f0f6ff; margin:3px 0 6px; }
  .d-label { font-size:9px; text-transform:uppercase; letter-spacing:0.12em; color:var(--muted); font-family:var(--mono); margin:14px 0 3px; }
  .d-val   { font-family:var(--mono); font-size:13px; color:#e2e8f0; }
  .meter { height:3px; background:var(--border); border-radius:2px; overflow:hidden; margin-top:5px; }
  .meter-fill { height:100%; border-radius:2px; }
  .reason-chip { display:block; font-size:10px; padding:4px 7px; background:rgba(255,255,255,0.04); border-radius:2px; margin-top:3px; font-family:var(--mono); color:var(--text); }
  .close-btn { float:right; background:none; border:none; color:var(--muted); cursor:pointer; font-size:15px; }
  .gst-box { background:rgba(0,229,255,0.05); border:1px solid rgba(0,229,255,0.15); border-radius:3px; padding:10px 12px; margin-top:10px; }
  .gst-row { display:flex; justify-content:space-between; font-family:var(--mono); font-size:11px; margin-top:4px; }
  .gst-row:first-child { margin-top:0; }
  .err-banner { padding:9px 20px; background:rgba(248,113,113,0.1); border-bottom:1px solid var(--red); font-family:var(--mono); font-size:11px; color:var(--red); }

  /* Inventory specific */
  .dos-bar { height:3px; border-radius:2px; margin-top:4px; overflow:hidden; background:var(--border); }

  /* Supplier specific */
  .supplier-card { background:var(--panel); border:1px solid var(--border); border-radius:3px; padding:14px; margin-bottom:10px; }
  .supplier-card:hover { border-color:var(--accent); }
  .rel-stars { font-family:var(--mono); font-size:12px; color:var(--yellow); }
  .po-item { padding:10px 14px; border-bottom:1px solid var(--border); }
  .risk-chip { display:inline-block; padding:2px 6px; border-radius:2px; font-family:var(--mono); font-size:10px; margin:2px; }

  ::-webkit-scrollbar { width:3px; }
  ::-webkit-scrollbar-track { background:var(--bg); }
  ::-webkit-scrollbar-thumb { background:var(--border); }
`;

// ─── Pricing Tab ──────────────────────────────────────────────────────────────
function PricingTab({ feed, history, running, setRunning, addFeed, config, setConfig }) {
  const [products, setProducts]   = useState([]);
  const [selected, setSelected]   = useState(null);
  const [flashIds, setFlashIds]   = useState(new Set());
  const [error, setError]         = useState(null);
  const [marginInput, setMarginInput]   = useState("20");
  const [headroomInput, setHeadroomInput] = useState("80");
  const [llmSug, setLlmSug]               = useState(null);
  const [sugLoading, setSugLoading]       = useState(false);

  const fetchProducts = useCallback(async () => {
    try {
      const res  = await fetch(`${API_BASE}/products`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setProducts(data.products);
      if (data.config) setConfig(data.config);
      setError(null);
    } catch (e) {
      setError(`Cannot reach API at ${API_BASE} — run: uvicorn api:app --reload --port 8000`);
    }
  }, [setConfig]);

  useEffect(() => { fetchProducts(); }, []);

  const fetchSuggestion = async (product_id) => {
    setSugLoading(true); setLlmSug(null);
    try {
      const res  = await fetch(`${API_BASE}/suggest/${product_id}`);
      const data = await res.json();
      setLlmSug(data);
    } catch (e) { /* ignore */ }
    finally { setSugLoading(false); }
  };

  const applyMargin = async () => {
    const val = parseInt(marginInput);
    if (isNaN(val) || val < 1 || val > 80) { setError("Min margin must be 1–80%"); return; }
    await fetch(`${API_BASE}/config`, { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ min_margin_pct: val }) });
    setConfig(c => ({ ...c, min_margin_pct: val }));
    addFeed("info", `⚙ Min margin → ${val}%`);
    fetchProducts();
  };

  const applyHeadroom = async () => {
    const val = parseInt(headroomInput);
    if (isNaN(val) || val < 10 || val > 100) { setError("Headroom must be 10–100%"); return; }
    await fetch(`${API_BASE}/config`, { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ mrp_headroom_pct: val }) });
    setConfig(c => ({ ...c, mrp_headroom_pct: val }));
    addFeed("info", `⚙ MRP headroom → ${val}%`);
    fetchProducts();
  };

  const runOptimization = async (ids = null) => {
    if (running) return;
    setRunning(true); setError(null);
    try {
      const res = await fetch(`${API_BASE}/optimize`, { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ product_ids: ids }) });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail || `HTTP ${res.status}`); }
      const data = await res.json();
      addFeed("agent", `Job ${data.job_id} dispatched — ${data.product_ids.length} product(s)`);
    } catch (e) { setError(e.message); setRunning(false); }
  };

  const slowCount  = products.filter(p => p.is_slow_moving).length;
  const totalStock = products.reduce((a, p) => a + p.stock_bags, 0);
  const totalValue = products.reduce((a, p) => a + p.current_rate * p.stock_bags, 0);
  const avgMargin  = products.length ? (products.reduce((a, p) => a + p.recommended_margin_pct, 0) / products.length).toFixed(1) : "—";

  return (
    <>
      <div className="config-bar">
        <div style={{ display:"flex", alignItems:"center" }}>
          <span className="cfg-label">Min Margin %</span>
          <input className="cfg-input" type="number" min="1" max="80" value={marginInput}
            onChange={e => setMarginInput(e.target.value)} onKeyDown={e => e.key==="Enter" && applyMargin()} />
        </div>
        <button className="apply-btn" onClick={applyMargin}>Apply</button>
        <div className="divider" />
        <div style={{ display:"flex", alignItems:"center" }}>
          <span className="cfg-label">MRP Headroom %</span>
          <input className="cfg-input" type="number" min="10" max="100" value={headroomInput}
            onChange={e => setHeadroomInput(e.target.value)} onKeyDown={e => e.key==="Enter" && applyHeadroom()} />
        </div>
        <button className="apply-btn" onClick={applyHeadroom}>Apply</button>
        <div className="divider" />
        <div style={{ display:"flex", alignItems:"center" }}>
          <span className="cfg-label">Slow-moving</span>
          <span className="cfg-value">{config.slow_moving_days}d</span>
        </div>
        <div style={{ display:"flex", alignItems:"center" }}>
          <span className="cfg-label">GST</span><span className="cfg-value">5%</span>
        </div>
        <div style={{ display:"flex", alignItems:"center" }}>
          <span className="cfg-label">Markdown</span><span className="cfg-value">10%</span>
        </div>
      </div>

      {error && <div className="err-banner">⚠ {error}</div>}

      <div className="main">
        <div style={{ gridColumn:"1/-1" }}>
          <div className="stats-bar">
            {[
              { label:"Products",        value: products.length || "—",                        sub:"25 kg bag grades" },
              { label:"Total Stock",     value: totalStock ? `${fmtN(totalStock)} bags` : "—", sub:"in warehouse" },
              { label:"Inventory Value", value: totalValue ? `₹${(totalValue/100000).toFixed(1)}L` : "—", sub:"at current rates" },
              { label:"Avg Margin",      value: products.length ? `${avgMargin}%` : "—",       sub:"on recommended rate" },
              { label:"Slow-Moving",     value: slowCount,                                      sub:"need markdown" },
              { label:"Price Changes",   value: history.length,                                 sub:"in history" },
            ].map(s => (
              <div className="stat" key={s.label}>
                <div className="stat-label">{s.label}</div>
                <div className="stat-value">{s.value}</div>
                <div className="stat-sub">{s.sub}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="table-panel">
          <div className="tbl-header">
            <span className="tbl-title">25 KG Bag Price Dashboard</span>
            <div className="btn-row">
              <button className="run-btn sm" onClick={fetchProducts} disabled={running}>↻ Refresh</button>
              <button className={`run-btn ${running ? "running" : ""}`} onClick={() => runOptimization()} disabled={running}>
                {running ? "⟳ Optimising..." : "▶ Run Optimisation"}
              </button>
            </div>
          </div>
          <table>
            <thead><tr>
              <th>Product</th><th>Prod. Cost</th><th>Distributor Rate</th>
              <th>Recommended</th><th>MRP</th><th>Chg%</th><th>RF Margin%</th>
              <th>Distributor Pays (incl. GST)</th><th>Stock</th><th>Status</th>
            </tr></thead>
            <tbody>
              {products.length === 0
                ? <tr><td colSpan={10} className="loading-msg">{error ? "⚠ Cannot load" : "⟳ Loading..."}</td></tr>
                : products.map(p => {
                  const diff = p.recommended_rate - p.current_rate;
                  const pct  = p.current_rate ? ((diff / p.current_rate) * 100).toFixed(1) : "0.0";
                  const dir  = diff > 0.5 ? "up" : diff < -0.5 ? "down" : "same";
                  return (
                    <tr key={p.product_id}
                      className={`${selected === p.product_id ? "selected" : ""} ${flashIds.has(p.product_id) ? "flash" : ""}`}
                      onClick={() => {
                const next = selected === p.product_id ? null : p.product_id;
                setSelected(next);
                if (next) fetchSuggestion(next);
              }}>
                      <td>
                        <div className="pid">{p.product_id}</div>
                        <div className="pname">{p.name}</div>
                        <div className="cat-chip" style={{ color: CATEGORY_COLOR[p.category] || "var(--muted)" }}>{p.category}</div>
                      </td>
                      <td><span className="mono" style={{ color:"var(--muted)", fontSize:11 }}>{fmt(p.production_cost)}</span></td>
                      <td><span className="mono">{fmt(p.current_rate)}</span></td>
                      <td><span className={`price-${dir}`}>{fmt(p.recommended_rate)}</span></td>
                      <td><span className="mono" style={{ color:"var(--muted)", fontSize:11 }}>{fmt(p.mrp)}</span></td>
                      <td><span className={`badge badge-${dir === "same" ? "flat" : dir}`}>{dir==="up" ? "+" : ""}{pct}%</span></td>
                      <td>
                        <span className="mono">{p.recommended_margin_pct}%</span>
                        <div style={{ height:2, background:"var(--border)", borderRadius:1, marginTop:3, width:40, overflow:"hidden" }}>
                          <div style={{ height:"100%", width:`${Math.min(p.recommended_margin_pct,60)/60*100}%`,
                            background: p.recommended_margin_pct >= config.min_margin_pct ? "var(--green)" : "var(--red)", borderRadius:1 }} />
                        </div>
                      </td>
                      <td><span className="mono" style={{ color:"var(--accent)", fontSize:12 }}>{fmt(p.distributor_pays_incl_gst)}</span></td>
                      <td>
                        <div className="stock-mini" style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--muted)" }}>{p.stock_bags} bags</div>
                        <div style={{ fontSize:10, color:"var(--muted)", fontFamily:"var(--mono)" }}>
                          {p.days_of_stock === 999 ? "∞ days" : `${p.days_of_stock}d`}
                        </div>
                      </td>
                      <td>
                        <span style={{ fontFamily:"var(--mono)", fontSize:10, padding:"2px 7px", borderRadius:10,
                          background: p.is_slow_moving ? "rgba(248,113,113,0.1)" : "rgba(74,222,128,0.1)",
                          color: p.is_slow_moving ? "var(--red)" : "var(--green)" }}>
                          {p.is_slow_moving ? "▼ Slow" : "● Healthy"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>

        <div className="side">
          <div className="feed-wrap">
            <div className="panel-hdr">
              <span className="panel-title">Agent Activity</span>
              <span style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--muted)" }}>{feed.length} events</span>
            </div>
            <div className="feed-list">
              {feed.length === 0 ? <div className="empty-msg">Waiting for events...</div>
                : feed.map(f => (
                  <div className="feed-item" key={f.id}>
                    <div className="feed-time">{f.time}</div>
                    <div className="feed-msg"><span className={`tag tag-${f.tag}`}>{f.tag.toUpperCase()}</span>{f.msg}</div>
                  </div>
                ))}
            </div>
          </div>
          <div className="hist-wrap">
            <div className="panel-hdr">
              <span className="panel-title">Price History</span>
              <span style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--muted)" }}>{history.length} changes</span>
            </div>
            <div className="hist-list">
              {history.length === 0 ? <div className="empty-msg">No changes yet.</div>
                : history.map((h, i) => (
                  <div className="hist-item" key={i}>
                    <div>
                      <div className="hist-id">{h.product_id}</div>
                      <div className="hist-name">{h.name}</div>
                    </div>
                    <div style={{ textAlign:"right" }}>
                      <div style={{ fontFamily:"var(--mono)", fontSize:11, color: h.adj_pct > 0 ? "var(--green)" : "var(--red)" }}>
                        {h.adj_pct > 0 ? "+" : ""}{h.adj_pct}%
                      </div>
                      <div className="hist-time">{new Date(h.timestamp).toLocaleTimeString("en-IN")}</div>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        </div>
      </div>

      {selected && (() => {
        const p = products.find(x => x.product_id === selected);
        if (!p) return null;
        return (
          <div className="detail">
            <button className="close-btn" onClick={() => setSelected(null)}>✕</button>
            <div className="d-id">{p.product_id} · {p.pack}</div>
            <div className="d-name">{p.name}</div>
            <div className="cat-chip" style={{ color: CATEGORY_COLOR[p.category] || "var(--muted)" }}>{p.category}</div>
            <div className="gst-box" style={{ marginTop:14 }}>
              <div style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--accent)", textTransform:"uppercase", letterSpacing:"0.1em", marginBottom:6 }}>Distributor Billing Breakdown</div>
              <div className="gst-row"><span style={{ color:"var(--muted)" }}>Distributor rate (ex-GST)</span><span>{fmt(p.recommended_rate)}</span></div>
              <div className="gst-row"><span style={{ color:"var(--muted)" }}>GST @ {p.gst_pct}%</span><span style={{ color:"var(--yellow)" }}>+ {fmt(p.gst_amount)}</span></div>
              <div className="gst-row" style={{ borderTop:"1px solid rgba(0,229,255,0.1)", paddingTop:4, marginTop:4 }}>
                <span style={{ color:"var(--accent)" }}>Distributor pays Richfield</span>
                <span style={{ color:"var(--accent)", fontWeight:600 }}>{fmt(p.distributor_pays_incl_gst)}</span>
              </div>
            </div>
            <div className="d-label">Production Cost</div>
            <div className="d-val">{fmt(p.production_cost)}</div>
            <div className="d-label">Rate Range <span style={{ color:"var(--accent2)", fontSize:9 }}>headroom {config.mrp_headroom_pct}%</span></div>
            <div className="d-val" style={{ fontSize:11 }}>{fmt(p.min_allowed)} → {fmt(p.mrp)} (MRP)</div>
            <div className="meter">
              <div className="meter-fill" style={{ width:`${((p.recommended_rate - p.min_allowed) / (p.mrp - p.min_allowed)) * 100}%`, background:"linear-gradient(90deg, var(--accent), var(--green))" }} />
            </div>
            <div className="d-label">Richfield Margin (ex-GST)</div>
            <div className="d-val">{p.recommended_margin_pct}% = {fmt(p.margin_rs)} / bag</div>
            <div className="d-label">Effective Margin (after 7% advance discount)</div>
            <div className="d-val">{p.effective_margin_pct}%</div>
            <div className="d-label">Inventory</div>
            <div className="d-val">{p.stock_bags} bags · {p.days_of_stock === 999 ? "no recent sales" : `${p.days_of_stock}d of stock`}</div>
            <div className="d-label">Sales (last 30d)</div>
            <div className="d-val">{p.sales_last_30d} bags · {p.days_since_last_sale}d since last sale</div>
            <div className="d-label">Pricing Reason</div>
            <span className="reason-chip">{p.reason}</span>

            {/* LLM Suggestions panel */}
            <div className="d-label" style={{ marginTop:18 }}>🤖 LLM Config Suggestions</div>
            {sugLoading && <div style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--muted)", marginTop:6 }}>⟳ Asking LLM...</div>}
            {llmSug && llmSug.product_id === p.product_id && (
              <div style={{ background:"rgba(0,229,255,0.03)", border:"1px solid rgba(0,229,255,0.12)", borderRadius:3, padding:"10px 12px", marginTop:6 }}>
                {/* Pricing suggestions */}
                <div style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--accent)", textTransform:"uppercase", letterSpacing:"0.1em", marginBottom:8 }}>Pricing</div>
                {llmSug.pricing && !llmSug.pricing.error && (
                  <>
                    {[
                      { label:"Min Margin",   val:`${llmSug.pricing.min_margin_pct}%`,   reason: llmSug.pricing.reasoning?.min_margin_pct },
                      { label:"MRP Headroom", val:`${llmSug.pricing.mrp_headroom_pct}%`, reason: llmSug.pricing.reasoning?.mrp_headroom_pct },
                      { label:"Markdown",     val:`${llmSug.pricing.markdown_pct}%`,     reason: llmSug.pricing.reasoning?.markdown_pct },
                    ].map(r => (
                      <div key={r.label} style={{ marginBottom:7 }}>
                        <div style={{ display:"flex", justifyContent:"space-between" }}>
                          <span style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--muted)" }}>{r.label}</span>
                          <span style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--yellow)", fontWeight:600 }}>{r.val}</span>
                        </div>
                        {r.reason && <div style={{ fontSize:10, color:"var(--muted)", marginTop:2, lineHeight:1.4 }}>{r.reason}</div>}
                      </div>
                    ))}
                    <div style={{ fontFamily:"var(--mono)", fontSize:9, color: llmSug.pricing.source === "llm" ? "var(--green)" : "var(--muted)", marginTop:4 }}>
                      source: {llmSug.pricing.source}
                    </div>
                  </>
                )}

                {/* Inventory suggestions */}
                <div style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--accent2)", textTransform:"uppercase", letterSpacing:"0.1em", margin:"10px 0 8px" }}>Inventory</div>
                {llmSug.inventory && !llmSug.inventory.error && (
                  <>
                    {[
                      { label:"Target DoS",       val:`${llmSug.inventory.target_dos}d`,        reason: llmSug.inventory.reasoning?.target_dos },
                      { label:"Safety Stock",     val:`${llmSug.inventory.safety_stock_days}d`,  reason: llmSug.inventory.reasoning?.safety_stock_days },
                    ].map(r => (
                      <div key={r.label} style={{ marginBottom:7 }}>
                        <div style={{ display:"flex", justifyContent:"space-between" }}>
                          <span style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--muted)" }}>{r.label}</span>
                          <span style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--yellow)", fontWeight:600 }}>{r.val}</span>
                        </div>
                        {r.reason && <div style={{ fontSize:10, color:"var(--muted)", marginTop:2, lineHeight:1.4 }}>{r.reason}</div>}
                      </div>
                    ))}
                    <div style={{ fontFamily:"var(--mono)", fontSize:9, color: llmSug.inventory.source === "llm" ? "var(--green)" : "var(--muted)", marginTop:4 }}>
                      source: {llmSug.inventory.source}
                    </div>
                  </>
                )}

                {/* Supplier suggestions */}
                <div style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--purple)", textTransform:"uppercase", letterSpacing:"0.1em", margin:"10px 0 8px" }}>Supplier Strategy</div>
                {llmSug.supplier && !llmSug.supplier.error && (
                  <>
                    {[
                      { label:"Order Now",       val: llmSug.supplier.order_now ? "Yes" : "Wait",    reason: llmSug.supplier.reasoning?.order_now },
                      { label:"Buffer Qty",      val:`+${llmSug.supplier.quantity_buffer_pct}%`,      reason: llmSug.supplier.reasoning?.quantity_buffer_pct },
                      { label:"Prioritise",      val: llmSug.supplier.prioritise,                     reason: llmSug.supplier.reasoning?.prioritise },
                      { label:"Split Order",     val: llmSug.supplier.split_order ? "Yes" : "No",     reason: llmSug.supplier.reasoning?.split_order },
                    ].map(r => (
                      <div key={r.label} style={{ marginBottom:7 }}>
                        <div style={{ display:"flex", justifyContent:"space-between" }}>
                          <span style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--muted)" }}>{r.label}</span>
                          <span style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--yellow)", fontWeight:600 }}>{r.val}</span>
                        </div>
                        {r.reason && <div style={{ fontSize:10, color:"var(--muted)", marginTop:2, lineHeight:1.4 }}>{r.reason}</div>}
                      </div>
                    ))}
                    <div style={{ fontFamily:"var(--mono)", fontSize:9, color: llmSug.supplier.source === "llm" ? "var(--green)" : "var(--muted)", marginTop:4 }}>
                      source: {llmSug.supplier.source}
                    </div>
                  </>
                )}
              </div>
            )}

            <div className="d-label" style={{ marginTop:18 }}>Actions</div>
            <button className="run-btn" style={{ width:"100%", marginTop:6 }} disabled={running}
              onClick={() => { setSelected(null); runOptimization([p.product_id]); }}>
              Optimise This Product
            </button>
          </div>
        );
      })()}
    </>
  );
}

// ─── Inventory Tab ────────────────────────────────────────────────────────────
function InventoryTab({ feed, running, setRunning, addFeed }) {
  const [inv, setInv]             = useState(null);
  const [selected, setSelected]   = useState(null);
  const [targetDos, setTargetDos] = useState("60");
  const [critDos, setCritDos]     = useState("15");
  const [error, setError]         = useState(null);

  const fetchInv = useCallback(async () => {
    try {
      const res  = await fetch(`${API_BASE}/inventory`);
      const data = await res.json();
      setInv(data);
      setError(null);
    } catch (e) { setError("Cannot reach /inventory endpoint"); }
  }, []);

  useEffect(() => { fetchInv(); }, []);

  const applyInvConfig = async () => {
    const td = parseInt(targetDos), cd = parseInt(critDos);
    await fetch(`${API_BASE}/inventory/config`, { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ target_dos: td, critical_dos_threshold: cd }) });
    addFeed("info", `⚙ Inventory config → target ${td}d, critical <${cd}d`);
    fetchInv();
  };

  const runAudit = async () => {
    if (running) return;
    setRunning(true);
    try {
      await fetch(`${API_BASE}/inventory/audit`, { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({}) });
      addFeed("agent", "📦 Inventory audit dispatched");
      setTimeout(fetchInv, 3000);
    } catch (e) { setError(e.message); setRunning(false); }
  };

  if (!inv) return <div className="loading-msg">{error || "⟳ Loading inventory..."}</div>;

  const sc = inv.status_counts;
  const products = inv.products || [];
  const selProd  = products.find(p => p.product_id === selected);

  return (
    <>
      <div className="config-bar">
        <div style={{ display:"flex", alignItems:"center" }}>
          <span className="cfg-label">Target DoS</span>
          <input className="cfg-input" type="number" min="20" max="120" value={targetDos} onChange={e => setTargetDos(e.target.value)} />
          <span className="cfg-label" style={{ marginLeft:4 }}>days</span>
        </div>
        <div style={{ display:"flex", alignItems:"center" }}>
          <span className="cfg-label">Critical &lt;</span>
          <input className="cfg-input" type="number" min="5" max="30" value={critDos} onChange={e => setCritDos(e.target.value)} />
          <span className="cfg-label" style={{ marginLeft:4 }}>days</span>
        </div>
        <button className="apply-btn" onClick={applyInvConfig}>Apply</button>
        <div className="divider" />
        <div style={{ display:"flex", alignItems:"center" }}>
          <span className="cfg-label">Warehouse</span>
          <span className="cfg-value">{inv.utilisation_pct}% full</span>
        </div>
        <div style={{ display:"flex", alignItems:"center" }}>
          <span className="cfg-label">Safety Stock</span>
          <span className="cfg-value">{inv.config?.safety_stock_days}d</span>
        </div>
      </div>

      {error && <div className="err-banner">⚠ {error}</div>}

      <div className="main no-side" style={{ gridTemplateColumns:"1fr" }}>
        <div style={{ gridColumn:"1/-1" }}>
          <div className="stats-bar">
            {[
              { label:"Total Stock",    value:`${fmtN(inv.total_bags)} bags`,              sub:`${inv.utilisation_pct}% of capacity` },
              { label:"Inventory Value",value:`₹${(inv.total_value_rs/100000).toFixed(1)}L`, sub:"at current rates" },
              { label:"Critical",       value: sc.critical || 0,  sub:"stockout risk < 15d" },
              { label:"Low",            value: sc.low || 0,       sub:"reorder soon < 30d" },
              { label:"Healthy",        value: sc.healthy || 0,   sub:"30–90 days of stock" },
              { label:"Overstock",      value: (sc.overstock||0) + (sc.dead_stock||0), sub:"pause production" },
            ].map(s => (
              <div className="stat" key={s.label}>
                <div className="stat-label">{s.label}</div>
                <div className="stat-value">{s.value}</div>
                <div className="stat-sub">{s.sub}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="table-panel" style={{ borderRight:"none" }}>
          <div className="tbl-header">
            <span className="tbl-title">Warehouse Stock Levels</span>
            <div className="btn-row">
              <button className="run-btn sm" onClick={fetchInv} disabled={running}>↻ Refresh</button>
              <button className={`run-btn orange ${running ? "running" : ""}`} onClick={runAudit} disabled={running}>
                {running ? "⟳ Auditing..." : "📦 Run Inventory Audit"}
              </button>
            </div>
          </div>
          <table>
            <thead><tr>
              <th>Product</th><th>Stock (bags)</th><th>Sales / 30d</th>
              <th>Daily Rate</th><th>Days of Stock</th><th>DoS Meter</th>
              <th>Reorder Qty</th><th>Reorder Value</th><th>Urgency</th><th>Status</th>
            </tr></thead>
            <tbody>
              {products.map(p => (
                <tr key={p.product_id}
                  className={selected === p.product_id ? "selected" : ""}
                  onClick={() => {
                const next = selected === p.product_id ? null : p.product_id;
                setSelected(next);
                if (next) fetchSuggestion(next);
              }}>
                  <td>
                    <div className="pid">{p.product_id}</div>
                    <div className="pname">{p.name}</div>
                    <div className="cat-chip" style={{ color: CATEGORY_COLOR[p.category] || "var(--muted)" }}>{p.category}</div>
                  </td>
                  <td><span className="mono">{fmtN(p.stock_bags)}</span></td>
                  <td><span className="mono">{p.sales_last_30d} bags</span></td>
                  <td><span className="mono" style={{ color:"var(--muted)", fontSize:11 }}>{p.daily_sales_rate}/day</span></td>
                  <td>
                    <span className="mono" style={{ color: DOS_COLOR(p.days_of_stock) }}>
                      {p.days_of_stock === 999 ? "∞" : `${p.days_of_stock}d`}
                    </span>
                  </td>
                  <td style={{ width:100 }}>
                    <div className="dos-bar">
                      <div style={{ height:"100%", width:`${Math.min((p.days_of_stock === 999 ? 200 : p.days_of_stock) / 120 * 100, 100)}%`,
                        background: DOS_COLOR(p.days_of_stock), borderRadius:2 }} />
                    </div>
                  </td>
                  <td>
                    {p.reorder_qty > 0
                      ? <span className="mono" style={{ color:"var(--yellow)" }}>{fmtN(p.reorder_qty)} bags</span>
                      : <span style={{ color:"var(--muted)", fontFamily:"var(--mono)", fontSize:11 }}>—</span>}
                  </td>
                  <td>
                    {p.reorder_value_rs > 0
                      ? <span className="mono" style={{ fontSize:11 }}>{fmt(p.reorder_value_rs)}</span>
                      : <span style={{ color:"var(--muted)", fontFamily:"var(--mono)", fontSize:11 }}>—</span>}
                  </td>
                  <td>
                    <span style={{ fontFamily:"var(--mono)", fontSize:10, color: URGENCY_COLOR[p.urgency] || "var(--muted)" }}>
                      {p.urgency}
                    </span>
                  </td>
                  <td>
                    <span style={{ fontFamily:"var(--mono)", fontSize:10, padding:"2px 6px", borderRadius:2,
                      background: p.stock_status === "critical" ? "rgba(248,113,113,0.15)"
                        : p.stock_status === "low" ? "rgba(251,146,60,0.15)"
                        : p.stock_status === "overstock" || p.stock_status === "dead_stock" ? "rgba(167,139,250,0.15)"
                        : "rgba(74,222,128,0.1)",
                      color: p.stock_status === "critical" ? "var(--red)"
                        : p.stock_status === "low" ? "var(--accent2)"
                        : p.stock_status === "overstock" || p.stock_status === "dead_stock" ? "var(--purple)"
                        : "var(--green)" }}>
                      {p.stock_status.replace("_", " ").toUpperCase()}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Reorder log */}
          {inv.reorder_log?.length > 0 && (
            <div style={{ borderTop:"1px solid var(--border)", padding:"12px 18px" }}>
              <div className="tbl-title" style={{ marginBottom:10 }}>Reorder Log</div>
              <table>
                <thead><tr>
                  <th>Product</th><th>Qty</th><th>Order Value</th><th>Urgency</th><th>Status</th><th>Time</th>
                </tr></thead>
                <tbody>
                  {inv.reorder_log.map((r, i) => (
                    <tr key={i}>
                      <td><span className="pid">{r.product_id}</span><br /><span style={{ fontSize:11 }}>{r.product_name}</span></td>
                      <td><span className="mono">{fmtN(r.total_order_bags)} bags</span></td>
                      <td><span className="mono">{fmt(r.order_value_rs)}</span></td>
                      <td><span style={{ fontFamily:"var(--mono)", fontSize:10, color: URGENCY_COLOR[r.urgency?.split(" ")[0]] }}>{r.urgency}</span></td>
                      <td><span style={{ fontFamily:"var(--mono)", fontSize:10, color: r.status === "ordered" ? "var(--green)" : "var(--yellow)" }}>{r.status}</span></td>
                      <td><span style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--muted)" }}>{new Date(r.recommended_at).toLocaleTimeString("en-IN")}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {selProd && (
        <div className="detail" style={{ right:0 }}>
          <button className="close-btn" onClick={() => setSelected(null)}>✕</button>
          <div className="d-id">{selProd.product_id}</div>
          <div className="d-name">{selProd.name}</div>
          <div className="d-label">Stock Status</div>
          <div className="d-val" style={{ color: DOS_COLOR(selProd.days_of_stock) }}>{selProd.stock_status.toUpperCase()}</div>
          <div className="d-label">Days of Stock</div>
          <div className="d-val">{selProd.days_of_stock === 999 ? "∞ (no sales)" : `${selProd.days_of_stock} days`}</div>
          <div className="meter" style={{ marginTop:6 }}>
            <div className="meter-fill" style={{ width:`${Math.min((selProd.days_of_stock === 999 ? 200 : selProd.days_of_stock)/120*100,100)}%`, background: DOS_COLOR(selProd.days_of_stock) }} />
          </div>
          <div className="d-label">Stock</div>
          <div className="d-val">{fmtN(selProd.stock_bags)} bags</div>
          <div className="d-label">Sales Velocity</div>
          <div className="d-val">{selProd.sales_last_30d} bags / 30d &nbsp;=&nbsp; {selProd.daily_sales_rate}/day</div>
          <div className="d-label">Last Sale</div>
          <div className="d-val">{selProd.days_since_last_sale}d ago</div>
          {selProd.reorder_qty > 0 && <>
            <div className="d-label">Recommended Reorder</div>
            <div className="d-val" style={{ color:"var(--yellow)" }}>{fmtN(selProd.reorder_qty)} bags</div>
            <div className="d-label">Reorder Value</div>
            <div className="d-val">{fmt(selProd.reorder_value_rs)}</div>
            <div className="d-label">Urgency</div>
            <div className="d-val" style={{ color: URGENCY_COLOR[selProd.urgency] }}>{selProd.urgency}</div>
          </>}
        </div>
      )}
    </>
  );
}

// ─── Supplier Tab ─────────────────────────────────────────────────────────────
function SupplierTab({ feed, running, setRunning, addFeed }) {
  const [data, setData]   = useState(null);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/suppliers`);
      const d   = await res.json();
      setData(d); setError(null);
    } catch (e) { setError("Cannot reach /suppliers endpoint"); }
  }, []);

  useEffect(() => { fetchData(); }, []);

  const runProcure = async () => {
    if (running) return;
    setRunning(true);
    try {
      const res  = await fetch(`${API_BASE}/suppliers/procure`, { method:"POST" });
      const resp = await res.json();
      addFeed("agent", resp.message || `🚚 Procurement dispatched — ${resp.pending_reorders || 0} reorders`);
      setTimeout(fetchData, 4000);
    } catch (e) { setError(e.message); setRunning(false); }
  };

  if (!data) return <div className="loading-msg">{error || "⟳ Loading suppliers..."}</div>;

  const totalPO   = data.purchase_orders?.reduce((a, p) => a + (p.total_payable_rs || 0), 0) || 0;
  const pendingRO = data.pending_reorders?.length || 0;

  return (
    <>
      {error && <div className="err-banner">⚠ {error}</div>}

      <div className="main no-side" style={{ gridTemplateColumns:"1fr", overflowY:"auto" }}>
        <div style={{ gridColumn:"1/-1" }}>
          <div className="stats-bar">
            {[
              { label:"Suppliers",       value: data.supplier_count,                              sub:"across India" },
              { label:"Purchase Orders", value: data.po_count,                                    sub:"raised total" },
              { label:"Total PO Value",  value: totalPO ? `₹${(totalPO/100000).toFixed(1)}L` : "₹0", sub:"incl. 18% GST" },
              { label:"Pending Reorders",value: pendingRO,                                        sub:"awaiting PO" },
              { label:"Supply Risks",    value: data.supply_risks?.length || 0,                   sub:"flagged" },
            ].map(s => (
              <div className="stat" key={s.label}>
                <div className="stat-label">{s.label}</div>
                <div className="stat-value">{s.value}</div>
                <div className="stat-sub">{s.sub}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="table-panel" style={{ borderRight:"none", height:"auto", overflow:"visible" }}>
          <div className="tbl-header">
            <span className="tbl-title">Supplier Management</span>
            <div className="btn-row">
              <button className="run-btn sm" onClick={fetchData} disabled={running}>↻ Refresh</button>
              <button className={`run-btn purple ${running ? "running" : ""}`} onClick={runProcure} disabled={running}>
                {running ? "⟳ Procuring..." : `🚚 Run Procurement${pendingRO > 0 ? ` (${pendingRO} pending)` : ""}`}
              </button>
            </div>
          </div>

          {/* Supplier cards */}
          <div style={{ padding:"16px 20px" }}>
            <div style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--muted)", textTransform:"uppercase", letterSpacing:"0.12em", marginBottom:12 }}>Supplier Catalogue</div>
            <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(280px, 1fr))", gap:10 }}>
              {data.suppliers?.map(s => (
                <div className="supplier-card" key={s.supplier_id}>
                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start" }}>
                    <div>
                      <div style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--accent)" }}>{s.supplier_id}</div>
                      <div style={{ fontSize:13, fontWeight:600, color:"#e2e8f0", marginTop:2 }}>{s.name}</div>
                      <div style={{ fontSize:11, color:"var(--muted)", marginTop:2 }}>{s.location}</div>
                    </div>
                    <div style={{ textAlign:"right" }}>
                      <div className="rel-stars">{"★".repeat(Math.round(s.reliability_score / 2))}</div>
                      <div style={{ fontFamily:"var(--mono)", fontSize:11, color:"var(--yellow)" }}>{s.reliability_score}/10</div>
                    </div>
                  </div>
                  <div style={{ display:"flex", gap:16, marginTop:10, flexWrap:"wrap" }}>
                    <div>
                      <div style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--muted)", textTransform:"uppercase" }}>Lead Time</div>
                      <div style={{ fontFamily:"var(--mono)", fontSize:12, color:"var(--text)" }}>{s.lead_time_days} days</div>
                    </div>
                    <div>
                      <div style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--muted)", textTransform:"uppercase" }}>MOQ</div>
                      <div style={{ fontFamily:"var(--mono)", fontSize:12, color:"var(--text)" }}>{s.moq_bags} bags</div>
                    </div>
                    <div>
                      <div style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--muted)", textTransform:"uppercase" }}>Payment</div>
                      <div style={{ fontFamily:"var(--mono)", fontSize:12, color:"var(--text)" }}>{s.payment_terms}</div>
                    </div>
                    <div>
                      <div style={{ fontFamily:"var(--mono)", fontSize:9, color:"var(--muted)", textTransform:"uppercase" }}>Products</div>
                      <div style={{ fontFamily:"var(--mono)", fontSize:12, color:"var(--text)" }}>{s.product_count} SKUs</div>
                    </div>
                  </div>
                  <div style={{ marginTop:8, display:"flex", flexWrap:"wrap", gap:4 }}>
                    {s.products_supplied.map(pid => (
                      <span key={pid} style={{ fontFamily:"var(--mono)", fontSize:9, padding:"1px 5px",
                        background:"rgba(0,229,255,0.08)", color:"var(--accent)", borderRadius:2 }}>{pid}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* Supply risks */}
            {data.supply_risks?.length > 0 && (
              <div style={{ marginTop:24 }}>
                <div style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--muted)", textTransform:"uppercase", letterSpacing:"0.12em", marginBottom:10 }}>Supply Risks</div>
                <div style={{ display:"flex", flexWrap:"wrap", gap:8 }}>
                  {data.supply_risks.map((r, i) => (
                    <div key={i} style={{ background:"var(--panel)", border:`1px solid ${RISK_COLOR[r.severity] || "var(--border)"}22`,
                      borderRadius:3, padding:"8px 12px", minWidth:200 }}>
                      <div style={{ fontFamily:"var(--mono)", fontSize:9, color: RISK_COLOR[r.severity], textTransform:"uppercase" }}>
                        {r.severity} · {r.risk_type}
                      </div>
                      <div style={{ fontSize:12, fontWeight:500, color:"#e2e8f0", marginTop:3 }}>{r.product_id}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Purchase orders */}
            {data.purchase_orders?.length > 0 && (
              <div style={{ marginTop:24 }}>
                <div style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--muted)", textTransform:"uppercase", letterSpacing:"0.12em", marginBottom:10 }}>Purchase Orders</div>
                <table>
                  <thead><tr>
                    <th>PO #</th><th>Product</th><th>Supplier</th><th>Qty</th>
                    <th>Ex-GST</th><th>GST 18%</th><th>Total Payable</th>
                    <th>Payment Terms</th><th>Expected Delivery</th><th>Status</th>
                  </tr></thead>
                  <tbody>
                    {data.purchase_orders.map((po, i) => (
                      <tr key={i}>
                        <td><span className="mono" style={{ color:"var(--accent)", fontSize:11 }}>{po.po_number}</span></td>
                        <td><span className="pid">{po.product_id}</span><br /><span style={{ fontSize:11 }}>{po.product_name}</span></td>
                        <td><span style={{ fontSize:11 }}>{po.supplier_name}</span></td>
                        <td><span className="mono">{fmtN(po.quantity_bags)} bags</span></td>
                        <td><span className="mono" style={{ fontSize:11 }}>{fmt(po.order_value_rs)}</span></td>
                        <td><span className="mono" style={{ fontSize:11, color:"var(--yellow)" }}>{fmt(po.gst_18pct)}</span></td>
                        <td><span className="mono" style={{ color:"var(--green)" }}>{fmt(po.total_payable_rs)}</span></td>
                        <td><span className="mono" style={{ fontSize:11 }}>{po.payment_terms}</span></td>
                        <td><span className="mono" style={{ fontSize:11 }}>{po.expected_delivery}</span></td>
                        <td><span style={{ fontFamily:"var(--mono)", fontSize:10, padding:"2px 6px", borderRadius:2,
                          background:"rgba(74,222,128,0.1)", color:"var(--green)" }}>{po.status}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

// ─── Root App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab]             = useState("pricing");
  const [feed, setFeed]           = useState([]);
  const [history, setHistory]     = useState([]);
  const [running, setRunning]     = useState(false);
  const [sseStatus, setSseStatus] = useState("connecting");
  const [config, setConfig]       = useState({ min_margin_pct:20, slow_moving_days:30, mrp_headroom_pct:80 });
  const esRef = useRef(null);

  const addFeed = useCallback((tag, msg) => {
    const time = new Date().toLocaleTimeString("en-IN", { hour12:false });
    setFeed(f => [{ id:uid(), time, tag, msg }, ...f].slice(0, 120));
  }, []);

  const fetchHistory = useCallback(async () => {
    try { const r = await fetch(`${API_BASE}/history`); const d = await r.json(); setHistory(d.history); } catch (_) {}
  }, []);

  useEffect(() => { fetchHistory(); }, []);

  useEffect(() => {
    const connect = () => {
      setSseStatus("connecting");
      const es = new EventSource(`${API_BASE}/stream`);
      esRef.current = es;
      es.onopen = () => setSseStatus("connected");
      es.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data);
          const { type, data } = ev;
          if (type === "ping" || type === "connected") return;
          addFeed(type, data?.message || "");
          if (type === "update") fetchHistory();
          if (type === "agent" && data?.message?.includes("complete")) {
            setRunning(false); fetchHistory();
          }
          if (type === "error") setRunning(false);
        } catch (_) {}
      };
      es.onerror = () => { setSseStatus("disconnected"); es.close(); setTimeout(connect, 4000); };
    };
    connect();
    return () => esRef.current?.close();
  }, [addFeed, fetchHistory]);

  return (
    <>
      <style>{css}</style>

      <header className="header">
        <div style={{ display:"flex", alignItems:"center", gap:12 }}>
          <div className="logo">RF</div>
          <div>
            <div className="h-title">Richfield Fertilisers — Multi-Agent System</div>
            <div className="h-sub">Maharashtra · 25 kg Bag Grades · Pricing · Inventory · Supplier</div>
          </div>
        </div>
        <div className="h-right">
          <div className="h-status">
            <div className={`dot ${sseStatus}`} />
            {sseStatus === "connected" ? "LIVE" : sseStatus === "connecting" ? "CONNECTING" : "RECONNECTING"}
          </div>
          <div className="h-status">groq / llama-3.3-70b</div>
        </div>
      </header>

      <div className="tab-bar">
        {[
          { id:"pricing",   label:"💰 Pricing Agent" },
          { id:"inventory", label:"📦 Inventory Agent" },
          { id:"supplier",  label:"🚚 Supplier Agent" },
        ].map(t => (
          <div key={t.id} className={`tab ${tab === t.id ? "active" : ""}`} onClick={() => setTab(t.id)}>
            {t.label}
          </div>
        ))}
        <div style={{ marginLeft:"auto", display:"flex", alignItems:"center", gap:8, padding:"0 4px" }}>
          {feed.slice(0, 1).map(f => (
            <span key={f.id} style={{ fontFamily:"var(--mono)", fontSize:10, color:"var(--muted)" }}>
              <span className={`tag tag-${f.tag}`}>{f.tag.toUpperCase()}</span> {f.msg.slice(0, 60)}
            </span>
          ))}
        </div>
      </div>

      {tab === "pricing"   && <PricingTab  feed={feed} history={history} running={running} setRunning={setRunning} addFeed={addFeed} config={config} setConfig={setConfig} />}
      {tab === "inventory" && <InventoryTab feed={feed} running={running} setRunning={setRunning} addFeed={addFeed} />}
      {tab === "supplier"  && <SupplierTab  feed={feed} running={running} setRunning={setRunning} addFeed={addFeed} />}
    </>
  );
}
