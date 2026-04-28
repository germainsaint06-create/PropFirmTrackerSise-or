"""
Seed initial data: the 9 prop firms and the rules we know about so far.
Run this once after init_db() to populate the system.
You can re-run it safely; it only inserts what's missing.
"""
from db import get_conn, init_db, upsert_firm, list_rules, add_rule, clear_rules_for_firm


# All firms the user operates with
FIRMS = [
    {"name": "Trading Pit",          "default_inactivity_days": 12},
    {"name": "For Traders",          "default_inactivity_days": 20},
    {"name": "FTMO",                 "default_inactivity_days": 20},
    {"name": "FundingPips",          "default_inactivity_days": 20},
    {"name": "Funded Next",          "default_inactivity_days": 20},
    {"name": "Funded Trading Plus",  "default_inactivity_days": 20},
    {"name": "Alpha Capital",        "default_inactivity_days": 20},
    {"name": "The5ers",              "default_inactivity_days": 20},
    {"name": "E8 Markets",           "default_inactivity_days": 20},
]


# Hard rules per firm. Format:
#   (phase_or_None, instrument_or_None, rule_type, value, notes)
# phase = None means rule applies in any phase.
# instrument = None means rule applies to any instrument.
RULES_BY_FIRM = {
    "Trading Pit": [
        # Risk cap per trade in USD - applies across all phases and instruments
        (None, None, "max_risk_usd", 1500.0, "Riesgo maximo por operacion (basado en SL)"),
        # Lot caps per instrument (apply across all phases unless overridden)
        (None, "US30",   "max_lot", 0.75, "Dow Jones"),
        (None, "XAUUSD", "max_lot", 0.77, "Oro"),
        (None, "NAS100", "max_lot", 1.35, "Nasdaq"),
    ],
    "For Traders": [
        # Phase 1 / Phase 2 limits (challenge phases)
        ("phase1", "US30",   "max_lot", 17.0, "Dow Jones - Fase challenge"),
        ("phase1", "NAS100", "max_lot", 28.0, "Nasdaq - Fase challenge"),
        ("phase1", "XAUUSD", "max_lot", 3.0,  "Oro - Fase challenge"),
        ("phase2", "US30",   "max_lot", 17.0, "Dow Jones - Fase challenge"),
        ("phase2", "NAS100", "max_lot", 28.0, "Nasdaq - Fase challenge"),
        ("phase2", "XAUUSD", "max_lot", 3.0,  "Oro - Fase challenge"),
        # Funded (real) limits
        ("funded", "NAS100", "max_lot", 14.0, "Nasdaq - Cuenta real"),
        ("funded", "US30",   "max_lot", 8.0,  "Dow Jones - Cuenta real"),
        ("funded", "XAUUSD", "max_lot", 0.8,  "Oro - Cuenta real"),
    ],
}


def seed():
    init_db()

    # Insert firms
    firm_ids = {}
    for f in FIRMS:
        fid = upsert_firm(f["name"], f["default_inactivity_days"])
        firm_ids[f["name"]] = fid
        print(f"  Firm OK: {f['name']} (id={fid}, inactivity={f['default_inactivity_days']}d)")

    # Insert rules - clear and re-insert to keep clean
    for firm_name, rules in RULES_BY_FIRM.items():
        fid = firm_ids[firm_name]
        clear_rules_for_firm(fid)
        for phase, instrument, rtype, rvalue, notes in rules:
            add_rule(fid, rtype, rvalue, phase=phase, instrument=instrument, notes=notes)
        print(f"  Rules loaded for {firm_name}: {len(rules)}")

    print("\nSeed complete.")


if __name__ == "__main__":
    seed()
