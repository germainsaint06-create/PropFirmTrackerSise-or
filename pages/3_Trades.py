"""Trades - registro de operaciones con deteccion de violaciones."""
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

if not st.session_state.get("authed"):
    st.warning("Inicia sesion en la pagina principal.")
    st.stop()

st.title("Trades")
st.caption("Registro de operaciones, deteccion de violaciones de reglas y P&L")

# Common instruments - editable list
COMMON_INSTRUMENTS = [
    "XAUUSD",   # Oro
    "US30",     # Dow Jones
    "NAS100",   # Nasdaq
    "SPX500",   # S&P
    "GBPUSD",   # GU
    "EURUSD",   # EU
    "GBPJPY",   # GJ
    "USDJPY",
    "AUDUSD",
    "EURJPY",
    "BTCUSD",
    "ETHUSD",
    "USOIL",
    "OTRO",
]

active_accounts = list_accounts(status="active")
if not active_accounts:
    st.warning("No hay cuentas activas. Crea una en la pagina **Cuentas** primero.")
    st.stop()

acct_lookup = {f"#{a['id']} - {a['firm_name']} / {a['account_alias']} ({a['phase']})": a
               for a in active_accounts}

tab_new, tab_list = st.tabs(["Registrar trade", "Historial"])

# ---------------- Registrar ----------------
with tab_new:
    st.subheader("Nuevo trade")

    # Outside of form: account selector (so we can validate live)
    selected_label = st.selectbox("Cuenta", list(acct_lookup.keys()))
    acct = acct_lookup[selected_label]

    with st.form("new_trade", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        instrument_choice = c1.selectbox("Activo", COMMON_INSTRUMENTS)
        instrument_other = c1.text_input("Si elegiste OTRO, escribe el simbolo aqui",
                                          placeholder="ej: XAGUSD")
        direction = c2.selectbox("Direccion", ["long", "short"])
        lot_size = c3.number_input("Lotaje", min_value=0.0, value=0.10, step=0.01, format="%.2f")

        c4, c5, c6 = st.columns(3)
        entry_date = c4.date_input("Fecha entrada", value=date.today())
        entry_t = c5.time_input("Hora entrada", value=datetime.now().time())
        spread = c6.number_input("Spread USD", min_value=0.0, value=0.0,
                                 step=0.5, format="%.2f",
                                 help="Costo del spread pagado al entrar, en USD")

        c7, c8, c9 = st.columns(3)
        entry_price = c7.number_input("Precio entrada", min_value=0.0, value=0.0, step=0.01, format="%.5f")
        sl_price = c8.number_input("Stop loss", min_value=0.0, value=0.0, step=0.01, format="%.5f")
        tp_price = c9.number_input("Take profit", min_value=0.0, value=0.0, step=0.01, format="%.5f")

        c10, c11 = st.columns(2)
        risk_usd = c10.number_input("Riesgo USD (entrada -> SL)",
                                    min_value=0.0, value=0.0, step=10.0,
                                    help="Si lo dejas en 0 y la regla de la firm es de riesgo USD, no se podra validar.")
        pnl = c11.number_input("P&L realizado (USD, dejalo en 0 si esta abierto)",
                               value=0.0, step=10.0)

        c12, c13 = st.columns(2)
        exit_date = c12.date_input("Fecha cierre (opcional)", value=date.today())
        exit_t = c13.time_input("Hora cierre", value=datetime.now().time())
        is_closed = st.checkbox("Trade cerrado", value=True)

        notes = st.text_area("Notas")

        submitted = st.form_submit_button("Registrar trade", type="primary")
        if submitted:
            instrument = instrument_other.strip().upper() if instrument_choice == "OTRO" else instrument_choice
            if not instrument:
                st.error("Especifica un activo.")
            else:
                # Build entry/exit timestamps
                entry_dt = datetime.combine(entry_date, entry_t)
                exit_dt = datetime.combine(exit_date, exit_t) if is_closed else None

                # Run rules engine (checks firm-level + account-specific rules)
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
                    exit_time=exit_dt.isoformat() if exit_dt else None,
                    entry_price=entry_price or None,
                    exit_price=None,  # set below if closed
                    stop_loss=sl_price or None,
                    take_profit=tp_price or None,
                    risk_usd=risk_usd or None,
                    pnl=pnl if is_closed else None,
                    spread_pips=spread or None,
                    notes=notes.strip() or None,
                    violations=violations,
                )

                # Update current balance if PnL provided
                old_balance = acct.get("current_balance") or acct["initial_balance"]
                new_balance = old_balance
                if is_closed and pnl != 0:
                    new_balance = float(old_balance) + float(pnl)
                    update_account(acct["id"], current_balance=new_balance)

                if violations:
                    st.error(f"Trade #{tid} registrado con {len(violations)} VIOLACION(ES):")
                    for v in violations:
                        st.write(f"  - {v}")
                else:
                    st.success(f"Trade #{tid} registrado. Sin violaciones detectadas.")

                if is_closed and pnl != 0:
                    delta = pnl
                    icon = "+" if delta >= 0 else ""
                    st.info(
                        f"**Balance actualizado:** {old_balance:,.2f} -> {new_balance:,.2f} "
                        f"({icon}{delta:,.2f} USD)"
                    )

# ---------------- Historial ----------------
with tab_list:
    st.subheader("Historial")

    c1, c2 = st.columns([2, 1])
    filter_account = c1.selectbox(
        "Filtrar por cuenta",
        ["(Todas)"] + list(acct_lookup.keys())
    )
    limit_n = c2.number_input("Mostrar ultimas N", min_value=10, max_value=2000, value=100, step=10)

    aid = None if filter_account == "(Todas)" else acct_lookup[filter_account]["id"]
    trades = list_trades(account_id=aid, limit=limit_n)

    if not trades:
        st.info("No hay trades para mostrar.")
    else:
        rows = []
        for t in trades:
            viol = json.loads(t.get("violations") or "[]")
            rows.append({
                "ID": t["id"],
                "Cuenta": f"{t['firm_name']} / {t['account_alias']}",
                "Fase": t["phase"],
                "Activo": t["instrument"],
                "Dir": t["direction"],
                "Lote": t["lot_size"],
                "Entrada": t["entry_time"],
                "Salida": t.get("exit_time") or "ABIERTO",
                "Riesgo USD": t.get("risk_usd"),
                "P&L": t.get("pnl"),
                "Spread USD": t.get("spread_pips"),
                "Violaciones": " | ".join(viol),
            })
        df = pd.DataFrame(rows)


        def highlight_viol(val):
            return "background-color: #ef4444; color: #0a0e1a; font-weight: 600;" if val else ""


        st.dataframe(
            df.style.map(highlight_viol, subset=["Violaciones"]),
            use_container_width=True,
            hide_index=True,
        )

        # Quick aggregated stats
        st.divider()
        st.subheader("Estadisticas del filtro")
        m1, m2, m3, m4 = st.columns(4)
        total_pnl = sum((t.get("pnl") or 0) for t in trades)
        total_viol = sum(1 for t in trades if json.loads(t.get("violations") or "[]"))
        avg_spread = (sum((t.get("spread_pips") or 0) for t in trades if t.get("spread_pips"))
                      / max(1, sum(1 for t in trades if t.get("spread_pips"))))
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
