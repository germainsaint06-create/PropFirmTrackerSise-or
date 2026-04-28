"""
Rules engine.

Two responsibilities:
1. When a trade is registered, compute which firm rules it violates.
2. For each account, compute current inactivity status (green / yellow / red / breach).

Alert thresholds:
 - GREEN  : days_inactive < 75% of limit
 - YELLOW : 75% <= days_inactive < 90%
 - RED    : 90% <= days_inactive < 100%
 - BREACH : days_inactive >= limit
"""
from datetime import datetime, date, timedelta
from db import list_rules


# ------------------ Trade-level rule checks ------------------

def check_trade_against_rules(firm_id, phase, instrument, lot_size, risk_usd):
    """
    Return list of human-readable violation strings for the given trade.
    Empty list = no violations.
    """
    violations = []
    rules = list_rules(firm_id=firm_id)

    for r in rules:
        applies_phase = r["phase"] is None or r["phase"] == phase
        applies_instr = r["instrument"] is None or r["instrument"] == instrument
        if not (applies_phase and applies_instr):
            continue

        rtype = r["rule_type"]
        rvalue = r["rule_value"]

        if rtype == "max_lot" and lot_size is not None:
            if lot_size > rvalue:
                violations.append(
                    f"Lotaje {lot_size} excede maximo {rvalue} "
                    f"para {instrument or 'cualquier activo'} en {phase or 'cualquier fase'}"
                )
        elif rtype == "max_risk_usd" and risk_usd is not None:
            if risk_usd > rvalue:
                violations.append(
                    f"Riesgo USD {risk_usd:.2f} excede maximo {rvalue:.2f}"
                )
    return violations


# ------------------ Account-level inactivity checks ------------------

def inactivity_status(account_row, today=None):
    """
    Given an account row (with last_trade_date and default_inactivity_days),
    return a dict:
        {
          'days_inactive': int,
          'limit_days': int,
          'pct': float,
          'level': 'green' | 'yellow' | 'red' | 'breach' | 'no_trades',
          'message': str
        }
    """
    today = today or date.today()
    limit = account_row.get("default_inactivity_days") or 20

    last = account_row.get("last_trade_date")
    if not last:
        # No trades ever - we count from start date
        ref = account_row.get("started_at") or account_row.get("created_at")
        if isinstance(ref, str):
            try:
                ref = datetime.fromisoformat(ref).date()
            except ValueError:
                ref = today
        elif isinstance(ref, datetime):
            ref = ref.date()
        elif ref is None:
            ref = today
        days = (today - ref).days
        level_msg_prefix = "Sin trades aun"
    else:
        if isinstance(last, str):
            try:
                last = datetime.fromisoformat(last).date()
            except ValueError:
                last = today
        elif isinstance(last, datetime):
            last = last.date()
        days = (today - last).days
        level_msg_prefix = f"Ultimo trade hace {days}d"

    pct = days / limit if limit else 0
    if days >= limit:
        level = "breach"
    elif pct >= 0.90:
        level = "red"
    elif pct >= 0.75:
        level = "yellow"
    else:
        level = "green"

    return {
        "days_inactive": days,
        "limit_days": limit,
        "pct": pct,
        "level": level,
        "message": f"{level_msg_prefix} (limite {limit}d)",
    }


LEVEL_COLORS = {
    "green":   "#22c55e",
    "yellow":  "#eab308",
    "red":     "#f97316",
    "breach":  "#ef4444",
    "no_trades": "#64748b",
}

LEVEL_LABELS = {
    "green":     "OK",
    "yellow":    "ATENCION",
    "red":       "ALERTA",
    "breach":    "BREACH",
    "no_trades": "Sin trades",
}
