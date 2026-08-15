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
    """백테스트에 필요한 파일들을 미리 로드 (반복 사용을 위해 한 번만)"""
    static_info = pd.read_csv("screener_data.csv", dtype={"종목코드": str})[
        ["종목코드", "종목명", "업종명", "시장구분", "상장주수"]
    ]
    financials = pd.read_csv("historical_financials.csv", dtype={"종목코드": str})
    prices = pd.read_csv("historical_prices.csv", dtype={"종목코드": str})
    prices["날짜"] = pd.to_datetime(prices["날짜"], format="%Y%m%d")
    prices = prices.sort_values(["종목코드", "날짜"]).reset_index(drop=True)

    try:
        timeline = pd.read_csv("financial_timeline.csv", dtype={"종목코드": str})
        timeline["공시일_추정"] = pd.to_datetime(timeline["공시일_추정"])
        timeline = timeline.sort_values("공시일_추정").reset_index(drop=True)
    except FileNotFoundError:
        timeline = None  # 없으면 예전 방식(연간 근사)으로 자동 대체

    return static_info, financials, prices, timeline


def get_price_asof(prices, stock_code, target_date, tolerance_days=21):
    """특정 종목의 target_date 이전(또는 당일) 가장 가까운 종가를 반환. tolerance_days 넘게 오래된 데이터면 None
    (단일 종목 조회용. 대량 조회는 merge_asof_prices()가 훨씬 빠름)"""
    sub = prices[(prices["종목코드"] == stock_code) & (prices["날짜"] <= target_date)]
    if sub.empty:
        return None
    last_row = sub.iloc[-1]
    if (target_date - last_row["날짜"]).days > tolerance_days:
        return None
    return last_row["종가"]


def build_price_lookup(prices):
    """종목코드별로 (날짜 오름차순 정렬된) 서브데이터프레임 딕셔너리를 미리 만듦 (벤치마크 등 단건 조회용)"""
    return {code: g[["날짜", "종가", "거래대금"]].reset_index(drop=True)
            for code, g in prices.groupby("종목코드")}


def fast_price_asof(price_lookup, stock_code, target_date, tolerance_days=21):
    """단일 종목 조회용 (벤치마크처럼 종목이 몇 개 안 될 때 사용)"""
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


def fast_price_asof_with_fallback(price_lookup, stock_code, target_date, tolerance_days=21):
    """fast_price_asof와 같지만, tolerance_days를 넘겨서 최신성 기준에는 못 미쳐도
    그 종목의 가격 데이터 자체는 있는 경우 '마지막으로 알려진 가격'을 대신 반환한다.
    (원래는 tolerance 초과 시 그냥 None을 반환했는데, 그러면 호출부에서 그 종목의
    평가금액이 통째로 누락돼버려서 - 데이터가 오래됐을 뿐인데 - 자산이 증발한 것처럼
    보이는 문제가 있었음. 종목의 가격 이력 자체가 전혀 없을 때만 None을 반환한다.)
    반환값: (가격 또는 None, 오래된_데이터로_대체했는지 여부)"""
    price = fast_price_asof(price_lookup, stock_code, target_date, tolerance_days)
    if price is not None:
        return price, False
    sub = price_lookup.get(stock_code)
    if sub is None or sub.empty:
        return None, False
    idx = sub["날짜"].searchsorted(target_date, side="right") - 1
    if idx < 0:
        return None, False
    return sub.iloc[idx]["종가"], True


def prepare_prices_for_vectorized(prices):
    """merge_asof 벡터화 조회를 위해 가격 데이터를 준비.
    종목별 최근 12주 평균거래대금(유동성)도 여기서 한 번만 미리 계산해둔다 (매번 재계산하면 느림)."""
    prices = prices.sort_values(["종목코드", "날짜"]).copy()
    prices["평균거래대금(억원)"] = (
        prices.groupby("종목코드")["거래대금"]
        .transform(lambda s: s.rolling(12, min_periods=1).mean())
        / 5 / 1e8
    )
    # merge_asof는 전체가 '날짜' 기준 오름차순 정렬되어 있어야 함
    return prices.sort_values("날짜").reset_index(drop=True)


def merge_asof_prices(stock_codes, target_date, prices_sorted, value_cols=("종가",), tolerance_days=21):
    """여러 종목의 target_date 시점 값을 한 번에(벡터로) 조회. 반복문 없이 처리해서 훨씬 빠름.
    tolerance_days=None이면 최신성 기준 없이 그냥 마지막으로 알려진 값을 씀."""
    target_df = pd.DataFrame({"종목코드": stock_codes, "__date__": target_date})
    merge_kwargs = dict(left_on="__date__", right_on="날짜", by="종목코드", direction="backward")
    if tolerance_days is not None:
        merge_kwargs["tolerance"] = pd.Timedelta(days=tolerance_days)
    result = pd.merge_asof(
        target_df, prices_sorted[["종목코드", "날짜"] + list(value_cols)], **merge_kwargs
    )
    return result[list(value_cols)]


def merge_asof_prices_with_fallback(stock_codes, target_date, prices_sorted, value_cols=("종가",), tolerance_days=21):
    """merge_asof_prices와 같지만, tolerance_days를 넘겨서 최신성 기준에는 못 미쳐도
    그 종목의 가격 데이터 자체는 있으면(상장폐지 등이 아니라 그냥 수집이 밀린 것뿐이면)
    마지막으로 알려진 값을 대신 채워 넣는다. 데이터 수집이 며칠~몇 주 밀린 날에도
    전종목 스냅샷 자체가 통째로 비어버리는(→ 필터링 결과 0종목) 문제를 막기 위함.
    반환: (값 DataFrame, 오래된 데이터로 대체된 행 수)"""
    fresh = merge_asof_prices(stock_codes, target_date, prices_sorted, value_cols, tolerance_days)
    fallback = merge_asof_prices(stock_codes, target_date, prices_sorted, value_cols, tolerance_days=None)
    is_stale = fresh[value_cols[0]].isna() & fallback[value_cols[0]].notna()
    result = fresh.copy()
    for col in value_cols:
        result[col] = fresh[col].where(~is_stale, fallback[col])
    return result, int(is_stale.sum())


def merge_asof_timeline(stock_codes, target_date, timeline_sorted, tolerance_days=200):
    """각 종목의 target_date 시점까지 '이미 공시된' 가장 최근 재무 실적을 한 번에(벡터로) 조회.
    tolerance_days는 넉넉하게 잡음(연간보고서 발표 주기가 1년에 가까워서, 그 안에 최근 분기 실적이 있으면 됨)"""
    value_cols = ["부채총계", "자본총계", "유동자산", "유동부채",
                  "TTM_매출액", "TTM_영업이익", "TTM_당기순이익",
                  "매출액성장률(%)", "영업이익성장률(%)"]
    target_df = pd.DataFrame({"종목코드": stock_codes, "__date__": target_date})
    result = pd.merge_asof(
        target_df, timeline_sorted[["종목코드", "공시일_추정"] + value_cols],
        left_on="__date__", right_on="공시일_추정", by="종목코드",
        direction="backward", tolerance=pd.Timedelta(days=tolerance_days)
    )
    return result[value_cols]


def build_historical_snapshot(target_date, static_info, financials, prices_sorted, timeline_sorted=None):
    """target_date 시점 기준의 전 종목 스냅샷을 만들어, 실시간 화면과 동일한 컬럼 형태로 반환.
    (merge_asof로 전 종목을 한 번에 조회하는 벡터화 버전 - 반복문 버전보다 훨씬 빠름)
    timeline_sorted가 있으면(분기별 정밀데이터) 그걸로 ROE/PBR/PER/성장률을 정밀 계산하고,
    없으면 예전 방식(연간 근사, 4월1일 공시 규칙)으로 자동 대체한다."""
    Y = get_fiscal_year_asof(target_date)

    fin_cols_needed = [f"영업이익_{Y}", f"영업이익_{Y-1}", f"영업이익_{Y-2}"]
    available_cols = [c for c in fin_cols_needed if c in financials.columns]
    fin_slim = financials[["종목코드"] + available_cols].copy()

    df = static_info.merge(fin_slim, on="종목코드", how="left").reset_index(drop=True)
    codes = df["종목코드"]

    # 현재가 + 유동성(12주 평균거래대금) - 한 번의 벡터 조회로 전 종목 처리
    # tolerance_days(21일)를 넘겨서 데이터가 밀려있어도, 그 종목 가격 이력 자체는 있으면
    # 마지막으로 알려진 값을 씀 (안 그러면 데이터 수집이 며칠만 밀려도 전종목 현재가가
    # 통째로 NaN이 되어 필터링 결과가 0종목으로 나오는 문제가 있었음)
    current, _ = merge_asof_prices_with_fallback(codes, target_date, prices_sorted, value_cols=("종가", "평균거래대금(억원)"))
    df["현재가"] = current["종가"]
    df["평균거래대금(억원)"] = current["평균거래대금(억원)"].round(1)

    # 3/6/12개월 전 가격도 각각 한 번씩의 벡터 조회로 처리 (반복문 없음)
    p3 = merge_asof_prices(codes, target_date - relativedelta(months=3), prices_sorted, value_cols=("종가",))["종가"]
    p6 = merge_asof_prices(codes, target_date - relativedelta(months=6), prices_sorted, value_cols=("종가",))["종가"]
    p12 = merge_asof_prices(codes, target_date - relativedelta(months=12), prices_sorted, value_cols=("종가",))["종가"]

    df["3개월수익률(%)"] = ((df["현재가"] - p3) / p3 * 100).round(2)
    df["6개월수익률(%)"] = ((df["현재가"] - p6) / p6 * 100).round(2)
    df["12개월수익률(%)"] = ((df["현재가"] - p12) / p12 * 100).round(2)

    # 주의: screener_data.csv의 '상장주수'는 '천주' 단위이므로 실제 주식수로 환산(×1000) 후 계산
    df["시가총액"] = (df["현재가"] * df["상장주수"] * 1000 / 1e8).round(1)

    if timeline_sorted is not None:
        # ── 분기별 정밀 데이터 사용 (TTM 기준) ──
        fin = merge_asof_timeline(codes, target_date, timeline_sorted)

        equity_safe = fin["자본총계"].replace(0, np.nan)
        net_income_safe = fin["TTM_당기순이익"].replace(0, np.nan)

        df["PBR"] = ((df["시가총액"] * 1e8) / equity_safe).round(2)
        df["PER"] = ((df["시가총액"] * 1e8) / net_income_safe).round(2)
        df["ROE"] = (fin["TTM_당기순이익"] / equity_safe * 100).round(2)
        df["부채비율(%)"] = (fin["부채총계"] / equity_safe * 100).round(2)
        df["유동비율(%)"] = (fin["유동자산"] / fin["유동부채"].replace(0, np.nan) * 100).round(2)
        df["매출액성장률(%)"] = fin["매출액성장률(%)"]
        df["영업이익성장률(%)"] = fin["영업이익성장률(%)"]
    else:
        # ── 예전 방식(연간 근사, 데이터 없을 때 대체) ──
        fin_cols_needed2 = [f"매출액_{Y}", f"매출액_{Y-1}", f"자본총계_{Y}", f"당기순이익_{Y}",
                             f"ROE_{Y}", f"부채비율_{Y}", f"유동비율_{Y}"]
        available2 = [c for c in fin_cols_needed2 if c in financials.columns]
        fin_slim2 = financials[["종목코드"] + available2].copy()
        df = df.merge(fin_slim2, on="종목코드", how="left")

        equity_col = f"자본총계_{Y}"
        net_income_col = f"당기순이익_{Y}"
        if equity_col in df.columns:
            equity_safe = df[equity_col].replace(0, np.nan)
            df["PBR"] = ((df["시가총액"] * 1e8) / equity_safe).round(2)
        else:
            df["PBR"] = None
        if net_income_col in df.columns:
            net_income_safe = df[net_income_col].replace(0, np.nan)
            df["PER"] = ((df["시가총액"] * 1e8) / net_income_safe).round(2)
        else:
            df["PER"] = None

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
        cols = [f"영업이익_{Y}", f"영업이익_{Y-1}", f"영업이익_{Y-2}"]
        all_present = df[cols].notna().all(axis=1)
        all_positive = (df[cols] > 0).all(axis=1)
        df["3년연속흑자"] = pd.Series(
            [bool(p) if present else None for present, p in zip(all_present, all_positive)],
            index=df.index, dtype="object"
        )
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
    static_info, financials, prices, timeline = load_backtest_data()
    prices_sorted = prepare_prices_for_vectorized(prices)  # 전종목 스냅샷용 (벡터화, 빠름)
    price_lookup = build_price_lookup(prices)  # 보유/매매 종목처럼 소수 종목 조회용
    name_map = dict(zip(static_info["종목코드"], static_info["종목명"]))

    rebalance_dates = get_monthly_rebalance_dates(months_back)
    total_steps = len(rebalance_dates)

    # 이 백테스트에서 실제로 쓸 수 있는 가격 데이터가 가장 최근 어디까지인지 (화면 경고용)
    data_latest_price_date = prices["날짜"].max() if len(prices) else None

    cash = initial_amount
    holdings = {}  # 종목코드 -> 수량
    portfolio_history = []

    for step, target_date in enumerate(rebalance_dates):
        snapshot = build_historical_snapshot(target_date, static_info, financials, prices_sorted, timeline)
        passing = filter_stocks(snapshot, criteria)

        if use_ranking and ranking_indicators:
            passing, _ = rank_stocks(passing, ranking_indicators, top_n)

        passing_codes = set(passing["종목코드"]) if len(passing) > 0 else set()
        current_codes = set(holdings.keys())
        stale_codes_this_step = set()

        # 1) 탈락 종목 매도
        to_sell = current_codes - passing_codes
        for code in to_sell:
            price, is_stale = fast_price_asof_with_fallback(price_lookup, code, target_date)
            if price is None:
                continue
            if is_stale:
                stale_codes_this_step.add(code)
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
            price, is_stale = fast_price_asof_with_fallback(price_lookup, code, target_date)
            if price:
                total_value += qty * price
                if is_stale:
                    stale_codes_this_step.add(code)

        held_names = ", ".join(f"{name_map.get(c, c)}({c})" for c in sorted(holdings.keys())) if holdings else ""
        portfolio_history.append({
            "날짜": target_date, "총자산": total_value, "현금": cash, "보유종목수": len(holdings),
            "보유종목": held_names,
            "오래된가격_종목수": len(stale_codes_this_step),
        })

        if progress_callback:
            progress_callback(step + 1, total_steps)

    # 벤치마크 계산 (매매 없이 그대로 보유)
    benchmark_results = {}
    for name, code in BACKTEST_BENCHMARKS.items():
        start_price, _ = fast_price_asof_with_fallback(price_lookup, code, rebalance_dates[0])
        series = []
        for target_date in rebalance_dates:
            price, _ = fast_price_asof_with_fallback(price_lookup, code, target_date)
            if start_price and price:
                value = initial_amount * (price / start_price)
            else:
                value = None
            series.append({"날짜": target_date, "총자산": value})
        benchmark_results[name] = series

    final_value = portfolio_history[-1]["총자산"] if portfolio_history else initial_amount
    final_return = (final_value - initial_amount) / initial_amount * 100

    # 마지막 시점 기준 가격 데이터가 며칠이나 오래됐는지 (화면 경고용)
    data_staleness_days = None
    if data_latest_price_date is not None and rebalance_dates:
        data_staleness_days = (rebalance_dates[-1] - data_latest_price_date).days

    return {
        "portfolio": portfolio_history,
        "benchmarks": benchmark_results,
        "final_return": final_return,
        "initial_amount": initial_amount,
        "final_value": final_value,
        "data_latest_price_date": data_latest_price_date,
        "data_staleness_days": data_staleness_days,
        "months_back": months_back,
    }