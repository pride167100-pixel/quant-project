"""
백테스트 엔진 - 과거 특정 시점부터 프리셋 조건으로 월별 리밸런싱했다면 어떤 수익률이 나왔을지 계산.
API 호출 없이, 미리 수집해둔 historical_financials.csv / historical_prices.csv / screener_data.csv만으로 계산한다.
"""
import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta

from screener_logic import filter_stocks, rank_stocks
from portfolio_db import BUY_FEE_RATE, SELL_FEE_RATE, SELL_TAX_RATE

BACKTEST_BENCHMARKS = {
    "코스피": "069500",
    "코스닥": "229200",
    "S&P500": "360200",
}


def get_fiscal_year_asof(target_date):
    """이 날짜 시점에 '이미 공시되어 있었을' 가장 최근 사업연도 (4월 1일 공시 근사 규칙)"""
    if target_date.month >= 4:
        return target_date.year - 1
    else:
        return target_date.year - 2


def load_backtest_data():
    """백테스트에 필요한 3개 파일을 미리 로드 (반복 사용을 위해 한 번만)"""
    static_info = pd.read_csv("screener_data.csv", dtype={"종목코드": str})[
        ["종목코드", "종목명", "업종명", "시장구분", "상장주수"]
    ]
    financials = pd.read_csv("historical_financials.csv", dtype={"종목코드": str})
    prices = pd.read_csv("historical_prices.csv", dtype={"종목코드": str})
    prices["날짜"] = pd.to_datetime(prices["날짜"], format="%Y%m%d")
    prices = prices.sort_values(["종목코드", "날짜"]).reset_index(drop=True)
    return static_info, financials, prices


def get_price_asof(prices, stock_code, target_date, tolerance_days=21):
    """특정 종목의 target_date 이전(또는 당일) 가장 가까운 종가를 반환. tolerance_days 넘게 오래된 데이터면 None"""
    sub = prices[(prices["종목코드"] == stock_code) & (prices["날짜"] <= target_date)]
    if sub.empty:
        return None
    last_row = sub.iloc[-1]
    if (target_date - last_row["날짜"]).days > tolerance_days:
        return None
    return last_row["종가"]


def build_price_lookup(prices):
    """종목코드별로 (날짜 오름차순 정렬된) 서브데이터프레임 딕셔너리를 미리 만들어 반복조회 속도 개선"""
    return {code: g[["날짜", "종가", "거래대금"]].reset_index(drop=True)
            for code, g in prices.groupby("종목코드")}


def fast_price_asof(price_lookup, stock_code, target_date, tolerance_days=21):
    sub = price_lookup.get(stock_code)
    if sub is None or sub.empty:
        return None
    idx = sub["날짜"].searchsorted(target_date, side="right") - 1
    if idx < 0:
        return None
    row = sub.iloc[idx]
    if (target_date - row["날짜"]).days > tolerance_days:
        return None
    return row["종가"]


def build_historical_snapshot(target_date, static_info, financials, price_lookup):
    """target_date 시점 기준의 전 종목 스냅샷을 만들어, 실시간 화면과 동일한 컬럼 형태로 반환"""
    Y = get_fiscal_year_asof(target_date)

    fin_cols_needed = [f"매출액_{Y}", f"매출액_{Y-1}", f"영업이익_{Y}", f"영업이익_{Y-1}", f"영업이익_{Y-2}",
                       f"자본총계_{Y}", f"당기순이익_{Y}",
                       f"ROE_{Y}", f"부채비율_{Y}", f"유동비율_{Y}"]
    available_cols = [c for c in fin_cols_needed if c in financials.columns]
    fin_slim = financials[["종목코드"] + available_cols].copy()

    df = static_info.merge(fin_slim, on="종목코드", how="left")

    # 가격 관련 계산
    def calc_row(row):
        code = row["종목코드"]
        price = fast_price_asof(price_lookup, code, target_date)
        if price is None:
            return pd.Series({"현재가": None, "시가총액": None, "PBR": None, "PER": None,
                               "평균거래대금(억원)": None,
                               "3개월수익률(%)": None, "6개월수익률(%)": None, "12개월수익률(%)": None})

        # 주의: screener_data.csv의 '상장주수'는 '천주' 단위이므로 실제 주식수로 환산(×1000) 후 계산
        market_cap = price * row["상장주수"] * 1000 / 1e8  # 억원 단위

        equity = row.get(f"자본총계_{Y}") if f"자본총계_{Y}" in row else None
        net_income = row.get(f"당기순이익_{Y}") if f"당기순이익_{Y}" in row else None

        pbr = (market_cap * 1e8) / equity if equity and equity != 0 else None
        per = (market_cap * 1e8) / net_income if net_income and net_income != 0 else None

        p3 = fast_price_asof(price_lookup, code, target_date - relativedelta(months=3))
        p6 = fast_price_asof(price_lookup, code, target_date - relativedelta(months=6))
        p12 = fast_price_asof(price_lookup, code, target_date - relativedelta(months=12))

        mom3 = round((price - p3) / p3 * 100, 2) if p3 else None
        mom6 = round((price - p6) / p6 * 100, 2) if p6 else None
        mom12 = round((price - p12) / p12 * 100, 2) if p12 else None

        sub = price_lookup.get(code)
        avg_liquidity = None
        if sub is not None and not sub.empty:
            recent = sub[sub["날짜"] <= target_date].tail(12)
            if not recent.empty:
                avg_liquidity = round(recent["거래대금"].mean() / 5 / 1e8, 1)

        return pd.Series({
            "현재가": price, "시가총액": round(market_cap, 1),
            "PBR": round(pbr, 2) if pbr else None, "PER": round(per, 2) if per else None,
            "평균거래대금(억원)": avg_liquidity,
            "3개월수익률(%)": mom3, "6개월수익률(%)": mom6, "12개월수익률(%)": mom12,
        })

    price_derived = df.apply(calc_row, axis=1)
    df = pd.concat([df, price_derived], axis=1)

    # ROE/부채비율/유동비율/성장률은 해당 연도 컬럼명을 표준 이름으로 매핑
    df["ROE"] = df.get(f"ROE_{Y}")
    df["부채비율(%)"] = df.get(f"부채비율_{Y}")
    df["유동비율(%)"] = df.get(f"유동비율_{Y}")

    if f"매출액_{Y}" in df.columns and f"매출액_{Y-1}" in df.columns:
        df["매출액성장률(%)"] = ((df[f"매출액_{Y}"] - df[f"매출액_{Y-1}"]) / df[f"매출액_{Y-1}"].abs() * 100).round(2)
    else:
        df["매출액성장률(%)"] = None

    if f"영업이익_{Y}" in df.columns and f"영업이익_{Y-1}" in df.columns:
        df["영업이익성장률(%)"] = ((df[f"영업이익_{Y}"] - df[f"영업이익_{Y-1}"]) / df[f"영업이익_{Y-1}"].abs() * 100).round(2)
    else:
        df["영업이익성장률(%)"] = None

    if all(f"영업이익_{y}" in df.columns for y in [Y, Y - 1, Y - 2]):
        def check_3y(row):
            vals = [row.get(f"영업이익_{Y}"), row.get(f"영업이익_{Y-1}"), row.get(f"영업이익_{Y-2}")]
            if any(v is None or pd.isna(v) for v in vals):
                return None
            return bool(all(v > 0 for v in vals))
        df["3년연속흑자"] = df.apply(check_3y, axis=1).astype("object")
    else:
        df["3년연속흑자"] = None

    return df


def get_monthly_rebalance_dates(months_back):
    """오늘부터 months_back개월 전까지, 매달 같은 날짜의 리밸런싱 일정을 오름차순으로 반환"""
    today = datetime.now()
    dates = []
    for i in range(months_back, -1, -1):
        dates.append(today - relativedelta(months=i))
    return dates


def run_backtest(criteria, months_back, initial_amount=10_000_000, progress_callback=None,
                  use_ranking=False, ranking_indicators=None, top_n=20):
    """
    criteria: screener_logic 형식의 조건 딕셔너리 (1차 필터로 항상 적용됨)
    months_back: 몇 개월 전부터 시작할지 (3, 6, 12, 24, 36 등)
    use_ranking: True면, 1차 필터 통과 종목 중 랭킹 상위 top_n개만 매달 재선정
    ranking_indicators: rank_stocks에 넘길 지표 라벨 리스트 (screener_logic.RANKING_INDICATORS 참고)
    반환: {"portfolio": [...], "benchmarks": {...}, "final_return": float}
    """
    static_info, financials, prices = load_backtest_data()
    price_lookup = build_price_lookup(prices)
    name_map = dict(zip(static_info["종목코드"], static_info["종목명"]))

    rebalance_dates = get_monthly_rebalance_dates(months_back)
    total_steps = len(rebalance_dates)

    cash = initial_amount
    holdings = {}  # 종목코드 -> 수량
    portfolio_history = []

    for step, target_date in enumerate(rebalance_dates):
        snapshot = build_historical_snapshot(target_date, static_info, financials, price_lookup)
        passing = filter_stocks(snapshot, criteria)

        if use_ranking and ranking_indicators:
            passing, _ = rank_stocks(passing, ranking_indicators, top_n)

        passing_codes = set(passing["종목코드"]) if len(passing) > 0 else set()
        current_codes = set(holdings.keys())

        # 1) 탈락 종목 매도
        to_sell = current_codes - passing_codes
        for code in to_sell:
            price = fast_price_asof(price_lookup, code, target_date)
            if price is None:
                continue
            qty = holdings.pop(code)
            gross = qty * price
            fee = gross * SELL_FEE_RATE
            tax = gross * SELL_TAX_RATE
            cash += gross - fee - tax

        # 2) 신규 통과 종목 매수 (겹치는 종목은 그대로 유지, 매매 없음)
        to_buy = passing_codes - current_codes
        if to_buy and cash > 0:
            price_map = {code: fast_price_asof(price_lookup, code, target_date) for code in to_buy}
            valid_codes = [c for c in to_buy if price_map[c] and price_map[c] > 0]
            if valid_codes:
                per_stock_amount = cash / len(valid_codes)
                for code in valid_codes:
                    price = price_map[code]
                    amount_after_fee = per_stock_amount / (1 + BUY_FEE_RATE)
                    qty = int(amount_after_fee // price)
                    if qty > 0:
                        cost = qty * price
                        fee = cost * BUY_FEE_RATE
                        cash -= (cost + fee)
                        holdings[code] = holdings.get(code, 0) + qty

        # 3) 이 시점 포트폴리오 평가금액 계산
        total_value = cash
        for code, qty in holdings.items():
            price = fast_price_asof(price_lookup, code, target_date)
            if price:
                total_value += qty * price

        held_names = ", ".join(f"{name_map.get(c, c)}({c})" for c in sorted(holdings.keys())) if holdings else ""
        portfolio_history.append({
            "날짜": target_date, "총자산": total_value, "현금": cash, "보유종목수": len(holdings),
            "보유종목": held_names
        })

        if progress_callback:
            progress_callback(step + 1, total_steps)

    # 벤치마크 계산 (매매 없이 그대로 보유)
    benchmark_results = {}
    for name, code in BACKTEST_BENCHMARKS.items():
        start_price = fast_price_asof(price_lookup, code, rebalance_dates[0])
        series = []
        for target_date in rebalance_dates:
            price = fast_price_asof(price_lookup, code, target_date)
            if start_price and price:
                value = initial_amount * (price / start_price)
            else:
                value = None
            series.append({"날짜": target_date, "총자산": value})
        benchmark_results[name] = series

    final_value = portfolio_history[-1]["총자산"] if portfolio_history else initial_amount
    final_return = (final_value - initial_amount) / initial_amount * 100

    return {
        "portfolio": portfolio_history,
        "benchmarks": benchmark_results,
        "final_return": final_return,
        "initial_amount": initial_amount,
        "final_value": final_value,
    }