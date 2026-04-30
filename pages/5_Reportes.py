"""Reportes - analitica completa con export Excel profesional."""
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import json
import io
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import list_trades, list_accounts, list_firms, get_conn
from instruments_config import DIRECTION_LABELS

if not st.session_state.get("authed"):
    st.warning("Inicia sesion en la pagina principal.")
    st.stop()

st.title("Reportes")
st.caption("Analitica de tus cuentas y operaciones. Filtra por periodo, firm, cuenta o activo.")

# ============================================================
# Filtros
# ============================================================
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
fid = None
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
        SELECT t.*, a.account_alias, a.phase, a.firm_id, a.notes AS account_notes,
               pf.name AS firm_name
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


# ============================================================
# Helpers
# ============================================================
def calc_r(pnl, risk):
    if not risk or risk <= 0 or pnl is None:
        return None
    return pnl / risk


def calc_planned_rr(entry, sl, tp):
    if not (entry and sl and tp):
        return None
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    return reward / risk if risk else None


# ============================================================
# Resumen general
# ============================================================
st.markdown("### Resumen general")

total_trades = len(trades)
closed = [t for t in trades if t.get("pnl") is not None]
winning = [t for t in closed if (t.get("pnl") or 0) > 0]
losing = [t for t in closed if (t.get("pnl") or 0) < 0]
breakeven = [t for t in closed if (t.get("pnl") or 0) == 0]
total_pnl = sum((t.get("pnl") or 0) for t in closed)
total_spread = sum((t.get("spread_pips") or 0) for t in trades if t.get("spread_pips"))
violations_count = sum(1 for t in trades if json.loads(t.get("violations") or "[]"))

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total trades", total_trades)
m2.metric("P&L total USD", f"{total_pnl:,.2f}")
m3.metric("Spread total USD", f"{total_spread:,.2f}")
m4.metric("Trades con violaciones", violations_count)

m5, m6, m7, m8 = st.columns(4)
win_rate = (len(winning) / len(closed) * 100) if closed else 0
avg_win = (sum(t["pnl"] for t in winning) / len(winning)) if winning else 0
avg_loss = (sum(t["pnl"] for t in losing) / len(losing)) if losing else 0
profit_factor = (sum(t["pnl"] for t in winning) / abs(sum(t["pnl"] for t in losing))) if losing else 0
m5.metric("Win rate", f"{win_rate:.1f}%")
m6.metric("Promedio gana USD", f"{avg_win:,.2f}")
m7.metric("Promedio pierde USD", f"{avg_loss:,.2f}")
m8.metric("Profit factor", f"{profit_factor:.2f}" if profit_factor else "-")

# R-multiple and RR averages
r_mults = [calc_r(t.get("pnl"), t.get("risk_usd")) for t in trades]
r_mults = [r for r in r_mults if r is not None]
avg_r = sum(r_mults) / len(r_mults) if r_mults else None
planned_rrs = [calc_planned_rr(t.get("entry_price"), t.get("stop_loss"), t.get("take_profit")) for t in trades]
planned_rrs = [r for r in planned_rrs if r is not None]
avg_rr = sum(planned_rrs) / len(planned_rrs) if planned_rrs else None

m9, m10, m11, m12 = st.columns(4)
m9.metric("R-multiplo promedio", f"{avg_r:+.2f}R" if avg_r is not None else "-")
m10.metric("R:R planeado promedio", f"1:{avg_rr:.2f}" if avg_rr is not None else "-")
m11.metric("Trades ganadores", len(winning))
m12.metric("Trades perdedores", len(losing))

st.divider()

# ============================================================
# P&L por cuenta
# ============================================================
st.markdown("### Por cuenta")

by_acct = {}
for t in trades:
    key = (t["firm_name"], t["account_alias"])
    by_acct.setdefault(key, {"trades": 0, "pnl": 0.0, "spread": 0.0, "viol": 0,
                             "wins": 0, "losses": 0, "rs": []})
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
    r = calc_r(t.get("pnl"), t.get("risk_usd"))
    if r is not None:
        by_acct[key]["rs"].append(r)

acct_rows = []
for (firm, alias), s in sorted(by_acct.items(), key=lambda x: -x[1]["pnl"]):
    wr = (s["wins"] / (s["wins"] + s["losses"]) * 100) if (s["wins"] + s["losses"]) else 0
    avg_r_acct = sum(s["rs"]) / len(s["rs"]) if s["rs"] else None
    acct_rows.append({
        "Firm": firm,
        "Cuenta": alias,
        "Trades": s["trades"],
        "P&L USD": round(s["pnl"], 2),
        "Spread total USD": round(s["spread"], 2),
        "Wins": s["wins"],
        "Losses": s["losses"],
        "Win rate": f"{wr:.1f}%",
        "R-mult promedio": f"{avg_r_acct:+.2f}" if avg_r_acct is not None else "-",
        "Violaciones": s["viol"],
    })
df_acct = pd.DataFrame(acct_rows)
st.dataframe(df_acct, use_container_width=True, hide_index=True)

st.divider()

# ============================================================
# Por activo
# ============================================================
st.markdown("### Por activo")

by_inst = {}
for t in trades:
    inst = t["instrument"]
    by_inst.setdefault(inst, {"trades": 0, "pnl": 0.0, "spread": 0.0, "lots": 0.0,
                              "wins": 0, "losses": 0})
    by_inst[inst]["trades"] += 1
    if t.get("pnl") is not None:
        by_inst[inst]["pnl"] += t["pnl"]
        if t["pnl"] > 0:
            by_inst[inst]["wins"] += 1
        elif t["pnl"] < 0:
            by_inst[inst]["losses"] += 1
    if t.get("spread_pips"):
        by_inst[inst]["spread"] += t["spread_pips"]
    by_inst[inst]["lots"] += t.get("lot_size") or 0

inst_rows = []
total_lots = sum(s["lots"] for s in by_inst.values()) or 1
for inst, s in sorted(by_inst.items(), key=lambda x: -x[1]["trades"]):
    pct_trades = s["trades"] / total_trades * 100
    pct_lots = s["lots"] / total_lots * 100
    wr = (s["wins"] / (s["wins"] + s["losses"]) * 100) if (s["wins"] + s["losses"]) else 0
    inst_rows.append({
        "Activo": inst,
        "Trades": s["trades"],
        "% del total trades": round(pct_trades, 1),
        "Lotaje total": round(s["lots"], 2),
        "% del lotaje total": round(pct_lots, 1),
        "P&L USD": round(s["pnl"], 2),
        "Spread total USD": round(s["spread"], 2),
        "Win rate %": round(wr, 1),
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

# ============================================================
# Por firm
# ============================================================
st.markdown("### Por firm")

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
    "Firm": fname,
    "Trades": s["trades"],
    "% del total": round(s['trades']/total_trades*100, 1),
    "P&L USD": round(s["pnl"], 2),
    "Violaciones": s["viol"],
} for fname, s in sorted(by_firm.items(), key=lambda x: -x[1]["trades"])]
df_firm = pd.DataFrame(firm_rows)
st.dataframe(df_firm, use_container_width=True, hide_index=True)

st.divider()

# ============================================================
# Violaciones
# ============================================================
st.markdown("### Violaciones detectadas en el periodo")
viol_trades = [t for t in trades if json.loads(t.get("violations") or "[]")]
if not viol_trades:
    st.success("Sin violaciones en el periodo.")
    df_viol = pd.DataFrame()
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
            "Riesgo USD": t.get("risk_usd"),
            "P&L USD": t.get("pnl"),
            "Violaciones": " | ".join(viol),
        })
    df_viol = pd.DataFrame(rows)
    st.dataframe(df_viol, use_container_width=True, hide_index=True)

st.divider()

# ============================================================
# Notas
# ============================================================
st.markdown("### Trades con notas en el periodo")
notes_trades = [t for t in trades if t.get("notes")]
if not notes_trades:
    st.info("Sin notas en el periodo.")
    df_notes = pd.DataFrame()
else:
    rows = []
    for t in notes_trades:
        rows.append({
            "Fecha": t["entry_time"],
            "Firm": t["firm_name"],
            "Cuenta": t["account_alias"],
            "Activo": t["instrument"],
            "Direccion": DIRECTION_LABELS.get(t["direction"], t["direction"]),
            "Lotaje": t["lot_size"],
            "P&L USD": t.get("pnl"),
            "Nota": t["notes"],
        })
    df_notes = pd.DataFrame(rows)
    st.dataframe(df_notes, use_container_width=True, hide_index=True)

st.divider()

# ============================================================
# EXPORTAR EXCEL PROFESIONAL
# ============================================================
st.markdown("### Exportar")
st.caption("Genera un archivo Excel completo con todas las hojas, formato profesional y graficos")


def build_full_trades_df(trades_list):
    """Build the detailed trades dataframe with all calculations."""
    rows = []
    for t in trades_list:
        viol = json.loads(t.get("violations") or "[]")
        r_mult = calc_r(t.get("pnl"), t.get("risk_usd"))
        rr_planeado = calc_planned_rr(t.get("entry_price"), t.get("stop_loss"), t.get("take_profit"))
        rows.append({
            "ID": t["id"],
            "Fecha entrada": t["entry_time"],
            "Fecha salida": t.get("exit_time"),
            "Firm": t["firm_name"],
            "Cuenta": t["account_alias"],
            "Fase": t["phase"],
            "Activo": t["instrument"],
            "Direccion": DIRECTION_LABELS.get(t["direction"], t["direction"]),
            "Lotaje": t["lot_size"],
            "Precio entrada": t.get("entry_price"),
            "Stop loss": t.get("stop_loss"),
            "Take profit": t.get("take_profit"),
            "Riesgo USD": t.get("risk_usd"),
            "P&L USD": t.get("pnl"),
            "R-multiplo": round(r_mult, 2) if r_mult is not None else None,
            "R:R planeado": round(rr_planeado, 2) if rr_planeado is not None else None,
            "Spread USD": t.get("spread_pips"),
            "Violaciones": " | ".join(viol),
            "Nota": t.get("notes") or "",
        })
    return pd.DataFrame(rows)


def make_excel_report(trades_list, df_acct, df_inst, df_firm, df_viol, df_notes,
                      start_date, end_date):
    """Build a professional multi-sheet Excel file in memory."""
    output = io.BytesIO()

    # Use xlsxwriter for richer formatting
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        workbook = writer.book

        # ---------- formats ----------
        title_fmt = workbook.add_format({
            "bold": True, "font_size": 16, "font_color": "#0a0e1a",
            "bg_color": "#22c55e", "align": "center", "valign": "vcenter"
        })
        header_fmt = workbook.add_format({
            "bold": True, "font_color": "white", "bg_color": "#1f2937",
            "border": 1, "align": "center"
        })
        cell_fmt = workbook.add_format({"border": 1})
        money_fmt = workbook.add_format({"num_format": "#,##0.00", "border": 1})
        money_pos = workbook.add_format({"num_format": "#,##0.00", "border": 1,
                                          "font_color": "#22c55e", "bold": True})
        money_neg = workbook.add_format({"num_format": "#,##0.00", "border": 1,
                                          "font_color": "#ef4444", "bold": True})
        viol_fmt = workbook.add_format({"bg_color": "#fee2e2", "border": 1, "bold": True})
        label_fmt = workbook.add_format({"bold": True, "bg_color": "#f1f5f9"})

        # ------------------ HOJA 1: RESUMEN EJECUTIVO ------------------
        ws = workbook.add_worksheet("1. Resumen ejecutivo")
        ws.set_column("A:A", 35)
        ws.set_column("B:B", 22)

        ws.merge_range("A1:B1", "RESUMEN EJECUTIVO", title_fmt)
        ws.set_row(0, 28)

        row = 2
        ws.write(row, 0, "Periodo desde:", label_fmt)
        ws.write(row, 1, str(start_date)); row += 1
        ws.write(row, 0, "Periodo hasta:", label_fmt)
        ws.write(row, 1, str(end_date)); row += 2

        ws.merge_range(row, 0, row, 1, "Resumen operativo", header_fmt); row += 1
        for label, val in [
            ("Total de trades", total_trades),
            ("Trades cerrados", len(closed)),
            ("Trades ganadores", len(winning)),
            ("Trades perdedores", len(losing)),
            ("Trades en empate", len(breakeven)),
            ("Win rate %", round(win_rate, 2)),
            ("Profit factor", round(profit_factor, 2) if profit_factor else 0),
        ]:
            ws.write(row, 0, label, cell_fmt)
            ws.write(row, 1, val, cell_fmt); row += 1

        row += 1
        ws.merge_range(row, 0, row, 1, "Resumen financiero", header_fmt); row += 1
        for label, val, is_money_signed in [
            ("P&L total USD", total_pnl, True),
            ("Promedio gana USD", avg_win, True),
            ("Promedio pierde USD", avg_loss, True),
            ("Spread total USD", total_spread, False),
            ("R-multiplo promedio", avg_r if avg_r else 0, False),
            ("R:R planeado promedio", avg_rr if avg_rr else 0, False),
        ]:
            ws.write(row, 0, label, cell_fmt)
            if is_money_signed:
                fmt = money_pos if val > 0 else (money_neg if val < 0 else money_fmt)
            else:
                fmt = money_fmt
            ws.write(row, 1, val, fmt); row += 1

        row += 1
        ws.merge_range(row, 0, row, 1, "Reglas y violaciones", header_fmt); row += 1
        ws.write(row, 0, "Trades con violaciones", cell_fmt)
        ws.write(row, 1, violations_count, cell_fmt); row += 1
        ws.write(row, 0, "% trades con violacion", cell_fmt)
        ws.write(row, 1, round(violations_count/total_trades*100, 2) if total_trades else 0, cell_fmt)

        # ------------------ HOJA 2: DETALLE DE TRADES ------------------
        df_full = build_full_trades_df(trades_list)
        df_full.to_excel(writer, sheet_name="2. Detalle de trades", index=False)
        ws2 = writer.sheets["2. Detalle de trades"]
        ws2.set_column("A:A", 6)
        ws2.set_column("B:C", 18)
        ws2.set_column("D:E", 18)
        ws2.set_column("F:F", 8)
        ws2.set_column("G:H", 10)
        ws2.set_column("I:I", 8)
        ws2.set_column("J:O", 13)
        ws2.set_column("P:P", 11)
        ws2.set_column("Q:Q", 35)
        ws2.set_column("R:R", 35)
        # Apply header format
        for col_idx, col_name in enumerate(df_full.columns):
            ws2.write(0, col_idx, col_name, header_fmt)
        # Conditional format on P&L column
        if not df_full.empty and "P&L USD" in df_full.columns:
            pnl_col = df_full.columns.get_loc("P&L USD")
            ws2.conditional_format(1, pnl_col, len(df_full), pnl_col, {
                "type": "cell", "criteria": ">", "value": 0,
                "format": workbook.add_format({"font_color": "#22c55e", "bold": True})
            })
            ws2.conditional_format(1, pnl_col, len(df_full), pnl_col, {
                "type": "cell", "criteria": "<", "value": 0,
                "format": workbook.add_format({"font_color": "#ef4444", "bold": True})
            })

        # ------------------ HOJA 3: POR CUENTA ------------------
        df_acct.to_excel(writer, sheet_name="3. Por cuenta", index=False)
        ws3 = writer.sheets["3. Por cuenta"]
        ws3.set_column("A:B", 22)
        ws3.set_column("C:J", 13)
        for col_idx, col_name in enumerate(df_acct.columns):
            ws3.write(0, col_idx, col_name, header_fmt)

        # ------------------ HOJA 4: POR ACTIVO ------------------
        df_inst.to_excel(writer, sheet_name="4. Por activo", index=False)
        ws4 = writer.sheets["4. Por activo"]
        ws4.set_column("A:A", 14)
        ws4.set_column("B:H", 16)
        for col_idx, col_name in enumerate(df_inst.columns):
            ws4.write(0, col_idx, col_name, header_fmt)

        # Add chart for trades by instrument
        if len(df_inst) > 1:
            chart = workbook.add_chart({"type": "column"})
            n = len(df_inst)
            chart.add_series({
                "name": "Trades por activo",
                "categories": ["4. Por activo", 1, 0, n, 0],
                "values":     ["4. Por activo", 1, 1, n, 1],
                "fill":   {"color": "#22c55e"},
            })
            chart.set_title({"name": "Trades por activo"})
            chart.set_x_axis({"name": "Activo"})
            chart.set_y_axis({"name": "Numero de trades"})
            chart.set_size({"width": 600, "height": 320})
            ws4.insert_chart("J2", chart)

        # ------------------ HOJA 5: POR FIRM ------------------
        df_firm.to_excel(writer, sheet_name="5. Por firm", index=False)
        ws5 = writer.sheets["5. Por firm"]
        ws5.set_column("A:A", 22)
        ws5.set_column("B:E", 14)
        for col_idx, col_name in enumerate(df_firm.columns):
            ws5.write(0, col_idx, col_name, header_fmt)

        if len(df_firm) > 1:
            chart2 = workbook.add_chart({"type": "pie"})
            n = len(df_firm)
            chart2.add_series({
                "name": "Trades por firm",
                "categories": ["5. Por firm", 1, 0, n, 0],
                "values":     ["5. Por firm", 1, 1, n, 1],
            })
            chart2.set_title({"name": "Distribucion de trades por firm"})
            chart2.set_size({"width": 500, "height": 320})
            ws5.insert_chart("G2", chart2)

        # ------------------ HOJA 6: VIOLACIONES ------------------
        if not df_viol.empty:
            df_viol.to_excel(writer, sheet_name="6. Violaciones", index=False)
            ws6 = writer.sheets["6. Violaciones"]
            ws6.set_column("A:A", 20)
            ws6.set_column("B:B", 22)
            ws6.set_column("C:C", 18)
            ws6.set_column("D:G", 13)
            ws6.set_column("H:H", 60)
            for col_idx, col_name in enumerate(df_viol.columns):
                ws6.write(0, col_idx, col_name, header_fmt)
        else:
            ws6 = workbook.add_worksheet("6. Violaciones")
            ws6.write(0, 0, "Sin violaciones en el periodo.", label_fmt)

        # ------------------ HOJA 7: NOTAS ------------------
        if not df_notes.empty:
            df_notes.to_excel(writer, sheet_name="7. Notas", index=False)
            ws7 = writer.sheets["7. Notas"]
            ws7.set_column("A:A", 20)
            ws7.set_column("B:C", 22)
            ws7.set_column("D:F", 13)
            ws7.set_column("G:G", 14)
            ws7.set_column("H:H", 60)
            for col_idx, col_name in enumerate(df_notes.columns):
                ws7.write(0, col_idx, col_name, header_fmt)
        else:
            ws7 = workbook.add_worksheet("7. Notas")
            ws7.write(0, 0, "Sin notas en el periodo.", label_fmt)

        # ------------------ HOJA 8: EQUITY CURVE ------------------
        # Build daily P&L series
        ws8 = workbook.add_worksheet("8. Equity curve")
        ws8.set_column("A:A", 14)
        ws8.set_column("B:C", 16)

        # Aggregate P&L by date
        sorted_trades = sorted(trades_list, key=lambda x: x["entry_time"])
        daily_pnl = {}
        for t in sorted_trades:
            d = t["entry_time"][:10]
            daily_pnl.setdefault(d, 0.0)
            daily_pnl[d] += (t.get("pnl") or 0)

        ws8.write(0, 0, "Fecha", header_fmt)
        ws8.write(0, 1, "P&L del dia USD", header_fmt)
        ws8.write(0, 2, "P&L acumulado USD", header_fmt)

        cumulative = 0.0
        for i, (d, p) in enumerate(sorted(daily_pnl.items()), start=1):
            cumulative += p
            ws8.write(i, 0, d, cell_fmt)
            ws8.write(i, 1, p, money_pos if p > 0 else (money_neg if p < 0 else money_fmt))
            ws8.write(i, 2, cumulative, money_pos if cumulative > 0 else (money_neg if cumulative < 0 else money_fmt))

        # Add equity curve chart
        if len(daily_pnl) > 1:
            chart3 = workbook.add_chart({"type": "line"})
            n = len(daily_pnl)
            chart3.add_series({
                "name": "P&L acumulado",
                "categories": ["8. Equity curve", 1, 0, n, 0],
                "values":     ["8. Equity curve", 1, 2, n, 2],
                "line": {"color": "#22c55e", "width": 2.25},
            })
            chart3.set_title({"name": "Equity Curve - P&L acumulado"})
            chart3.set_x_axis({"name": "Fecha"})
            chart3.set_y_axis({"name": "USD"})
            chart3.set_size({"width": 800, "height": 380})
            ws8.insert_chart("E2", chart3)

    output.seek(0)
    return output.getvalue()


# ----- Botones de descarga -----
ec1, ec2 = st.columns(2)

# CSV simple (siempre disponible, fallback)
trades_simple_df = build_full_trades_df(trades)
csv_data = trades_simple_df.to_csv(index=False).encode("utf-8")
ec1.download_button(
    "Descargar CSV (solo trades)",
    data=csv_data,
    file_name=f"trades_{start}_a_{end}.csv",
    mime="text/csv",
    use_container_width=True,
)

# Excel profesional
try:
    excel_bytes = make_excel_report(trades, df_acct, df_inst, df_firm, df_viol, df_notes,
                                     start, end)
    ec2.download_button(
        "Descargar Excel completo (recomendado)",
        data=excel_bytes,
        file_name=f"reporte_{start}_a_{end}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True,
    )
except Exception as e:
    ec2.error(f"No se pudo generar Excel: {e}")
    st.caption("Si ves este error, revisa que xlsxwriter este en requirements.txt")
