"""Dashboard - vista detallada de cuentas y alertas."""
import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import list_accounts, list_firms, list_trades
from rules_engine import inactivity_status, LEVEL_COLORS, LEVEL_LABELS

if not st.session_state.get("authed"):
    st.warning("Inicia sesion en la pagina principal.")
    st.stop()

st.title("Dashboard")
st.caption("Estado de todas las cuentas activas")

# Filters
firms = list_firms()
firm_names = ["(Todas)"] + [f["name"] for f in firms]

c1, c2, c3 = st.columns([2, 2, 2])
selected_firm = c1.selectbox("Prop firm", firm_names)
selected_phase = c2.selectbox("Fase", ["(Todas)", "phase1", "phase2", "funded"])
selected_alert = c3.selectbox(
    "Nivel de alerta",
    ["(Todas)", "Solo en breach", "Roja o peor", "Amarilla o peor", "Solo OK"]
)

firm_filter = None
if selected_firm != "(Todas)":
    firm_filter = next(f["id"] for f in firms if f["name"] == selected_firm)

accounts = list_accounts(status="active", firm_id=firm_filter)

# Apply phase filter
if selected_phase != "(Todas)":
    accounts = [a for a in accounts if a["phase"] == selected_phase]

# Compute statuses and apply alert filter
rows = []
for a in accounts:
    s = inactivity_status(a)
    rows.append({**a, **{f"_{k}": v for k, v in s.items()}})

if selected_alert == "Solo en breach":
    rows = [r for r in rows if r["_level"] == "breach"]
elif selected_alert == "Roja o peor":
    rows = [r for r in rows if r["_level"] in ("red", "breach")]
elif selected_alert == "Amarilla o peor":
    rows = [r for r in rows if r["_level"] in ("yellow", "red", "breach")]
elif selected_alert == "Solo OK":
    rows = [r for r in rows if r["_level"] == "green"]

# Sort by pct desc (most urgent first)
rows.sort(key=lambda r: -r["_pct"])

st.markdown(f"**{len(rows)} cuentas** coinciden con los filtros")

if not rows:
    st.info("No hay cuentas para mostrar con los filtros seleccionados.")
    st.stop()

# Summary metrics for filtered view
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("OK", sum(1 for r in rows if r["_level"] == "green"))
m2.metric("Atencion", sum(1 for r in rows if r["_level"] == "yellow"))
m3.metric("Alerta", sum(1 for r in rows if r["_level"] == "red"))
m4.metric("Breach", sum(1 for r in rows if r["_level"] == "breach"))
m5.metric("Sin trades aun", sum(1 for r in rows if r["_level"] == "no_trades"))

st.divider()

# Detailed table
st.subheader("Cuentas")

display_rows = []
for r in rows:
    display_rows.append({
        "Estado": LEVEL_LABELS[r["_level"]],
        "Firm": r["firm_name"],
        "Cuenta": r["account_alias"],
        "Fase": r["phase"],
        "Balance inicial": r["initial_balance"],
        "Balance actual": r.get("current_balance"),
        "Trades totales": r.get("trade_count", 0),
        "Dias inactiva": r["_days_inactive"],
        "Limite": r["_limit_days"],
        "% del limite": f"{r['_pct']*100:.0f}%",
    })

df = pd.DataFrame(display_rows)


# Color coding for status column via styler
def color_state(val):
    color_map = {
        "OK": "#22c55e",
        "ATENCION": "#eab308",
        "ALERTA": "#f97316",
        "BREACH": "#ef4444",
        "Sin trades": "#64748b",
    }
    bg = color_map.get(val, "#64748b")
    return f"background-color: {bg}; color: #0a0e1a; font-weight: 600;"


styled = df.style.map(color_state, subset=["Estado"])
st.dataframe(styled, use_container_width=True, hide_index=True)

st.divider()

# Recent trades section
st.subheader("Ultimos 20 trades registrados")
recent = list_trades(limit=20)
if not recent:
    st.info("Aun no hay trades registrados.")
else:
    import json
    trade_rows = []
    for t in recent:
        viol = json.loads(t.get("violations") or "[]")
        trade_rows.append({
            "Cuenta": f"{t['firm_name']} / {t['account_alias']}",
            "Activo": t["instrument"],
            "Direccion": t["direction"],
            "Lotaje": t["lot_size"],
            "Riesgo USD": t.get("risk_usd"),
            "P&L": t.get("pnl"),
            "Spread": t.get("spread_pips"),
            "Entrada": t["entry_time"],
            "Violaciones": " | ".join(viol) if viol else "",
        })
    tdf = pd.DataFrame(trade_rows)


    def highlight_viol(val):
        return "background-color: #ef4444; color: #0a0e1a; font-weight: 600;" if val else ""


    st.dataframe(
        tdf.style.map(highlight_viol, subset=["Violaciones"]),
        use_container_width=True,
        hide_index=True,
    )
