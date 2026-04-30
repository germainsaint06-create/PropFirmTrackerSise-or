"""Trades - registro de operaciones con UX mejorada."""
import streamlit as st
import pandas as pd
from datetime import datetime, date, time
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import (
    list_accounts, list_trades, create_trade, update_trade, delete_trade,
    get_account, update_account
)
from rules_engine import check_trade_against_rules
from instruments_config import (
    INSTRUMENTS, get_decimals, get_step, get_format, get_label,
    DIRECTION_LABELS, DIRECTION_FROM_LABEL
)

if not st.session_state.get("authed"):
    st.warning("Inicia sesion en la pagina principal.")
    st.stop()

st.title("Trades")
st.caption("Registro de operaciones, deteccion de violaciones de reglas y P&L")

active_accounts = list_accounts(status="active")
if not active_accounts:
    st.warning("No hay cuentas activas. Crea una en la pagina **Cuentas** primero.")
    st.stop()

acct_lookup = {f"#{a['id']} - {a['firm_name']} / {a['account_alias']} ({a['phase']})": a
               for a in active_accounts}

tab_new, tab_list = st.tabs(["Registrar trade", "Historial"])


# ---------------- Helper for R-multiple calc ----------------
def calc_r_multiple(pnl, risk_usd):
    """R-multiplo realizado. Si gano 2x el riesgo => 2R."""
    if not risk_usd or risk_usd <= 0 or pnl is None:
        return None
    return round(pnl / risk_usd, 2)


def calc_planned_rr(entry, sl, tp):
    """Risk:Reward planeado = distancia(entrada, TP) / distancia(entrada, SL)."""
    if not (entry and sl and tp):
        return None
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    if risk == 0:
        return None
    return round(reward / risk, 2)


# ---------------- Registrar ----------------
with tab_new:
    st.subheader("Nuevo trade")

    # Account selector OUTSIDE form so we can react to selection
    selected_label = st.selectbox("Cuenta", list(acct_lookup.keys()))
    acct = acct_lookup[selected_label]

    # Activo selector OUTSIDE form so decimals can dynamically adjust
    instrument = st.selectbox(
        "Activo",
        INSTRUMENTS,
        format_func=get_label,
        help="Solo se permiten estos 7 activos. Si necesitas otro, avisa para agregarlo."
    )
    decimals = get_decimals(instrument)
    step = get_step(instrument)
    fmt = get_format(instrument)

    st.caption(f"Formato de precio para {get_label(instrument)}: {decimals} decimales (step {step})")

    with st.form("new_trade", clear_on_submit=True):
        # ------- Direccion + lotaje -------
        c1, c2 = st.columns(2)
        direction_label = c1.radio(
            "Direccion",
            ["Compra", "Venta"],
            horizontal=True
        )
        lot_size = c2.number_input("Lotaje", min_value=0.0, value=0.10, step=0.01, format="%.2f")

        # ------- Fechas/horas -------
        st.markdown("**Tiempos**")
        c3, c4, c5 = st.columns(3)
        entry_date = c3.date_input("Fecha entrada", value=date.today())
        entry_t = c4.time_input("Hora entrada", value=datetime.now().time())
        spread = c5.number_input("Spread USD", min_value=0.0, value=0.0,
                                 step=0.5, format="%.2f",
                                 help="Costo del spread pagado al entrar, en USD")

        # Exit defaults to entry time (same day) - user can override
        c6, c7 = st.columns(2)
        exit_date = c6.date_input(
            "Fecha cierre",
            value=date.today(),
            help="Por default es el mismo dia de entrada. Cambiala solo si el trade cruza dias."
        )
        exit_t = c7.time_input(
            "Hora cierre",
            value=datetime.now().time(),
            help="Por default es la hora actual."
        )

        # ------- Precios -------
        st.markdown("**Precios** (entrada / SL / TP)")
        c8, c9, c10 = st.columns(3)
        entry_price = c8.number_input("Precio entrada", min_value=0.0, value=0.0,
                                       step=step, format=fmt)
        sl_price = c9.number_input("Stop loss", min_value=0.0, value=0.0,
                                    step=step, format=fmt,
                                    help="Si el trade no tiene SL, dejalo en 0.")
        tp_price = c10.number_input("Take profit", min_value=0.0, value=0.0,
                                     step=step, format=fmt,
                                     help="Si el trade no tiene TP, dejalo en 0.")

        # ------- Riesgo y resultado -------
        st.markdown("**Riesgo y resultado**")
        c11, c12 = st.columns(2)
        risk_usd = c11.number_input(
            "Riesgo USD si toca SL",
            min_value=0.0, value=0.0, step=10.0,
            help=("Cuanto pierdes si toca el stop loss. Solo Trading Pit lo valida (max 1500). "
                  "Si tu cuenta no tiene esta regla, lo puedes dejar en 0.")
        )

        c12.markdown("&nbsp;")  # spacing
        result_type = c12.radio(
            "Resultado del trade",
            ["Gano (+)", "Empato (=)", "Perdio (-)"],
            horizontal=True,
            index=0
        )

        pnl_amount = st.number_input(
            "Monto en USD (sin signo)",
            min_value=0.0, value=0.0, step=10.0,
            help="Pon el monto positivo. El sistema le aplicara el signo segun el resultado seleccionado arriba."
        )

        notes = st.text_area("Notas",
                              placeholder="Cualquier detalle especial sobre este trade")

        submitted = st.form_submit_button("Registrar trade", type="primary")
        if submitted:
            # Convert direction to internal format
            direction = DIRECTION_FROM_LABEL[direction_label]

            # Apply sign to PnL based on result_type
            if result_type == "Gano (+)":
                pnl = pnl_amount
            elif result_type == "Perdio (-)":
                pnl = -pnl_amount
            else:  # Empato
                pnl = 0.0

            # Build timestamps
            entry_dt = datetime.combine(entry_date, entry_t)
            exit_dt = datetime.combine(exit_date, exit_t)

            # Run rules engine
            violations = check_trade_against_rules(
                firm_id=acct["firm_id"],
                phase=acct["phase"],
                instrument=instrument,
                lot_size=lot_size,
                risk_usd=risk_usd if risk_usd > 0 else None,
                account_id=acct["id"],
            )

            tid = create_trade(
                account_id=acct["id"],
                instrument=instrument,
                direction=direction,
                lot_size=lot_size,
                entry_time=entry_dt.isoformat(),
                exit_time=exit_dt.isoformat(),
                entry_price=entry_price or None,
                exit_price=None,
                stop_loss=sl_price or None,
                take_profit=tp_price or None,
                risk_usd=risk_usd or None,
                pnl=pnl,
                spread_pips=spread or None,
                notes=notes.strip() or None,
                violations=violations,
            )

            # Update balance
            old_balance = float(acct.get("current_balance") or acct["initial_balance"])
            new_balance = old_balance + pnl
            update_account(acct["id"], current_balance=new_balance)

            # Calculate analytics for feedback
            r_mult = calc_r_multiple(pnl, risk_usd) if risk_usd else None
            planned_rr = calc_planned_rr(entry_price, sl_price, tp_price)

            if violations:
                st.error(f"Trade #{tid} registrado con {len(violations)} VIOLACION(ES):")
                for v in violations:
                    st.write(f"  - {v}")
            else:
                st.success(f"Trade #{tid} registrado. Sin violaciones detectadas.")

            # Balance feedback
            delta_str = f"{pnl:+,.2f}"
            st.info(
                f"**Balance:** {old_balance:,.2f} -> {new_balance:,.2f} ({delta_str} USD)"
            )

            # Show metrics if available
            metric_cols = st.columns(3)
            metric_cols[0].metric("Resultado", f"{pnl:+,.2f} USD")
            if r_mult is not None:
                metric_cols[1].metric("R-multiplo", f"{r_mult:+.2f}R")
            if planned_rr is not None:
                metric_cols[2].metric("R:R planeado", f"1:{planned_rr}")


# ---------------- Historial ----------------
with tab_list:
    st.subheader("Historial")

    c1, c2 = st.columns([2, 1])
    filter_account = c1.selectbox(
        "Filtrar por cuenta",
        ["(Todas)"] + list(acct_lookup.keys()),
        key="hist_filter"
    )
    limit_n = c2.number_input("Mostrar ultimas N", min_value=10, max_value=2000, value=100, step=10)

    aid = None if filter_account == "(Todas)" else acct_lookup[filter_account]["id"]
    trades = list_trades(account_id=aid, limit=limit_n)

    if not trades:
        st.info("No hay trades para mostrar.")
    else:
        # Show trades with notes prominently first
        trades_with_notes = [t for t in trades if t.get("notes")]
        if trades_with_notes:
            with st.expander(f"Trades con notas ({len(trades_with_notes)})", expanded=True):
                for t in trades_with_notes[:10]:  # show top 10 most recent
                    viol = json.loads(t.get("violations") or "[]")
                    viol_marker = " [VIOLACION]" if viol else ""
                    st.markdown(
                        f"**#{t['id']}** {t['firm_name']} / {t['account_alias']} - "
                        f"{t['instrument']} {DIRECTION_LABELS.get(t['direction'], t['direction'])} "
                        f"{t['lot_size']} ({t['entry_time'][:16]}){viol_marker}"
                    )
                    st.caption(f"Nota: {t['notes']}")
                    st.divider()

        rows = []
        for t in trades:
            viol = json.loads(t.get("violations") or "[]")
            note = t.get("notes") or ""
            note_preview = (note[:40] + "...") if len(note) > 40 else note
            rows.append({
                "ID": t["id"],
                "Cuenta": f"{t['firm_name']} / {t['account_alias']}",
                "Fase": t["phase"],
                "Activo": t["instrument"],
                "Dir": DIRECTION_LABELS.get(t["direction"], t["direction"]),
                "Lote": t["lot_size"],
                "Entrada": t["entry_time"],
                "Salida": t.get("exit_time") or "ABIERTO",
                "Riesgo USD": t.get("risk_usd"),
                "P&L": t.get("pnl"),
                "R-mult": calc_r_multiple(t.get("pnl"), t.get("risk_usd")),
                "Spread USD": t.get("spread_pips"),
                "Nota": note_preview,
                "Violaciones": " | ".join(viol),
            })
        df = pd.DataFrame(rows)


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


        styled = (
            df.style
              .map(highlight_viol, subset=["Violaciones"])
              .map(color_pnl, subset=["P&L"])
        )
        st.dataframe(styled, use_container_width=True, hide_index=True)

        # Quick aggregated stats
        st.divider()
        st.subheader("Estadisticas del filtro")
        m1, m2, m3, m4 = st.columns(4)
        total_pnl = sum((t.get("pnl") or 0) for t in trades)
        total_viol = sum(1 for t in trades if json.loads(t.get("violations") or "[]"))
        spreads = [t.get("spread_pips") for t in trades if t.get("spread_pips")]
        avg_spread = (sum(spreads) / len(spreads)) if spreads else 0
        m1.metric("Trades", len(trades))
        m2.metric("P&L total USD", f"{total_pnl:,.2f}")
        m3.metric("Con violaciones", total_viol)
        m4.metric("Spread promedio USD", f"{avg_spread:.2f}" if avg_spread else "-")

        st.divider()
        with st.expander("Borrar un trade (cuidado)"):
            del_id = st.number_input("ID del trade a borrar", min_value=0, value=0, step=1)
            if st.button("Confirmar borrado", type="secondary"):
                if del_id > 0:
                    delete_trade(int(del_id))
                    st.success(f"Trade {del_id} borrado.")
                    st.rerun()
