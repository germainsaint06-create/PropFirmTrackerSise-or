"""Reglas - vista y edicion de reglas por prop firm."""
import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import (
    list_firms, list_rules, add_rule, delete_rule, upsert_firm
)

if not st.session_state.get("authed"):
    st.warning("Inicia sesion en la pagina principal.")
    st.stop()

st.title("Reglas por prop firm")
st.caption("Configura las reglas que el sistema vigila para cada firma")

firms = list_firms()
firm_lookup = {f["name"]: f for f in firms}

tab_view, tab_add, tab_firm = st.tabs(["Ver reglas", "Agregar regla", "Editar firm"])

# ---------------- Ver ----------------
with tab_view:
    st.subheader("Reglas cargadas")
    selected_firm_name = st.selectbox(
        "Filtrar por firm",
        ["(Todas)"] + list(firm_lookup.keys())
    )
    firm_filter_id = None
    if selected_firm_name != "(Todas)":
        firm_filter_id = firm_lookup[selected_firm_name]["id"]

    rules = list_rules(firm_id=firm_filter_id)
    if not rules:
        st.info("No hay reglas cargadas para este filtro.")
    else:
        df = pd.DataFrame([{
            "ID": r["id"],
            "Firm": r["firm_name"],
            "Fase": r["phase"] or "(cualquiera)",
            "Activo": r["instrument"] or "(cualquiera)",
            "Tipo": r["rule_type"],
            "Valor": r["rule_value"],
            "Notas": r.get("notes") or "",
        } for r in rules])
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**Borrar regla**")
    del_id = st.number_input("ID de regla a borrar", min_value=0, value=0, step=1)
    if st.button("Borrar regla"):
        if del_id > 0:
            delete_rule(int(del_id))
            st.success("Regla borrada.")
            st.rerun()

# ---------------- Agregar ----------------
with tab_add:
    st.subheader("Agregar regla")
    with st.form("add_rule"):
        firm_name = st.selectbox("Firm", list(firm_lookup.keys()))
        rtype = st.selectbox(
            "Tipo de regla",
            ["max_lot", "max_risk_usd", "inactivity_days"],
            help=("max_lot: limite de lotaje. "
                  "max_risk_usd: limite de riesgo en USD por trade (basado en SL). "
                  "inactivity_days: override del default de inactividad de la firma.")
        )
        rvalue = st.number_input("Valor", min_value=0.0, step=0.1, format="%.4f")

        c1, c2 = st.columns(2)
        phase = c1.selectbox("Fase (opcional)", ["(cualquiera)", "phase1", "phase2", "funded"])
        instrument = c2.text_input("Activo (opcional, ej: XAUUSD, US30, NAS100)").strip().upper()

        notes = st.text_area("Notas (opcional)")

        if st.form_submit_button("Agregar regla", type="primary"):
            fid = firm_lookup[firm_name]["id"]
            add_rule(
                firm_id=fid,
                rule_type=rtype,
                rule_value=rvalue,
                phase=None if phase == "(cualquiera)" else phase,
                instrument=instrument or None,
                notes=notes.strip() or None,
            )
            st.success("Regla agregada.")
            st.rerun()

# ---------------- Editar firm ----------------
with tab_firm:
    st.subheader("Editar firm (default de inactividad)")
    sel = st.selectbox("Firm a editar", list(firm_lookup.keys()))
    f = firm_lookup[sel]
    new_inact = st.number_input(
        "Dias maximos de inactividad (default)",
        min_value=1, max_value=365,
        value=int(f["default_inactivity_days"] or 20)
    )
    new_notes = st.text_area("Notas de la firm", value=f.get("notes") or "")
    if st.button("Guardar firm", type="primary"):
        upsert_firm(f["name"], new_inact, new_notes.strip() or None)
        st.success("Firm actualizada.")
        st.rerun()

    st.divider()
    st.subheader("Crear nueva firm")
    with st.form("new_firm"):
        nf_name = st.text_input("Nombre de la firm")
        nf_inact = st.number_input("Dias maximos de inactividad",
                                   min_value=1, max_value=365, value=20)
        nf_notes = st.text_area("Notas")
        if st.form_submit_button("Crear firm"):
            if nf_name.strip():
                upsert_firm(nf_name.strip(), nf_inact, nf_notes.strip() or None)
                st.success(f"Firm '{nf_name}' creada.")
                st.rerun()
            else:
                st.error("El nombre es obligatorio.")
