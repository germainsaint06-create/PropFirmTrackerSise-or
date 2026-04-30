"""Dashboard - vista detallada de cuentas y alertas con notas visibles."""
import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import list_accounts, list_firms, list_trades
from rules_engine import inactivity_status, LEVEL_COLORS, LEVEL_LABELS
from instruments_config import DIRECTION_LABELS

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

# ---------------- NOTAS ACTIVAS ----------------
# Show accounts with notes in a prominent section so they don't get missed
accts_with_notes = [r for r in rows if r.get("notes")]
if accts_with_notes:
    with st.expander(f"Notas en cuentas activas ({len(accts_with_notes)})", expanded=True):
        for r in accts_with_notes:
            st.markdown(
                f"**{r['firm_name']} / {r['account_alias']}** ({r['phase']})"
            )
            st.caption(f"Nota: {r['notes']}")
            st.divider()

# ---------------- Detailed table ----------------
st.subheader("Cuentas")

display_rows = []
for r in rows:
    note = r.get("notes") or ""
    note_preview = (note[:40] + "...") if len(note) > 40 else note
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
        "Nota": note_preview,
    })

df = pd.DataFrame(display_rows)


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

# ---------------- Recent trades ----------------
st.subheader("Ultimos 20 trades registrados")
recent = list_trades(limit=20)
if not recent:
    st.info("Aun no hay trades registrados.")
else:
    import json

    # Show recent trades with notes prominently
    trades_with_notes = [t for t in recent if t.get("notes")]
    if trades_with_notes:
        with st.expander(f"Notas en trades recientes ({len(trades_with_notes)})", expanded=False):
            for t in trades_with_notes:
                viol = json.loads(t.get("violations") or "[]")
                viol_marker = " [VIOLACION]" if viol else ""
                st.markdown(
                    f"**#{t['id']}** {t['firm_name']} / {t['account_alias']} - "
                    f"{t['instrument']} {DIRECTION_LABELS.get(t['direction'], t['direction'])} "
                    f"({t['entry_time'][:16]}){viol_marker}"
                )
                st.caption(f"Nota: {t['notes']}")
                st.divider()

    trade_rows = []
    for t in recent:
        viol = json.loads(t.get("violations") or "[]")
        note = t.get("notes") or ""
        note_preview = (note[:30] + "...") if len(note) > 30 else note
        trade_rows.append({
            "Cuenta": f"{t['firm_name']} / {t['account_alias']}",
            "Activo": t["instrument"],
            "Direccion": DIRECTION_LABELS.get(t["direction"], t["direction"]),
            "Lotaje": t["lot_size"],
            "Riesgo USD": t.get("risk_usd"),
            "P&L": t.get("pnl"),
            "Spread USD": t.get("spread_pips"),
            "Entrada": t["entry_time"],
            "Nota": note_preview,
            "Violaciones": " | ".join(viol) if viol else "",
        })
    tdf = pd.DataFrame(trade_rows)


    def highlight_viol(val):
        return "background-color: #ef4444; color: #0a0e1a; font-weight: 600;" if val else ""


    def color_pnl(val):
        try:
            v = float(val)
            if v > 0:
                return "color: #22c55e; font-weight: 600;"
            elif v < 0:
                return "color: #ef4444; font-weight: 600;"
        except (TypeError, ValueError):
            pass
        return ""


    st.dataframe(
        tdf.style
           .map(highlight_viol, subset=["Violaciones"])
           .map(color_pnl, subset=["P&L"]),
        use_container_width=True,
        hide_index=True,
    )
