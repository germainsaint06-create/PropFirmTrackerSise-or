"""Cuentas - gestion de cuentas (alta, edicion, archivo)."""
import streamlit as st
import pandas as pd
from datetime import date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import (
    list_accounts, list_firms, create_account, update_account,
    archive_account, get_account
)
from rules_engine import inactivity_status

if not st.session_state.get("authed"):
    st.warning("Inicia sesion en la pagina principal.")
    st.stop()

st.title("Cuentas")
st.caption("Alta, edicion y archivo de cuentas")

firms = list_firms()
if not firms:
    st.error("No hay prop firms. Corre `python seed.py` primero.")
    st.stop()

firm_lookup = {f["name"]: f["id"] for f in firms}

tab_new, tab_list, tab_edit = st.tabs(["Crear cuenta", "Lista de cuentas", "Editar / Archivar"])

# ---------------- Crear cuenta ----------------
with tab_new:
    st.subheader("Nueva cuenta")
    with st.form("new_account_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        firm_name = c1.selectbox("Prop firm", list(firm_lookup.keys()))
        phase = c2.selectbox("Fase", ["phase1", "phase2", "funded"])

        c3, c4 = st.columns(2)
        alias = c3.text_input("Alias (nombre corto que identifique la cuenta)",
                              placeholder="ej: TP-100k-A")
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
    st.subheader("Cuentas activas")
    show_archived = st.checkbox("Mostrar archivadas / breach / perdidas")
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
    st.subheader("Editar / archivar cuenta")
    accounts = list_accounts()
    if not accounts:
        st.info("No hay cuentas creadas.")
    else:
        options = {f"#{a['id']} - {a['firm_name']} / {a['account_alias']} ({a['status']})": a["id"]
                   for a in accounts}
        selected_label = st.selectbox("Selecciona la cuenta", list(options.keys()))
        acct_id = options[selected_label]
        acct = get_account(acct_id)

        with st.form("edit_account"):
            c1, c2 = st.columns(2)
            new_alias = c1.text_input("Alias", value=acct["account_alias"])
            new_number = c2.text_input("Numero", value=acct.get("account_number") or "")

            c3, c4 = st.columns(2)
            new_phase = c3.selectbox(
                "Fase",
                ["phase1", "phase2", "funded"],
                index=["phase1", "phase2", "funded"].index(acct["phase"]) if acct["phase"] in ("phase1", "phase2", "funded") else 0
            )
            new_status = c4.selectbox(
                "Status",
                ["active", "archived", "breached", "lost", "paid_out"],
                index=["active", "archived", "breached", "lost", "paid_out"].index(acct["status"]) if acct["status"] in ("active", "archived", "breached", "lost", "paid_out") else 0
            )

            c5, c6 = st.columns(2)
            new_balance_ini = c5.number_input("Balance inicial",
                                              value=float(acct["initial_balance"]))
            new_balance_act = c6.number_input("Balance actual",
                                              value=float(acct.get("current_balance") or acct["initial_balance"]))

            new_notes = st.text_area("Notas", value=acct.get("notes") or "")

            submit_edit = st.form_submit_button("Guardar cambios", type="primary")
            if submit_edit:
                update_account(
                    acct_id,
                    account_alias=new_alias.strip(),
                    account_number=new_number.strip() or None,
                    phase=new_phase,
                    status=new_status,
                    initial_balance=new_balance_ini,
                    current_balance=new_balance_act,
                    notes=new_notes.strip() or None,
                )
                st.success("Cambios guardados.")
                st.rerun()

        st.divider()
        st.markdown("**Acciones rapidas**")
        cols = st.columns(4)
        if cols[0].button("Archivar", use_container_width=True):
            archive_account(acct_id, "archived")
            st.success("Cuenta archivada.")
            st.rerun()
        if cols[1].button("Marcar BREACH", use_container_width=True):
            archive_account(acct_id, "breached")
            st.success("Cuenta marcada en breach.")
            st.rerun()
        if cols[2].button("Marcar PERDIDA", use_container_width=True):
            archive_account(acct_id, "lost")
            st.success("Cuenta marcada como perdida.")
            st.rerun()
        if cols[3].button("Marcar PAID OUT", use_container_width=True):
            archive_account(acct_id, "paid_out")
            st.success("Cuenta marcada como paid out.")
            st.rerun()
