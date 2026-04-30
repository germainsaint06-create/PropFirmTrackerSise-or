"""
Database module for Prop Firm Tracker.
SQLite database with full schema for accounts, firms, rules, trades.
"""
import sqlite3
import os
from contextlib import contextmanager
from datetime import datetime, date
from pathlib import Path

# Database lives next to the code so it's easy to back up
DB_PATH = os.environ.get("TRACKER_DB", str(Path(__file__).parent / "data" / "tracker.db"))


def _ensure_dir():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_conn():
    """Context manager that yields a SQLite connection with row factory set.

    NOTE: We intentionally do NOT use detect_types=PARSE_DECLTYPES because
    SQLite's built-in TIMESTAMP converter expects 'YYYY-MM-DD HH:MM:SS'
    format and breaks on ISO format with 'T' separator that we use.
    Timestamps are stored and retrieved as ISO strings; parsing happens
    in application code (rules_engine.py) when needed.
    """
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
-- Prop firms (one row per firm we operate with)
CREATE TABLE IF NOT EXISTS prop_firms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    default_inactivity_days INTEGER DEFAULT 20,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Rules per firm (lot caps, risk caps, inactivity overrides, etc.)
-- phase = NULL means rule applies to all phases
-- instrument = NULL means rule applies to all instruments
-- account_id = NULL means rule applies to entire firm; if set, rule is account-specific
CREATE TABLE IF NOT EXISTS firm_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    firm_id INTEGER NOT NULL,
    account_id INTEGER,
    phase TEXT,
    instrument TEXT,
    rule_type TEXT NOT NULL,    -- 'max_lot' | 'max_risk_usd' | 'inactivity_days'
    rule_value REAL NOT NULL,
    notes TEXT,
    FOREIGN KEY (firm_id) REFERENCES prop_firms(id) ON DELETE CASCADE,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

-- Status history of accounts (when status changes, log it)
CREATE TABLE IF NOT EXISTS account_status_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    reason TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

-- Accounts (one row per active or archived account)
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    firm_id INTEGER NOT NULL,
    account_alias TEXT NOT NULL,
    account_number TEXT,
    phase TEXT NOT NULL,        -- 'phase1' | 'phase2' | 'funded'
    initial_balance REAL NOT NULL,
    current_balance REAL,
    status TEXT DEFAULT 'active',  -- 'active' | 'archived' | 'breached' | 'lost' | 'paid_out'
    started_at DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (firm_id) REFERENCES prop_firms(id)
);

-- Trades (one row per registered trade)
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    instrument TEXT NOT NULL,
    direction TEXT NOT NULL,    -- 'long' | 'short'
    lot_size REAL NOT NULL,
    entry_time TIMESTAMP NOT NULL,
    exit_time TIMESTAMP,
    entry_price REAL,
    exit_price REAL,
    stop_loss REAL,
    take_profit REAL,
    risk_usd REAL,              -- declared risk in USD (entry - SL based)
    pnl REAL,                   -- realized P&L if closed
    spread_pips REAL,           -- spread paid on entry (in pips or points)
    screenshot_path TEXT,
    notes TEXT,
    violations TEXT,            -- JSON array of violation strings
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_trades_account ON trades(account_id);
CREATE INDEX IF NOT EXISTS idx_trades_entry ON trades(entry_time);
CREATE INDEX IF NOT EXISTS idx_accounts_firm ON accounts(firm_id);
CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);
CREATE INDEX IF NOT EXISTS idx_firm_rules_firm ON firm_rules(firm_id);
"""


def init_db():
    """Create all tables if they don't exist, and run migrations."""
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        # Migration: add account_id column to firm_rules if missing
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(firm_rules)")]
        if "account_id" not in cols:
            conn.execute("ALTER TABLE firm_rules ADD COLUMN account_id INTEGER")


def reset_db():
    """Wipe and recreate the database. USE WITH CARE."""
    if Path(DB_PATH).exists():
        Path(DB_PATH).unlink()
    init_db()


# ------------------ Firms ------------------

def list_firms():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM prop_firms ORDER BY name"
        )]


def get_firm(firm_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM prop_firms WHERE id = ?", (firm_id,)
        ).fetchone()
        return dict(row) if row else None


def upsert_firm(name, default_inactivity_days=20, notes=None):
    """Insert or update a firm by name."""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM prop_firms WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE prop_firms SET default_inactivity_days = ?, notes = ? WHERE id = ?",
                (default_inactivity_days, notes, existing["id"])
            )
            return existing["id"]
        cur = conn.execute(
            "INSERT INTO prop_firms (name, default_inactivity_days, notes) VALUES (?, ?, ?)",
            (name, default_inactivity_days, notes)
        )
        return cur.lastrowid


# ------------------ Rules ------------------

def list_rules(firm_id=None, account_id=None, only_firm_level=False, only_account_level=False):
    """List rules.

    - only_firm_level=True: only firm-wide rules (account_id IS NULL)
    - only_account_level=True: only account-specific rules (account_id IS NOT NULL)
    - account_id=N: rules that apply to that specific account
                    (firm-level rules of its firm + its own account-specific rules)
    """
    sql = """
        SELECT fr.*, pf.name AS firm_name,
               a.account_alias AS account_alias
        FROM firm_rules fr
        JOIN prop_firms pf ON pf.id = fr.firm_id
        LEFT JOIN accounts a ON a.id = fr.account_id
        WHERE 1=1
    """
    params = []
    if account_id is not None:
        # Get account's firm_id, then return both its firm rules and its account-specific rules
        sql += """ AND (
            fr.account_id = ?
            OR (fr.account_id IS NULL AND fr.firm_id = (SELECT firm_id FROM accounts WHERE id = ?))
        )"""
        params.extend([account_id, account_id])
    elif firm_id is not None:
        sql += " AND fr.firm_id = ?"
        params.append(firm_id)

    if only_firm_level:
        sql += " AND fr.account_id IS NULL"
    if only_account_level:
        sql += " AND fr.account_id IS NOT NULL"

    sql += " ORDER BY pf.name, fr.account_id IS NULL DESC, a.account_alias, fr.phase, fr.instrument, fr.rule_type"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def add_rule(firm_id, rule_type, rule_value, phase=None, instrument=None,
             account_id=None, notes=None):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO firm_rules (firm_id, account_id, phase, instrument, rule_type, rule_value, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (firm_id, account_id, phase, instrument, rule_type, rule_value, notes)
        )
        return cur.lastrowid


def delete_rule(rule_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM firm_rules WHERE id = ?", (rule_id,))


def clear_rules_for_firm(firm_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM firm_rules WHERE firm_id = ?", (firm_id,))


# ------------------ Accounts ------------------

def list_accounts(status=None, firm_id=None):
    sql = """
        SELECT a.*, pf.name AS firm_name, pf.default_inactivity_days,
               (SELECT MAX(t.entry_time) FROM trades t WHERE t.account_id = a.id) AS last_trade_date,
               (SELECT COUNT(*) FROM trades t WHERE t.account_id = a.id) AS trade_count
        FROM accounts a
        JOIN prop_firms pf ON pf.id = a.firm_id
        WHERE 1=1
    """
    params = []
    if status:
        sql += " AND a.status = ?"
        params.append(status)
    if firm_id:
        sql += " AND a.firm_id = ?"
        params.append(firm_id)
    sql += " ORDER BY pf.name, a.account_alias"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def get_account(account_id):
    with get_conn() as conn:
        row = conn.execute(
            """SELECT a.*, pf.name AS firm_name, pf.default_inactivity_days
               FROM accounts a JOIN prop_firms pf ON pf.id = a.firm_id
               WHERE a.id = ?""",
            (account_id,)
        ).fetchone()
        return dict(row) if row else None


def create_account(firm_id, account_alias, account_number, phase, initial_balance,
                   started_at=None, notes=None):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO accounts (firm_id, account_alias, account_number, phase,
                                     initial_balance, current_balance, started_at, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (firm_id, account_alias, account_number, phase,
             initial_balance, initial_balance, started_at or date.today(), notes)
        )
        return cur.lastrowid


def update_account(account_id, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE accounts SET {cols} WHERE id = ?",
            (*fields.values(), account_id)
        )


def archive_account(account_id, status="archived", reason=None):
    """Change account status and log the change."""
    with get_conn() as conn:
        old = conn.execute("SELECT status FROM accounts WHERE id = ?", (account_id,)).fetchone()
        old_status = old["status"] if old else None
        conn.execute("UPDATE accounts SET status = ? WHERE id = ?", (status, account_id))
        conn.execute(
            """INSERT INTO account_status_log (account_id, old_status, new_status, reason)
               VALUES (?, ?, ?, ?)""",
            (account_id, old_status, status, reason)
        )


def list_status_changes(account_id=None):
    sql = """
        SELECT asl.*, a.account_alias, pf.name AS firm_name
        FROM account_status_log asl
        JOIN accounts a ON a.id = asl.account_id
        JOIN prop_firms pf ON pf.id = a.firm_id
        WHERE 1=1
    """
    params = []
    if account_id is not None:
        sql += " AND asl.account_id = ?"
        params.append(account_id)
    sql += " ORDER BY asl.changed_at DESC"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def recalculate_balance_from_trades(account_id):
    """Recompute current_balance as initial_balance + sum of P&Ls. Returns the new balance."""
    with get_conn() as conn:
        acct = conn.execute(
            "SELECT initial_balance FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if not acct:
            return None
        total_pnl = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) AS s FROM trades WHERE account_id = ? AND pnl IS NOT NULL",
            (account_id,)
        ).fetchone()["s"]
        new_balance = float(acct["initial_balance"]) + float(total_pnl)
        conn.execute(
            "UPDATE accounts SET current_balance = ? WHERE id = ?",
            (new_balance, account_id)
        )
        return new_balance


# ------------------ Trades ------------------

def list_trades(account_id=None, limit=None, since=None):
    sql = """
        SELECT t.*, a.account_alias, a.phase, pf.name AS firm_name
        FROM trades t
        JOIN accounts a ON a.id = t.account_id
        JOIN prop_firms pf ON pf.id = a.firm_id
        WHERE 1=1
    """
    params = []
    if account_id:
        sql += " AND t.account_id = ?"
        params.append(account_id)
    if since:
        sql += " AND t.entry_time >= ?"
        params.append(since)
    sql += " ORDER BY t.entry_time DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def create_trade(account_id, instrument, direction, lot_size, entry_time,
                 exit_time=None, entry_price=None, exit_price=None,
                 stop_loss=None, take_profit=None, risk_usd=None, pnl=None,
                 spread_pips=None, screenshot_path=None, notes=None,
                 violations=None):
    import json
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO trades (
                account_id, instrument, direction, lot_size, entry_time, exit_time,
                entry_price, exit_price, stop_loss, take_profit, risk_usd, pnl,
                spread_pips, screenshot_path, notes, violations
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (account_id, instrument, direction.lower(), lot_size, entry_time, exit_time,
             entry_price, exit_price, stop_loss, take_profit, risk_usd, pnl,
             spread_pips, screenshot_path, notes,
             json.dumps(violations or []))
        )
        return cur.lastrowid


def update_trade(trade_id, **fields):
    if not fields:
        return
    if "violations" in fields:
        import json
        fields["violations"] = json.dumps(fields["violations"])
    cols = ", ".join(f"{k} = ?" for k in fields)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE trades SET {cols} WHERE id = ?",
            (*fields.values(), trade_id)
        )


def delete_trade(trade_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM trades WHERE id = ?", (trade_id,))
