import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "portfolio.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolios (
            preset_name TEXT PRIMARY KEY,
            initial_cash REAL NOT NULL,
            cash_balance REAL NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            preset_name TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            avg_buy_price REAL NOT NULL,
            PRIMARY KEY (preset_name, stock_code)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            preset_name TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            stock_name TEXT NOT NULL,
            action TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            amount REAL NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS preset_criteria (
            preset_name TEXT PRIMARY KEY,
            criteria_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def list_presets():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT preset_name FROM preset_criteria ORDER BY updated_at DESC")
    names = [row["preset_name"] for row in cur.fetchall()]
    conn.close()
    return names


def save_preset_criteria(preset_name, criteria_dict):
    import json
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO preset_criteria (preset_name, criteria_json, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(preset_name) DO UPDATE SET criteria_json = excluded.criteria_json, updated_at = excluded.updated_at",
        (preset_name, json.dumps(criteria_dict), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def load_preset_criteria(preset_name):
    import json
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT criteria_json FROM preset_criteria WHERE preset_name = ?", (preset_name,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return json.loads(row["criteria_json"])


def get_all_portfolio_summaries():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM portfolios", conn)
    conn.close()
    return df


def get_or_create_portfolio(preset_name, initial_cash=10_000_000):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM portfolios WHERE preset_name = ?", (preset_name,))
    row = cur.fetchone()

    if row is None:
        cur.execute(
            "INSERT INTO portfolios (preset_name, initial_cash, cash_balance, created_at) VALUES (?, ?, ?, ?)",
            (preset_name, initial_cash, initial_cash, datetime.now().isoformat())
        )
        conn.commit()
        result = {"preset_name": preset_name, "initial_cash": initial_cash, "cash_balance": initial_cash}
    else:
        result = dict(row)

    conn.close()
    return result


def get_holdings(preset_name):
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM holdings WHERE preset_name = ?", conn, params=(preset_name,)
    )
    conn.close()
    return df


def buy_stocks(preset_name, orders):
    """orders: list of dict {stock_code, stock_name, quantity, price}"""
    conn = get_connection()
    cur = conn.cursor()

    total_cost = sum(o["quantity"] * o["price"] for o in orders)

    cur.execute("SELECT cash_balance FROM portfolios WHERE preset_name = ?", (preset_name,))
    row = cur.fetchone()
    cash_balance = row["cash_balance"] if row else 0

    if total_cost > cash_balance:
        conn.close()
        return False, f"현금 부족: 필요 {total_cost:,.0f}원, 보유 현금 {cash_balance:,.0f}원"

    for o in orders:
        cur.execute(
            "SELECT quantity, avg_buy_price FROM holdings WHERE preset_name = ? AND stock_code = ?",
            (preset_name, o["stock_code"])
        )
        existing = cur.fetchone()

        if existing:
            new_qty = existing["quantity"] + o["quantity"]
            new_avg = (existing["quantity"] * existing["avg_buy_price"] + o["quantity"] * o["price"]) / new_qty
            cur.execute(
                "UPDATE holdings SET quantity = ?, avg_buy_price = ? WHERE preset_name = ? AND stock_code = ?",
                (new_qty, new_avg, preset_name, o["stock_code"])
            )
        else:
            cur.execute(
                "INSERT INTO holdings (preset_name, stock_code, stock_name, quantity, avg_buy_price) VALUES (?, ?, ?, ?, ?)",
                (preset_name, o["stock_code"], o["stock_name"], o["quantity"], o["price"])
            )

        cur.execute(
            "INSERT INTO transactions (preset_name, stock_code, stock_name, action, quantity, price, amount, timestamp) VALUES (?, ?, ?, 'BUY', ?, ?, ?, ?)",
            (preset_name, o["stock_code"], o["stock_name"], o["quantity"], o["price"],
             o["quantity"] * o["price"], datetime.now().isoformat())
        )

    cur.execute(
        "UPDATE portfolios SET cash_balance = cash_balance - ? WHERE preset_name = ?",
        (total_cost, preset_name)
    )

    conn.commit()
    conn.close()
    return True, f"매수 완료: 총 {total_cost:,.0f}원"


def sell_stocks(preset_name, sell_orders):
    """sell_orders: list of dict {stock_code, stock_name, price} - 전량 매도"""
    conn = get_connection()
    cur = conn.cursor()

    total_proceeds = 0

    for o in sell_orders:
        cur.execute(
            "SELECT quantity FROM holdings WHERE preset_name = ? AND stock_code = ?",
            (preset_name, o["stock_code"])
        )
        existing = cur.fetchone()
        if not existing:
            continue

        qty = existing["quantity"]
        proceeds = qty * o["price"]
        total_proceeds += proceeds

        cur.execute(
            "DELETE FROM holdings WHERE preset_name = ? AND stock_code = ?",
            (preset_name, o["stock_code"])
        )

        cur.execute(
            "INSERT INTO transactions (preset_name, stock_code, stock_name, action, quantity, price, amount, timestamp) VALUES (?, ?, ?, 'SELL', ?, ?, ?, ?)",
            (preset_name, o["stock_code"], o["stock_name"], qty, o["price"], proceeds, datetime.now().isoformat())
        )

    cur.execute(
        "UPDATE portfolios SET cash_balance = cash_balance + ? WHERE preset_name = ?",
        (total_proceeds, preset_name)
    )

    conn.commit()
    conn.close()
    return True, f"매도 완료: 총 {total_proceeds:,.0f}원"


def get_transactions(preset_name):
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM transactions WHERE preset_name = ? ORDER BY timestamp DESC", conn, params=(preset_name,)
    )
    conn.close()
    return df