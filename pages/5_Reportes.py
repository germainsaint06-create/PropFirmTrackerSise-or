"""Reportes - analitica con filtros de fecha, firm, cuenta, instrumento."""
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import list_trades, list_accounts, list_firms, get_conn

if not st.session_state.get("authed"):
    st.warning("Inicia sesion en la pagina principal.")
    st.stop()

st.title("Reportes")
st.caption("Analitica de tus cuentas y operaciones. Filtra por periodo, firm, cuenta o activo.")

# ---------------- Filters ----------------
st.markdown("### Filtros")

c1, c2 = st.columns(2)
period = c1.selectbox(
    "Periodo",
    [
        "Ultimos 7 dias",
        "Ultimos 14 dias",
        "Ultimos 30 dias",
        "Ultimos 90 dias",
        "Mes actual",
        "Mes anterior",
        "Ano actual",
        "Todo",
        "Personalizado",
    ],
    index=2,
)

today = date.today()
if period == "Ultimos 7 dias":
    start = today - timedelta(days=7); end = today
elif period == "Ultimos 14 dias":
    start = today - timedelta(days=14); end = today
elif period == "Ultimos 30 dias":
    start = today - timedelta(days=30); end = today
elif period == "Ultimos 90 dias":
    start = today - timedelta(days=90); end = today
elif period == "Mes actual":
    start = today.replace(day=1); end = today
elif period == "Mes anterior":
    first_this = today.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    start = last_prev.replace(day=1); end = last_prev
elif period == "Ano actual":
    start = today.replace(month=1, day=1); end = today
elif period == "Todo":
    start = date(2000, 1, 1); end = today
else:  # Personalizado
    cc1, cc2 = c2.columns(2)
    start = cc1.date_input("Desde", value=today - timedelta(days=30))
    end = cc2.date_input("Hasta", value=today)

if period != "Personalizado":
    c2.markdown(f"**Desde:** {start}  \n**Hasta:** {end}")

# Firm and account filters
c3, c4 = st.columns(2)
firms = list_firms()
firm_names = ["(Todas)"] + [f["name"] for f in firms]
selected_firm = c3.selectbox("Firm", firm_names)

all_accounts = list_accounts()
if selected_firm != "(Todas)":
    fid = next(f["id"] for f in firms if f["name"] == selected_firm)
    filtered_accts = [a for a in all_accounts if a["firm_id"] == fid]
else:
    filtered_accts = all_accounts

acct_options = ["(Todas)"] + [
    f"#{a['id']} - {a['firm_name']} / {a['account_alias']}" for a in filtered_accts
]
selected_acct_label = c4.selectbox("Cuenta", acct_options)

acct_id_filter = None
if selected_acct_label != "(Todas)":
    acct_id_filter = int(selected_acct_label.split(" - ")[0].replace("#", ""))

# Fetch trades in range
since_str = datetime.combine(start, datetime.min.time()).isoformat()
until_str = datetime.combine(end, datetime.max.time()).isoformat()

with get_conn() as conn:
    sql = """
        SELECT t.*, a.account_alias, a.phase, a.firm_id, pf.name AS firm_name
        FROM trades t
        JOIN accounts a ON a.id = t.account_id
        JOIN prop_firms pf ON pf.id = a.firm_id
        WHERE t.entry_time >= ? AND t.entry_time <= ?
    """
    params = [since_str, until_str]
    if acct_id_filter is not None:
        sql += " AND t.account_id = ?"
        params.append(acct_id_filter)
    elif selected_firm != "(Todas)":
        sql += " AND a.firm_id = ?"
        params.append(fid)
    sql += " ORDER BY t.entry_time DESC"
    trades = [dict(r) for r in conn.execute(sql, params)]

st.divider()

if not trades:
    st.warning(f"No hay trades en el periodo {start} a {end} con esos filtros.")
    st.stop()

# ---------------- Resumen general ----------------
st.markdown("### Resumen general")

total_trades = len(trades)
closed_trades = [t for t in trades if t.get("pnl") is not None]
winning = [t for t in closed_trades if (t.get("pnl") or 0) > 0]
losing = [t for t in closed_trades if (t.get("pnl") or 0) < 0]
breakeven = [t for t in closed_trades if (t.get("pnl") or 0) == 0]
total_pnl = sum((t.get("pnl") or 0) for t in closed_trades)
total_spread = sum((t.get("spread_pips") or 0) for t in trades if t.get("spread_pips"))
violations_count = sum(1 for t in trades if json.loads(t.get("violations") or "[]"))

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total trades", total_trades)
m2.metric("P&L total USD", f"{total_pnl:,.2f}")
m3.metric("Spread total USD", f"{total_spread:,.2f}")
m4.metric("Trades con violaciones", violations_count)

m5, m6, m7, m8 = st.columns(4)
win_rate = (len(winning) / len(closed_trades) * 100) if closed_trades else 0
avg_win = (sum(t["pnl"] for t in winning) / len(winning)) if winning else 0
avg_loss = (sum(t["pnl"] for t in losing) / len(losing)) if losing else 0
profit_factor = (sum(t["pnl"] for t in winning) / abs(sum(t["pnl"] for t in losing))) if losing else 0
m5.metric("Win rate", f"{win_rate:.1f}%")
m6.metric("Promedio gana USD", f"{avg_win:,.2f}")
m7.metric("Promedio pierde USD", f"{avg_loss:,.2f}")
m8.metric("Profit factor", f"{profit_factor:.2f}" if profit_factor else "-")

st.divider()

# ---------------- P&L por cuenta ----------------
st.markdown("### P&L por cuenta")

by_acct = {}
for t in trades:
    key = (t["firm_name"], t["account_alias"])
    by_acct.setdefault(key, {"trades": 0, "pnl": 0.0, "spread": 0.0, "viol": 0,
                             "wins": 0, "losses": 0})
    by_acct[key]["trades"] += 1
    if t.get("pnl") is not None:
        by_acct[key]["pnl"] += t["pnl"]
        if t["pnl"] > 0:
            by_acct[key]["wins"] += 1
        elif t["pnl"] < 0:
            by_acct[key]["losses"] += 1
    if t.get("spread_pips"):
        by_acct[key]["spread"] += t["spread_pips"]
    if json.loads(t.get("violations") or "[]"):
        by_acct[key]["viol"] += 1

acct_rows = []
for (firm, alias), s in sorted(by_acct.items(), key=lambda x: -x[1]["pnl"]):
    wr = (s["wins"] / (s["wins"] + s["losses"]) * 100) if (s["wins"] + s["losses"]) else 0
    acct_rows.append({
        "Firm": firm,
        "Cuenta": alias,
        "Trades": s["trades"],
        "P&L USD": round(s["pnl"], 2),
        "Spread total USD": round(s["spread"], 2),
        "Wins": s["wins"],
        "Losses": s["losses"],
        "Win rate": f"{wr:.1f}%",
        "Violaciones": s["viol"],
    })
df_acct = pd.DataFrame(acct_rows)
st.dataframe(df_acct, use_container_width=True, hide_index=True)

st.divider()

# ---------------- Distribucion por activo ----------------
st.markdown("### Distribucion por activo")

by_inst = {}
for t in trades:
    inst = t["instrument"]
    by_inst.setdefault(inst, {"trades": 0, "pnl": 0.0, "spread": 0.0, "lots": 0.0})
    by_inst[inst]["trades"] += 1
    if t.get("pnl") is not None:
        by_inst[inst]["pnl"] += t["pnl"]
    if t.get("spread_pips"):
        by_inst[inst]["spread"] += t["spread_pips"]
    by_inst[inst]["lots"] += t.get("lot_size") or 0

inst_rows = []
total_lots = sum(s["lots"] for s in by_inst.values()) or 1
for inst, s in sorted(by_inst.items(), key=lambda x: -x[1]["trades"]):
    pct_trades = s["trades"] / total_trades * 100
    pct_lots = s["lots"] / total_lots * 100
    inst_rows.append({
        "Activo": inst,
        "Trades": s["trades"],
        "% del total trades": f"{pct_trades:.1f}%",
        "Lotaje total": round(s["lots"], 2),
        "% del lotaje total": f"{pct_lots:.1f}%",
        "P&L USD": round(s["pnl"], 2),
        "Spread total USD": round(s["spread"], 2),
    })
df_inst = pd.DataFrame(inst_rows)
st.dataframe(df_inst, use_container_width=True, hide_index=True)

# Bar chart of trades per instrument
if len(by_inst) > 1:
    chart_df = pd.DataFrame({
        "Activo": list(by_inst.keys()),
        "Trades": [s["trades"] for s in by_inst.values()],
    }).set_index("Activo")
    st.bar_chart(chart_df, height=250)

st.divider()

# ---------------- Distribucion por firm ----------------
st.markdown("### Distribucion por firm")

by_firm = {}
for t in trades:
    f = t["firm_name"]
    by_firm.setdefault(f, {"trades": 0, "pnl": 0.0, "viol": 0})
    by_firm[f]["trades"] += 1
    if t.get("pnl") is not None:
        by_firm[f]["pnl"] += t["pnl"]
    if json.loads(t.get("violations") or "[]"):
        by_firm[f]["viol"] += 1

firm_rows = [{
    "Firm": f,
    "Trades": s["trades"],
    "% del total": f"{s['trades']/total_trades*100:.1f}%",
    "P&L USD": round(s["pnl"], 2),
    "Violaciones": s["viol"],
} for f, s in sorted(by_firm.items(), key=lambda x: -x[1]["trades"])]
st.dataframe(pd.DataFrame(firm_rows), use_container_width=True, hide_index=True)

st.divider()

# ---------------- Violaciones ----------------
st.markdown("### Violaciones detectadas en el periodo")
viol_trades = [t for t in trades if json.loads(t.get("violations") or "[]")]
if not viol_trades:
    st.success("Sin violaciones en el periodo.")
else:
    rows = []
    for t in viol_trades:
        viol = json.loads(t.get("violations") or "[]")
        rows.append({
            "Fecha": t["entry_time"],
            "Firm": t["firm_name"],
            "Cuenta": t["account_alias"],
            "Activo": t["instrument"],
            "Lotaje": t["lot_size"],
            "Violaciones": " | ".join(viol),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.divider()

# ---------------- Descargar reporte completo (CSV) ----------------
st.markdown("### Exportar")

trades_df_export = pd.DataFrame([{
    "Fecha entrada": t["entry_time"],
    "Fecha salida": t.get("exit_time"),
    "Firm": t["firm_name"],
    "Cuenta": t["account_alias"],
    "Fase": t["phase"],
    "Activo": t["instrument"],
    "Direccion": t["direction"],
    "Lotaje": t["lot_size"],
    "Entrada": t.get("entry_price"),
    "Stop loss": t.get("stop_loss"),
    "Take profit": t.get("take_profit"),
    "Riesgo USD": t.get("risk_usd"),
    "P&L USD": t.get("pnl"),
    "Spread USD": t.get("spread_pips"),
    "Violaciones": " | ".join(json.loads(t.get("violations") or "[]")),
    "Notas": t.get("notes") or "",
} for t in trades])

csv_data = trades_df_export.to_csv(index=False).encode("utf-8")
st.download_button(
    "Descargar trades del periodo (CSV)",
    data=csv_data,
    file_name=f"trades_{start}_a_{end}.csv",
    mime="text/csv",
)
