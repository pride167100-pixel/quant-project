"""
스크리너의 핵심 필터링/랭킹 로직 (Streamlit 비의존).
screener_app.py(실시간 화면)와 backtest_engine.py(백테스터)가 공통으로 재사용한다.
동일한 로직을 두 곳에서 따로 구현하면 결과가 미묘하게 달라질 위험이 있어, 반드시 이 파일을 통해서만 필터링한다.
"""
import pandas as pd

# 저장/불러오기 대상이 되는 모든 조건 키 목록
# (use_key, key, label, 기본사용여부, min, max, 기본값, step, 부등호기호)
CRITERIA_DEFS = [
    ("use_pbr", "pbr", "PBR 이하", True, 0.0, 5.0, 1.0, 0.1, "≤"),
    ("use_per", "per", "PER 이하", True, 0.0, 50.0, 15.0, 1.0, "≤"),
    ("use_roe", "roe", "ROE 이상", True, -20.0, 50.0, 5.0, 1.0, "≥"),
    ("use_debt", "debt", "부채비율 이하", False, 0.0, 500.0, 100.0, 10.0, "≤"),
    ("use_current", "current", "유동비율 이상", False, 0.0, 500.0, 100.0, 10.0, "≥"),
    ("use_rev", "rev", "매출액성장률 이상", False, -50.0, 100.0, 0.0, 5.0, "≥"),
    ("use_op", "op", "영업이익성장률 이상", False, -50.0, 100.0, 10.0, 5.0, "≥"),
    ("use_cap", "cap", "시가총액 이상", True, 0.0, 50000.0, 1000.0, 100.0, "≥"),
    ("use_liquidity", "liquidity", "거래대금 이상", False, 0.0, 1000.0, 5.0, 1.0, "≥"),
    ("use_mom3", "mom3", "3개월수익률 이상", False, -80.0, 300.0, -20.0, 5.0, "≥"),
    ("use_mom6", "mom6", "6개월수익률 이상", False, -80.0, 300.0, -20.0, 5.0, "≥"),
    ("use_mom12", "mom12", "12개월수익률 이상", False, -80.0, 500.0, -20.0, 5.0, "≥"),
]

FILTER_COLUMN_MAP = {
    "pbr": ("PBR", "le"), "per": ("PER", "le"), "roe": ("ROE", "ge"),
    "debt": ("부채비율(%)", "le"), "current": ("유동비율(%)", "ge"),
    "rev": ("매출액성장률(%)", "ge"), "op": ("영업이익성장률(%)", "ge"),
    "cap": ("시가총액", "ge"), "liquidity": ("평균거래대금(억원)", "ge"),
    "mom3": ("3개월수익률(%)", "ge"), "mom6": ("6개월수익률(%)", "ge"), "mom12": ("12개월수익률(%)", "ge"),
}

# 랭킹 모드용 지표 목록: (표시라벨, 컬럼명, "low"=낮을수록좋음/"high"=높을수록좋음)
RANKING_INDICATORS = [
    ("PER (낮을수록 좋음)", "PER", "low"),
    ("PBR (낮을수록 좋음)", "PBR", "low"),
    ("ROE (높을수록 좋음)", "ROE", "high"),
    ("부채비율 (낮을수록 좋음)", "부채비율(%)", "low"),
    ("유동비율 (높을수록 좋음)", "유동비율(%)", "high"),
    ("매출액성장률 (높을수록 좋음)", "매출액성장률(%)", "high"),
    ("영업이익성장률 (높을수록 좋음)", "영업이익성장률(%)", "high"),
    ("3개월수익률 (높을수록 좋음)", "3개월수익률(%)", "high"),
    ("6개월수익률 (높을수록 좋음)", "6개월수익률(%)", "high"),
    ("12개월수익률 (높을수록 좋음)", "12개월수익률(%)", "high"),
]


def filter_stocks(df, criteria):
    """조건 딕셔너리를 데이터프레임에 적용해서 필터링 결과 반환"""
    filtered = df.copy()
    for use_key, key, *_ in CRITERIA_DEFS:
        if criteria.get(use_key):
            col, op = FILTER_COLUMN_MAP[key]
            threshold = criteria.get(f"{key}_slider")
            if threshold is None or col not in filtered.columns:
                continue
            if key == "per":
                filtered = filtered[(filtered[col] <= threshold) & (filtered[col] > 0)]
            elif op == "le":
                filtered = filtered[filtered[col] <= threshold]
            else:
                filtered = filtered[filtered[col] >= threshold]
    if criteria.get("use_3year_profit") and "3년연속흑자" in filtered.columns:
        filtered = filtered[filtered["3년연속흑자"] == True]
    return filtered


def summarize_criteria(criteria):
    """조건을 사람이 읽기 좋은 한 줄로 요약 (비교표 등 간단 표시용)"""
    parts = []
    for use_key, key, label, *_rest in CRITERIA_DEFS:
        sign = _rest[-1]
        if criteria.get(use_key):
            val = criteria.get(f"{key}_slider")
            short_label = label.replace(" 이하", "").replace(" 이상", "")
            parts.append(f"{short_label}{sign}{val}")
    if criteria.get("use_3year_profit"):
        parts.append("3년연속흑자")
    return ", ".join(parts) if parts else "(설정된 조건 없음)"


def summarize_criteria_lines(criteria):
    """조건을 카테고리별로 묶어 여러 줄로 반환 (카드 형태 표시용)"""
    category_map = {
        "가치": ["pbr", "per"],
        "퀄리티": ["roe", "debt", "current"],
        "성장": ["rev", "op"],
        "규모": ["cap", "liquidity"],
        "모멘텀": ["mom3", "mom6", "mom12"],
    }
    lookup = {key: (label, _rest[-1]) for use_key, key, label, *_rest in CRITERIA_DEFS}
    use_lookup = {key: use_key for use_key, key, *_ in CRITERIA_DEFS}

    lines = []
    for category, keys in category_map.items():
        active = []
        for key in keys:
            use_key = use_lookup[key]
            if criteria.get(use_key):
                label, sign = lookup[key]
                val = criteria.get(f"{key}_slider")
                short_label = label.replace(" 이하", "").replace(" 이상", "")
                active.append(f"{short_label} {sign} {val}")
        if category == "성장" and criteria.get("use_3year_profit"):
            active.append("3년연속흑자")
        if active:
            lines.append(f"**{category}**: {' · '.join(active)}")
    return lines if lines else ["(설정된 조건 없음)"]


def rank_stocks(df, selected_labels, top_n, balance_pct=None, sector_cap=None):
    """선택된 지표들로 순위를 매겨 합산순위 기준 상위 N개 반환.

    balance_pct: 지정하면(0~100 사이 숫자), 선택한 지표 '전부' 에서 상위 balance_pct% 안에
        드는 종목만 남긴다(교집합). 한 지표에만 몰빵되어 강한 종목(다른 지표는 나쁨)을
        걸러내고, 여러 지표에서 고르게 준수한 종목만 남기기 위한 필터.
    sector_cap: 지정하면, 합산순위 순서대로 담되 같은 업종명이 이미 이 개수만큼 담겼으면
        건너뛰고 다음 순위로 넘어간다("계란을 한 바구니에 담지 않기" - 업종 쏠림 방지).
        둘 다 지정 안 하면 기존과 동일하게 동작한다.
    """
    label_map = {label: (col, better) for label, col, better in RANKING_INDICATORS}
    selected = [label_map[label] for label in selected_labels]

    if not selected:
        return df.head(0), []

    cols_needed = [col for col, _ in selected]
    ranked = df.dropna(subset=cols_needed).copy()

    rank_cols = []
    for col, better in selected:
        rank_col = f"순위_{col}"
        ranked[rank_col] = ranked[col].rank(method="min", ascending=(better == "low"))
        rank_cols.append(rank_col)

    ranked["합산순위"] = ranked[rank_cols].sum(axis=1)

    if balance_pct is not None and len(ranked) > 0:
        cutoff_rank = max(1, len(ranked) * balance_pct / 100)
        balance_mask = pd.Series(True, index=ranked.index)
        for rank_col in rank_cols:
            balance_mask &= ranked[rank_col] <= cutoff_rank
        ranked = ranked[balance_mask]

    ranked = ranked.sort_values("합산순위")

    if sector_cap is not None and "업종명" in ranked.columns:
        picked_idx = []
        sector_counts = {}
        for idx, row in ranked.iterrows():
            if len(picked_idx) >= top_n:
                break
            sector = row["업종명"]
            if sector_counts.get(sector, 0) >= sector_cap:
                continue
            picked_idx.append(idx)
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
        ranked = ranked.loc[picked_idx]
    else:
        ranked = ranked.head(top_n)

    ranked = ranked.reset_index(drop=True)
    ranked.insert(0, "최종순위", range(1, len(ranked) + 1))
    return ranked, rank_cols