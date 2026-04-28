"""
Prop Firm Tracker - Main entry point.
Run with: streamlit run app.py
"""
import streamlit as st
import os
from db import init_db, list_accounts, list_firms
from rules_engine import inactivity_status, LEVEL_COLORS, LEVEL_LABELS

# Initialize database on first import
init_db()

st.set_page_config(
    page_title="Prop Firm Tracker",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------ Simple password gate ------------------
# Set the password via env var APP_PASSWORD when deploying.
# For local dev, default is 'admin' - change before deploying!
APP_PASSWORD = os.environ.get("APP_PASSWORD", "admin")


def check_password():
    if st.session_state.get("authed"):
        return True

    st.markdown("## Acceso")
    pwd = st.text_input("Contrasena", type="password")
    if st.button("Entrar"):
        if pwd == APP_PASSWORD:
            st.session_state["authed"] = True
            st.rerun()
        else:
            st.error("Contrasena incorrecta")
    return False


if not check_password():
    st.stop()


# ------------------ Custom CSS for professional look ------------------
st.markdown("""
<style>
    .main > div { padding-top: 1rem; }
    .stMetric { background: #111827; padding: 1rem; border-radius: 8px;
                border: 1px solid #1f2937; }
    .stat-card { background: #111827; padding: 1.2rem; border-radius: 10px;
                 border: 1px solid #1f2937; margin-bottom: 0.6rem; }
    .alert-pill { display: inline-block; padding: 2px 10px; border-radius: 99px;
                  font-size: 12px; font-weight: 600; color: #0a0e1a; }
    h1, h2, h3 { color: #e5e7eb; }
    .small-muted { color: #94a3b8; font-size: 13px; }
    [data-testid="stSidebarNav"] { padding-top: 1rem; }
</style>
""", unsafe_allow_html=True)


# ------------------ Landing page ------------------
st.title("Prop Firm Tracker")
st.caption("Sistema de control de cuentas, riesgo y reglas por prop firm")

firms = list_firms()
accounts = list_accounts(status="active")

# Top metrics
col1, col2, col3, col4 = st.columns(4)
col1.metric("Firms registradas", len(firms))
col2.metric("Cuentas activas", len(accounts))

# Compute alert counts
alert_counts = {"green": 0, "yellow": 0, "red": 0, "breach": 0, "no_trades": 0}
for a in accounts:
    s = inactivity_status(a)
    alert_counts[s["level"]] = alert_counts.get(s["level"], 0) + 1

col3.metric("En alerta (amarilla+)", alert_counts["yellow"] + alert_counts["red"])
col4.metric("En breach", alert_counts["breach"], delta_color="inverse")

st.divider()

if not firms:
    st.warning("No hay prop firms cargadas. Corre `python seed.py` desde la terminal.")
    st.stop()

if not accounts:
    st.info("Aun no hay cuentas activas. Ve a la pagina **Cuentas** en la barra lateral para agregar la primera.")
else:
    st.subheader("Resumen rapido")
    st.write("Las cuentas con alerta amarilla, roja o en breach aparecen primero. "
             "Para detalle completo, ve a la pagina **Dashboard** en la barra lateral.")

    # Show top 10 most concerning
    sorted_accts = sorted(
        accounts,
        key=lambda a: (
            -inactivity_status(a)["pct"],
        )
    )[:10]

    for a in sorted_accts:
        s = inactivity_status(a)
        color = LEVEL_COLORS[s["level"]]
        label = LEVEL_LABELS[s["level"]]
        st.markdown(
            f"""
            <div class="stat-card">
              <span class="alert-pill" style="background:{color};">{label}</span>
              &nbsp;<strong>{a['firm_name']}</strong> &mdash; {a['account_alias']}
              <span class="small-muted">({a['phase']})</span>
              <div class="small-muted">{s['message']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.divider()
st.markdown(
    """
    **Navegacion** (barra lateral izquierda):
    - **Dashboard** &mdash; vista detallada de todas las cuentas con alertas y filtros
    - **Cuentas** &mdash; agregar, editar y archivar cuentas
    - **Trades** &mdash; registrar nuevas operaciones y ver historial
    - **Reglas** &mdash; ver y editar reglas por prop firm
    """
)
