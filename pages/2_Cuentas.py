"""Cuentas - gestion de cuentas (alta, edicion, archivo, balance)."""
import streamlit as st
import pandas as pd
from datetime import date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import (
    list_accounts, list_firms, create_account, update_account,
    archive_account, get_account, recalculate_balance_from_trades,
    list_status_changes
)
from rules_engine import inactivity_status

if not st.session_state.get("authed"):
    st.warning("Inicia sesion en la pagina principal.")
    st.stop()

st.title("Cuentas")
st.caption("Alta, edicion, archivo y balance de cuentas")

firms = list_firms()
if not firms:
    st.error("No hay prop firms. Corre `python seed.py` primero.")
    st.stop()

firm_lookup = {f["name"]: f["id"] for f in firms}

tab_new, tab_list, tab_edit, tab_history = st.tabs([
    "Crear cuenta", "Lista de cuentas", "Editar / Balance / Estado", "Historial de estados"
])

# ---------------- Crear cuenta ----------------
with tab_new:
    st.subheader("Nueva cuenta")
    with st.form("new_account_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        firm_name = c1.selectbox("Prop firm", list(firm_lookup.keys()))
        phase = c2.selectbox("Fase", ["phase1", "phase2", "funded"])

        c3, c4 = st.columns(2)
        alias = c3.text_input("Alias (nombre corto que identifique la cuenta)",
                              placeholder="ej: Alpha 40, Trading Pit 33")
        number = c4.text_input("Numero de cuenta del broker (opcional)")

        c5, c6 = st.columns(2)
        balance = c5.number_input("Balance inicial (USD)", min_value=0.0, value=100000.0, step=1000.0)
        started = c6.date_input("Fecha de inicio", value=date.today())

        notes = st.text_area("Notas (opcional)")

        submitted = st.form_submit_button("Crear cuenta", type="primary")
        if submitted:
            if not alias.strip():
                st.error("El alias es obligatorio.")
            else:
                fid = firm_lookup[firm_name]
                acct_id = create_account(
                    firm_id=fid,
                    account_alias=alias.strip(),
                    account_number=number.strip() or None,
                    phase=phase,
                    initial_balance=balance,
                    started_at=started.isoformat(),
                    notes=notes.strip() or None,
                )
                st.success(f"Cuenta creada (id={acct_id}): {firm_name} / {alias}")

# ---------------- Lista ----------------
with tab_list:
    st.subheader("Cuentas")
    show_archived = st.checkbox("Mostrar archivadas / breach / perdidas / paid out")
    status_filter = None if show_archived else "active"

    accounts = list_accounts(status=status_filter)
    if not accounts:
        st.info("No hay cuentas para mostrar.")
    else:
        rows = []
        for a in accounts:
            s = inactivity_status(a)
            rows.append({
                "ID": a["id"],
                "Firm": a["firm_name"],
                "Alias": a["account_alias"],
                "Numero": a.get("account_number") or "",
                "Fase": a["phase"],
                "Status": a["status"],
                "Balance ini": a["initial_balance"],
                "Balance act": a.get("current_balance"),
                "Trades": a.get("trade_count", 0),
                "Dias inactiva": s["days_inactive"],
                "Limite": s["limit_days"],
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(f"Total: {len(rows)} cuentas")

# ---------------- Editar ----------------
with tab_edit:
    st.subheader("Editar cuenta, balance y estado")
    accounts = list_accounts()
    if not accounts:
        st.info("No hay cuentas creadas.")
    else:
        options = {f"#{a['id']} - {a['firm_name']} / {a['account_alias']} ({a['status']})": a["id"]
                   for a in accounts}
        selected_label = st.selectbox("Selecciona la cuenta", list(options.keys()))
        acct_id = options[selected_label]
        acct = get_account(acct_id)

        # Balance display section - always visible
        st.markdown("### Balance")
        bcol1, bcol2, bcol3 = st.columns(3)
        bcol1.metric("Balance inicial", f"{acct['initial_balance']:,.2f}")
        cur_bal = float(acct.get("current_balance") or acct["initial_balance"])
        delta = cur_bal - float(acct["initial_balance"])
        bcol2.metric("Balance actual", f"{cur_bal:,.2f}",
                     delta=f"{delta:+,.2f}" if delta != 0 else None)
        from db import list_trades
        trades = list_trades(account_id=acct_id)
        sum_pnl = sum((t.get("pnl") or 0) for t in trades)
        bcol3.metric("Suma P&L de trades", f"{sum_pnl:,.2f}")

        st.caption(
            "El **Balance actual** se actualiza automaticamente con el P&L de cada trade que registres como cerrado. "
            "Si la suma de P&L y el balance actual no coinciden, alguien hizo edicion manual."
        )

        ccol1, ccol2 = st.columns(2)
        if ccol1.button("Recalcular balance desde trades", help="Reescribe balance actual = inicial + suma de P&L"):
            new_bal = recalculate_balance_from_trades(acct_id)
            st.success(f"Balance recalculado: {new_bal:,.2f}")
            st.rerun()

        with ccol2.expander("Editar balance manualmente"):
            new_manual = st.number_input(
                "Nuevo balance actual",
                value=cur_bal,
                step=10.0
            )
            if st.button("Guardar balance manual"):
                update_account(acct_id, current_balance=new_manual)
                st.success("Balance actualizado manualmente.")
                st.rerun()

        st.divider()
        st.markdown("### Datos de la cuenta")
        with st.form("edit_account"):
            c1, c2 = st.columns(2)
            new_alias = c1.text_input("Alias", value=acct["account_alias"])
            new_number = c2.text_input("Numero", value=acct.get("account_number") or "")

            c3, c4 = st.columns(2)
            phase_opts = ["phase1", "phase2", "funded"]
            new_phase = c3.selectbox(
                "Fase",
                phase_opts,
                index=phase_opts.index(acct["phase"]) if acct["phase"] in phase_opts else 0
            )
            new_balance_ini = c4.number_input("Balance inicial",
                                              value=float(acct["initial_balance"]))

            new_notes = st.text_area("Notas", value=acct.get("notes") or "")

            submit_edit = st.form_submit_button("Guardar cambios", type="primary")
            if submit_edit:
                update_account(
                    acct_id,
                    account_alias=new_alias.strip(),
                    account_number=new_number.strip() or None,
                    phase=new_phase,
                    initial_balance=new_balance_ini,
                    notes=new_notes.strip() or None,
                )
                st.success("Cambios guardados.")
                st.rerun()

        st.divider()
        st.markdown("### Cambiar estado de la cuenta")

        with st.expander("Que significa cada estado"):
            st.markdown(
                "- **active**: cuenta operando normalmente.\n"
                "- **archived**: cuenta apartada por decision propia (no perdida, no cobrada). "
                "Sus datos siguen guardados.\n"
                "- **breached**: cuenta perdida por incumplir alguna regla de la firm "
                "(profit target, max DD, daily DD, regla de inactividad, etc.).\n"
                "- **lost**: cuenta perdida por drawdown del mercado / decisiones operativas, "
                "sin haber breach explicito.\n"
                "- **paid_out**: cuenta cobrada (retiraste profit de una funded). "
                "Sigue en el sistema con todo su historial.\n\n"
                "**Importante:** ningun estado borra datos. Las cuentas en cualquier estado "
                "siguen consultables marcando 'Mostrar archivadas' en la lista de cuentas."
            )

        st.markdown(f"Estado actual: **{acct['status']}**")

        new_status = st.selectbox(
            "Cambiar a",
            ["active", "archived", "breached", "lost", "paid_out"],
            index=["active", "archived", "breached", "lost", "paid_out"].index(acct["status"])
                if acct["status"] in ("active", "archived", "breached", "lost", "paid_out") else 0
        )
        reason = st.text_input("Razon del cambio (opcional pero recomendado)",
                               placeholder="ej: violo daily DD el 2026-04-29")
        if st.button("Aplicar cambio de estado", type="primary"):
            archive_account(acct_id, new_status, reason.strip() or None)
            st.success(f"Estado cambiado a {new_status}.")
            st.rerun()

# ---------------- Historial ----------------
with tab_history:
    st.subheader("Historial de cambios de estado")
    st.caption("Cada vez que cambia el estado de una cuenta queda registrado aqui")

    changes = list_status_changes()
    if not changes:
        st.info("Aun no hay cambios de estado registrados.")
    else:
        rows = [{
            "Fecha": c["changed_at"],
            "Firm": c["firm_name"],
            "Cuenta": c["account_alias"],
            "De": c.get("old_status") or "(nuevo)",
            "A": c["new_status"],
            "Razon": c.get("reason") or "",
        } for c in changes]
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
