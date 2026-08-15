import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "portfolio.db"

# 거래비용 (참고용 근사치 - 실제 증권사/시기별로 다를 수 있으니 필요시 조정하세요)
BUY_FEE_RATE = 0.00015   # 매수 수수료 약 0.015%
SELL_FEE_RATE = 0.00015  # 매도 수수료 약 0.015%
SELL_TAX_RATE = 0.0015   # 매도 시 증권거래세 약 0.15% (코스피/코스닥 근사치, 최신 세율은 별도 확인 권장)


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

    # 기존에 만들어진 DB에도 fee/tax 컬럼을 안전하게 추가 (이미 있으면 에러 무시)
    for column_def in ["fee REAL DEFAULT 0", "tax REAL DEFAULT 0"]:
        try:
            cur.execute(f"ALTER TABLE transactions ADD COLUMN {column_def}")
        except sqlite3.OperationalError:
            pass  # 이미 컬럼이 존재하는 경우

    # 리밸런싱 확정 시점 기록용 컬럼 (기존 DB에도 안전하게 추가)
    try:
        cur.execute("ALTER TABLE portfolios ADD COLUMN last_rebalanced_at TEXT")
    except sqlite3.OperationalError:
        pass  # 이미 컬럼이 존재하는 경우

    cur.execute("""
        CREATE TABLE IF NOT EXISTS funding_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            preset_name TEXT NOT NULL,
            event_date TEXT NOT NULL,
            amount REAL NOT NULL,
            event_type TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS benchmark_events (
            preset_name TEXT NOT NULL,
            event_date TEXT NOT NULL,
            benchmark_name TEXT NOT NULL,
            price REAL,
            PRIMARY KEY (preset_name, event_date, benchmark_name)
        )
    """)

    conn.commit()
    conn.close()


def add_funding_event(preset_name, event_date, amount, event_type):
    """자금 투입 이벤트(최초매수 또는 추가입금) 기록"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO funding_events (preset_name, event_date, amount, event_type) VALUES (?, ?, ?, ?)",
        (preset_name, event_date, amount, event_type)
    )
    conn.commit()
    conn.close()


def get_funding_events(preset_name):
    """이 프리셋의 모든 자금 투입 이벤트를 [{event_date, amount, event_type}] 형태로 반환"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT event_date, amount, event_type FROM funding_events WHERE preset_name = ? ORDER BY event_date ASC",
        (preset_name,)
    )
    result = [dict(row) for row in cur.fetchall()]
    conn.close()
    return result


def save_benchmark_event_prices(preset_name, event_date, benchmark_prices):
    """특정 투입 시점의 벤치마크 가격 저장 (이미 있으면 건드리지 않음)"""
    conn = get_connection()
    cur = conn.cursor()
    for name, price in benchmark_prices.items():
        if price is None:
            continue
        cur.execute(
            "INSERT OR IGNORE INTO benchmark_events (preset_name, event_date, benchmark_name, price) "
            "VALUES (?, ?, ?, ?)",
            (preset_name, event_date, name, price)
        )
    conn.commit()
    conn.close()


def get_benchmark_event_prices(preset_name, event_date):
    """특정 투입 시점의 벤치마크 가격을 {이름: 가격}으로 반환"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT benchmark_name, price FROM benchmark_events WHERE preset_name = ? AND event_date = ?",
        (preset_name, event_date)
    )
    result = {row["benchmark_name"]: row["price"] for row in cur.fetchall()}
    conn.close()
    return result


def add_deposit(preset_name, amount):
    """프리셋에 추가 자금을 입금 (초기자본/현금잔고 모두 증가, 이벤트 기록)"""
    from datetime import date
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE portfolios SET initial_cash = initial_cash + ?, cash_balance = cash_balance + ? WHERE preset_name = ?",
        (amount, amount, preset_name)
    )
    conn.commit()
    conn.close()
    add_funding_event(preset_name, date.today().isoformat(), amount, "DEPOSIT")
    return True, f"{amount:,.0f}원 입금 완료"


def delete_preset(preset_name):
    """프리셋과 관련된 모든 데이터(조건, 포트폴리오, 보유종목, 거래내역, 벤치마크)를 삭제"""
    conn = get_connection()
    cur = conn.cursor()
    for table in ["preset_criteria", "portfolios", "holdings", "transactions",
                  "funding_events", "benchmark_events"]:
        cur.execute(f"DELETE FROM {table} WHERE preset_name = ?", (preset_name,))
    conn.commit()
    conn.close()


def rename_preset(old_name, new_name):
    """프리셋 이름을 바꾼다. preset_name이 여러 테이블의 기본키/외래키처럼 쓰이고 있어서,
    조건·포트폴리오·보유종목·거래내역·벤치마크 기록 전부 한 번에 같이 바꿔줘야 한다."""
    new_name = new_name.strip()
    if not new_name:
        return False, "새 이름을 입력해주세요."
    if new_name == old_name:
        return False, "기존 이름과 같습니다."
    if new_name in list_presets():
        return False, f"'{new_name}' 이름은 이미 사용 중입니다."

    conn = get_connection()
    cur = conn.cursor()
    for table in ["preset_criteria", "portfolios", "holdings", "transactions",
                  "funding_events", "benchmark_events"]:
        cur.execute(f"UPDATE {table} SET preset_name = ? WHERE preset_name = ?", (new_name, old_name))
    conn.commit()
    conn.close()
    return True, f"'{old_name}' → '{new_name}'(으)로 이름을 변경했습니다."


def duplicate_preset_criteria(source_name, new_name, initial_cash=10_000_000):
    """조건만 복사해서 새 프리셋 생성 (보유종목/거래내역/벤치마크는 복사하지 않음, 시드머니는 초기화)"""
    import json
    criteria = load_preset_criteria(source_name)
    if criteria is None:
        return False, "원본 프리셋의 조건을 찾을 수 없습니다."

    save_preset_criteria(new_name, criteria)
    get_or_create_portfolio(new_name, initial_cash=initial_cash)
    return True, f"'{new_name}' 생성 완료 (조건만 복사, 시드머니 {initial_cash:,.0f}원으로 새로 시작)"


def generate_copy_name(source_name):
    """기존 프리셋 이름 목록과 겹치지 않는 '(1)', '(2)'... 형태의 이름을 생성"""
    existing = set(list_presets())
    n = 1
    while True:
        candidate = f"{source_name} ({n})"
        if candidate not in existing:
            return candidate
        n += 1


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
        result = {"preset_name": preset_name, "initial_cash": initial_cash, "cash_balance": initial_cash,
                   "last_rebalanced_at": None}
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

    gross_cost = sum(o["quantity"] * o["price"] for o in orders)
    buy_fee = gross_cost * BUY_FEE_RATE
    total_cost = gross_cost + buy_fee

    cur.execute("SELECT cash_balance FROM portfolios WHERE preset_name = ?", (preset_name,))
    row = cur.fetchone()
    cash_balance = row["cash_balance"] if row else 0

    if total_cost > cash_balance:
        conn.close()
        return False, f"현금 부족: 필요 {total_cost:,.0f}원(수수료 포함), 보유 현금 {cash_balance:,.0f}원"

    for o in orders:
        cur.execute(
            "SELECT quantity, avg_buy_price FROM holdings WHERE preset_name = ? AND stock_code = ?",
            (preset_name, o["stock_code"])
        )
        existing = cur.fetchone()

        # 종목별 수수료 배분 (매입금액 비중대로)
        order_amount = o["quantity"] * o["price"]
        order_fee = order_amount * BUY_FEE_RATE
        # 평균매입가에는 수수료까지 포함해 반영 (실제 원가 기준)
        effective_price = o["price"] + (order_fee / o["quantity"] if o["quantity"] else 0)

        if existing:
            new_qty = existing["quantity"] + o["quantity"]
            new_avg = (existing["quantity"] * existing["avg_buy_price"] + o["quantity"] * effective_price) / new_qty
            cur.execute(
                "UPDATE holdings SET quantity = ?, avg_buy_price = ? WHERE preset_name = ? AND stock_code = ?",
                (new_qty, new_avg, preset_name, o["stock_code"])
            )
        else:
            cur.execute(
                "INSERT INTO holdings (preset_name, stock_code, stock_name, quantity, avg_buy_price) VALUES (?, ?, ?, ?, ?)",
                (preset_name, o["stock_code"], o["stock_name"], o["quantity"], effective_price)
            )

        cur.execute(
            "INSERT INTO transactions (preset_name, stock_code, stock_name, action, quantity, price, amount, fee, tax, timestamp) "
            "VALUES (?, ?, ?, 'BUY', ?, ?, ?, ?, 0, ?)",
            (preset_name, o["stock_code"], o["stock_name"], o["quantity"], o["price"],
             order_amount, order_fee, datetime.now().isoformat())
        )

    cur.execute(
        "UPDATE portfolios SET cash_balance = cash_balance - ? WHERE preset_name = ?",
        (total_cost, preset_name)
    )

    conn.commit()
    conn.close()

    # 이 프리셋의 최초 매수라면, 초기자본 전체를 하나의 자금투입 이벤트로 기록 (벤치마크 비교용)
    from datetime import date
    existing_events = get_funding_events(preset_name)
    if not any(e["event_type"] == "INITIAL" for e in existing_events):
        portfolio = get_or_create_portfolio(preset_name)
        add_funding_event(preset_name, date.today().isoformat(), portfolio["initial_cash"], "INITIAL")

    return True, f"매수 완료: 총 {total_cost:,.0f}원 (수수료 {buy_fee:,.0f}원 포함)"


def sell_stocks(preset_name, sell_orders):
    """sell_orders: list of dict {stock_code, stock_name, price} - 전량 매도"""
    conn = get_connection()
    cur = conn.cursor()

    total_net_proceeds = 0
    total_fee = 0
    total_tax = 0

    for o in sell_orders:
        cur.execute(
            "SELECT quantity FROM holdings WHERE preset_name = ? AND stock_code = ?",
            (preset_name, o["stock_code"])
        )
        existing = cur.fetchone()
        if not existing:
            continue

        qty = existing["quantity"]
        gross_proceeds = qty * o["price"]
        fee = gross_proceeds * SELL_FEE_RATE
        tax = gross_proceeds * SELL_TAX_RATE
        net_proceeds = gross_proceeds - fee - tax

        total_net_proceeds += net_proceeds
        total_fee += fee
        total_tax += tax

        cur.execute(
            "DELETE FROM holdings WHERE preset_name = ? AND stock_code = ?",
            (preset_name, o["stock_code"])
        )

        cur.execute(
            "INSERT INTO transactions (preset_name, stock_code, stock_name, action, quantity, price, amount, fee, tax, timestamp) "
            "VALUES (?, ?, ?, 'SELL', ?, ?, ?, ?, ?, ?)",
            (preset_name, o["stock_code"], o["stock_name"], qty, o["price"], gross_proceeds, fee, tax,
             datetime.now().isoformat())
        )

    cur.execute(
        "UPDATE portfolios SET cash_balance = cash_balance + ? WHERE preset_name = ?",
        (total_net_proceeds, preset_name)
    )

    conn.commit()
    conn.close()
    return True, (f"매도 완료: 실수령액 {total_net_proceeds:,.0f}원 "
                  f"(수수료 {total_fee:,.0f}원 + 거래세 {total_tax:,.0f}원 차감)")


def mark_rebalanced(preset_name):
    """리밸런싱을 확정 실행한 시각을 기록 (화면에 '마지막 리밸런싱 N일 경과' 표시용)"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE portfolios SET last_rebalanced_at = ? WHERE preset_name = ?",
        (datetime.now().isoformat(), preset_name)
    )
    conn.commit()
    conn.close()


def backfill_initial_funding_event(preset_name):
    """funding_events가 비어있는데 과거 거래내역(transactions)이 있으면, 그 최초 매수일로 INITIAL 이벤트를 소급 생성"""
    existing = get_funding_events(preset_name)
    if existing:
        return existing  # 이미 있으면 그대로 반환

    earliest_date = get_earliest_buy_date(preset_name)
    if earliest_date is None:
        return []  # 매수 이력 자체가 없음

    portfolio = get_or_create_portfolio(preset_name)
    add_funding_event(preset_name, earliest_date, portfolio["initial_cash"], "INITIAL")
    return get_funding_events(preset_name)


def get_earliest_buy_date(preset_name):
    """이 프리셋의 첫 매수 거래 날짜(YYYY-MM-DD)를 반환. 매수 이력이 없으면 None"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT timestamp FROM transactions WHERE preset_name = ? AND action = 'BUY' "
        "ORDER BY timestamp ASC LIMIT 1",
        (preset_name,)
    )
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    return row["timestamp"][:10]  # YYYY-MM-DD 부분만


def get_transactions(preset_name):
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM transactions WHERE preset_name = ? ORDER BY timestamp DESC", conn, params=(preset_name,)
    )
    conn.close()
    return df