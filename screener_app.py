import streamlit as st
import pandas as pd
import json
import portfolio_db as db
import kis_realtime as kis
import benchmark_prices as bp
from benchmark_config import BENCHMARK_ETFS

db.init_db()

st.set_page_config(page_title="퀀트 스크리너", layout="wide")

# ── 지표 설명 (도움말 툴팁용) ──────────────────────────────
HELP_TEXT = {
    "pbr": "주가가 회사의 순자산(장부가치) 대비 몇 배로 거래되는지 나타냅니다.\n\n"
           "**낮을수록 저평가**로 봅니다. 1 이하면 회사가 가진 자산보다 싸게 거래된다는 뜻입니다.",
    "per": "주가가 회사의 연간 순이익 대비 몇 배인지 나타냅니다.\n\n"
           "**낮을수록 저평가**로 봅니다. 단, 너무 낮으면 시장이 그 회사 실적을 불신하고 있다는 신호일 수도 있습니다.",
    "roe": "회사가 자기 자본으로 얼마나 효율적으로 돈을 버는지(%) 나타냅니다.\n\n"
           "**높을수록 좋습니다.** 다만 부채가 과도해서 ROE가 인위적으로 높아진 경우도 있어 부채비율과 함께 보는 것이 안전합니다.",
    "debt_ratio": "부채총계를 자본총계로 나눈 값(%)입니다.\n\n**낮을수록** 재무적으로 안전합니다. "
                  "100% 이하면 자기자본이 부채보다 많다는 뜻으로 일반적으로 안전한 수준입니다.",
    "current_ratio": "유동자산을 유동부채로 나눈 값(%)입니다.\n\n**높을수록** 단기 지급능력이 좋습니다. "
                      "보통 100% 이상이면 1년 내 갚아야 할 빚을 감당할 자산이 충분하다는 뜻입니다.",
    "rev_growth": "작년 대비 매출이 얼마나 늘었는지(%) 나타냅니다.\n\n**높을수록** 성장하는 회사입니다.",
    "op_growth": "작년 대비 영업이익이 얼마나 늘었는지(%) 나타냅니다.\n\n"
                 "**높을수록 좋으나**, 기저효과(작년이 유난히 안 좋았던 경우)로 왜곡될 수 있습니다.",
    "cap": "회사 전체 가치(주가 × 발행주식수)를 나타냅니다.\n\n"
           "**너무 작으면** 거래량이 적어 매매 자체가 어렵거나 가격 변동이 심할 위험이 있습니다.",
    "mom_3m": "최근 3개월간 주가 변동률(%)입니다.\n\n"
              "단기 추세를 봅니다. 너무 낮으면(급락) 저평가 지표가 좋아 보여도 실제로는 악재가 있는 "
              "'밸류 트랩'일 위험이 있습니다.",
    "mom_6m": "최근 6개월간 주가 변동률(%)입니다.\n\n단기 소음은 줄이면서 중기 추세를 확인할 때 유용합니다.",
    "mom_12m": "최근 12개월간 주가 변동률(%)입니다.\n\n"
               "학계에서 가장 많이 검증된 전통적 모멘텀 기간입니다. 꾸준한 상승 추세인 종목을 찾을 때 참고합니다.",
    "liquidity": "최근 12주 평균 일별 거래대금(억원)입니다.\n\n"
                 "**너무 작으면** 원하는 가격에 매수/매도가 어려울 수 있습니다 (유동성 위험).",
}

# 저장/불러오기 대상이 되는 모든 조건 위젯 키 목록
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

# 랭킹 모드에서 사용할 지표 목록: (표시라벨, 실제컬럼명, "low"=낮을수록좋음/"high"=높을수록좋음)
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


def sync_from_slider(key):
    st.session_state[f"{key}_num"] = st.session_state[f"{key}_slider"]

def sync_from_number(key):
    st.session_state[f"{key}_slider"] = st.session_state[f"{key}_num"]


def linked_control(label, key, min_v, max_v, default, step, help_text=None):
    if f"{key}_slider" not in st.session_state:
        st.session_state[f"{key}_slider"] = default
        st.session_state[f"{key}_num"] = default

    col1, col2 = st.columns([3, 1])
    with col1:
        st.slider(label, min_v, max_v, key=f"{key}_slider", step=step,
                   on_change=sync_from_slider, args=(key,), help=help_text)
    with col2:
        st.number_input(" ", min_v, max_v, key=f"{key}_num", step=step,
                         on_change=sync_from_number, args=(key,), label_visibility="collapsed")

    return st.session_state[f"{key}_slider"]


def gather_current_criteria():
    """현재 위젯 상태를 저장 가능한 딕셔너리로 수집"""
    result = {}
    for use_key, key, *_ in CRITERIA_DEFS:
        result[use_key] = st.session_state.get(use_key, False)
        result[f"{key}_slider"] = st.session_state.get(f"{key}_slider")
    result["use_3year_profit"] = st.session_state.get("use_3year_profit", False)
    return result


def apply_criteria_to_state(criteria):
    """불러온 조건을 위젯 상태에 반영 (위젯 생성 전에 호출되어야 함)"""
    for use_key, key, *_ in CRITERIA_DEFS:
        if use_key in criteria:
            st.session_state[use_key] = criteria[use_key]
        if f"{key}_slider" in criteria and criteria[f"{key}_slider"] is not None:
            st.session_state[f"{key}_slider"] = criteria[f"{key}_slider"]
            st.session_state[f"{key}_num"] = criteria[f"{key}_slider"]
    if "use_3year_profit" in criteria:
        st.session_state["use_3year_profit"] = criteria["use_3year_profit"]


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


def rank_stocks(df, selected_labels, top_n):
    """선택된 지표들로 순위를 매겨 합산순위 기준 상위 N개 반환"""
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
    ranked = ranked.sort_values("합산순위").head(top_n).reset_index(drop=True)
    ranked.insert(0, "최종순위", range(1, len(ranked) + 1))
    return ranked, rank_cols


def format_currency_cols(view_df, cols):
    """지정한 컬럼들을 천단위 콤마가 붙은 문자열로 변환 (표시 전용)"""
    view_df = view_df.copy()
    for c in cols:
        if c in view_df.columns:
            view_df[c] = view_df[c].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else x)
    return view_df


import os
from datetime import datetime


def get_data_timestamp():
    """screener_data.csv가 마지막으로 갱신된 시각을 반환"""
    try:
        mtime = os.path.getmtime("screener_data.csv")
        dt = datetime.fromtimestamp(mtime)
        return dt.strftime("%Y-%m-%d %H:%M")
    except FileNotFoundError:
        return "알 수 없음"


def ensure_benchmark_events(preset_name):
    """이 프리셋의 모든 자금투입 이벤트(최초매수+추가입금)에 대해 벤치마크 가격이 없으면 조회해서 저장"""
    events = db.get_funding_events(preset_name)
    for event in events:
        existing = db.get_benchmark_event_prices(preset_name, event["event_date"])
        if not existing:
            target_date = datetime.strptime(event["event_date"], "%Y-%m-%d")
            prices = bp.get_all_prices_on_date(target_date)
            db.save_benchmark_event_prices(preset_name, event["event_date"], prices)
    return events


def compute_benchmark_return(preset_name, benchmark_name, current_price):
    """모든 자금투입 이벤트를 금액가중으로 반영한 벤치마크 수익률(%) 계산"""
    if current_price is None:
        return None
    events = db.get_funding_events(preset_name)
    total_invested = 0
    benchmark_value = 0
    for event in events:
        prices = db.get_benchmark_event_prices(preset_name, event["event_date"])
        price_then = prices.get(benchmark_name)
        if price_then is None or price_then == 0:
            continue
        total_invested += event["amount"]
        benchmark_value += event["amount"] * (current_price / price_then)
    if total_invested == 0:
        return None
    return (benchmark_value - total_invested) / total_invested * 100


def reset_criteria_to_defaults():
    """모든 조건 위젯을 기본값으로 되돌림 (프리셋 저장 후 새 시작을 위해)"""
    for use_key, key, label, default_bool, min_v, max_v, default_val, step, sign in CRITERIA_DEFS:
        st.session_state[use_key] = default_bool
        st.session_state[f"{key}_slider"] = default_val
        st.session_state[f"{key}_num"] = default_val
    st.session_state["use_3year_profit"] = False
    st.session_state.pop("select_all_results", None)
    st.session_state.pop("result_editor", None)
    st.session_state.pop("select_all_holdings", None)
    st.session_state.pop("holdings_editor", None)


@st.cache_data
def load_data():
    return pd.read_csv("screener_data.csv", dtype={"종목코드": str})

df = load_data()


# ══════════════════════════════════════════════════════════
# 사이드바: 화면 전환 + 프리셋 선택
# ══════════════════════════════════════════════════════════
st.sidebar.title("메뉴")
st.sidebar.caption(f"📅 데이터 기준: {get_data_timestamp()}")

page = st.sidebar.radio("화면 선택", ["스크리너 & 모의매매", "프리셋 비교"])

saved_presets = db.list_presets()

if page == "스크리너 & 모의매매":
    st.sidebar.divider()
    st.sidebar.subheader("프리셋 선택")

    preset_options = ["+ 새 프리셋 만들기"] + saved_presets
    if "_preset_selector_version" not in st.session_state:
        st.session_state["_preset_selector_version"] = 0
    selector_key = f"preset_selector_{st.session_state['_preset_selector_version']}"
    selected_option = st.sidebar.selectbox("불러올 프리셋", preset_options, key=selector_key)

    if selected_option == "+ 새 프리셋 만들기":
        preset_name = st.sidebar.text_input("새 프리셋 이름", value="", key="new_preset_name_input")
        if not preset_name:
            base = "새 프리셋"
            existing = set(saved_presets)
            if base not in existing:
                preset_name = base
            else:
                n = 1
                while f"{base} {n}" in existing:
                    n += 1
                preset_name = f"{base} {n}"
    else:
        preset_name = selected_option
        # 이 프리셋을 선택했을 때, 처음 로드하는 경우에만 조건을 적용
        if st.session_state.get("_loaded_preset") != preset_name:
            loaded = db.load_preset_criteria(preset_name)
            if loaded:
                apply_criteria_to_state(loaded)
            st.session_state["_loaded_preset"] = preset_name

        col_copy, col_del = st.sidebar.columns(2)
        with col_copy:
            if st.button("📋 조건 복사", use_container_width=True, help="이 프리셋의 조건만 복사해서 새 프리셋을 만듭니다 (시드머니는 초기화)"):
                new_name = db.generate_copy_name(preset_name)
                success, msg = db.duplicate_preset_criteria(preset_name, new_name)
                if success:
                    st.session_state["_just_duplicated"] = new_name
                    st.sidebar.success(msg)
                    st.rerun()
                else:
                    st.sidebar.error(msg)
        with col_del:
            if st.button("🗑️ 삭제", use_container_width=True):
                st.session_state["_confirm_delete"] = preset_name

        if st.session_state.get("_confirm_delete") == preset_name:
            st.sidebar.warning(f"'{preset_name}'을(를) 정말 삭제할까요? 보유종목·거래내역·벤치마크 기록이 모두 사라지며 되돌릴 수 없습니다.")
            col_yes, col_no = st.sidebar.columns(2)
            with col_yes:
                if st.button("네, 삭제합니다", use_container_width=True, type="primary"):
                    db.delete_preset(preset_name)
                    st.session_state.pop("_confirm_delete", None)
                    st.session_state.pop("_loaded_preset", None)
                    st.sidebar.success(f"'{preset_name}' 삭제 완료")
                    st.rerun()
            with col_no:
                if st.button("취소", use_container_width=True):
                    st.session_state.pop("_confirm_delete", None)
                    st.rerun()

    st.title("나만의 퀀트 스크리너")
    st.caption(f"전체 대상 종목: {len(df)}개 · 현재 프리셋: **{preset_name}** · 📅 데이터 기준: {get_data_timestamp()}")

    if st.sidebar.button("💾 현재 조건을 이 프리셋으로 저장"):
        criteria_now = gather_current_criteria()
        db.save_preset_criteria(preset_name, criteria_now)
        st.sidebar.success(f"'{preset_name}' 저장 완료! 새 프리셋을 위해 화면을 초기화합니다.")
        reset_criteria_to_defaults()
        st.session_state["_preset_selector_version"] += 1  # selectbox를 새로 만들어 기본값(새 프리셋)으로 리셋
        st.session_state.pop("_loaded_preset", None)
        st.session_state.pop("new_preset_name_input", None)
        st.rerun()

    # 새로고침은 실수로 누르기 쉬운 상단을 피해 사이드바 맨 아래에 배치
    st.sidebar.divider()
    st.sidebar.subheader("데이터 새로고침")

    if st.sidebar.button("⚡ 빠른 새로고침 (현재가·PER·PBR, ~1분)"):
        import kis_batch_refresh
        with st.spinner("현재가/PER/PBR 갱신 중... (약 1~2분)"):
            result = kis_batch_refresh.main()
        st.sidebar.success(f"완료! {result['success_count']}/{result['total']}개 갱신 "
                            f"({result['elapsed_sec']:.0f}초)")
        st.cache_data.clear()
        st.rerun()

    with st.sidebar.expander("🐢 재무 데이터 새로고침 (전체, ~1~1.5시간)"):
        st.caption("성장률/부채비율/유동비율/업종/회사개요/모멘텀까지 전부 갱신합니다. "
                   "시간이 오래 걸리니 실행 중 페이지를 닫지 마세요.")
        if st.button("재무 데이터 새로고침 시작"):
            import full_refresh
            with st.spinner("전체 데이터 갱신 중... 최대 1.5시간 정도 걸릴 수 있습니다."):
                result = full_refresh.main()
            st.sidebar.success(f"완료! 총 {result['elapsed_sec']/60:.1f}분 소요")
            st.cache_data.clear()
            st.rerun()

    st.divider()

    mode = st.radio(
        "모드 선택", ["필터 모드", "랭킹 모드"], horizontal=True,
        help="필터 모드: 조건을 만족하는 종목을 전부 찾습니다.\n\n"
             "랭킹 모드: 아래 조건으로 1차로 거른 뒤, 선택한 지표들의 순위를 합산해 상위 N개만 뽑습니다 (마법공식 방식)."
    )
    st.caption("아래 탭의 조건은 두 모드 모두에서 '1차 필터'로 적용됩니다.")

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["가치 (Value)", "퀄리티 (Quality)", "성장 (Growth)", "규모 (Size)", "모멘텀 (Momentum)"]
    )

    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            st.checkbox("PBR 조건 사용", key="use_pbr")
            linked_control("PBR 이하", "pbr", 0.0, 5.0, 1.0, 0.1, HELP_TEXT["pbr"])
        with col2:
            st.checkbox("PER 조건 사용", key="use_per")
            linked_control("PER 이하", "per", 0.0, 50.0, 15.0, 1.0, HELP_TEXT["per"])

    with tab2:
        st.checkbox("ROE 조건 사용", key="use_roe")
        linked_control("ROE 이상 (%)", "roe", -20.0, 50.0, 5.0, 1.0, HELP_TEXT["roe"])

        col1, col2 = st.columns(2)
        with col1:
            st.checkbox("부채비율 조건 사용", key="use_debt")
            linked_control("부채비율 이하 (%)", "debt", 0.0, 500.0, 100.0, 10.0, HELP_TEXT["debt_ratio"])
        with col2:
            st.checkbox("유동비율 조건 사용", key="use_current")
            linked_control("유동비율 이상 (%)", "current", 0.0, 500.0, 100.0, 10.0, HELP_TEXT["current_ratio"])

    with tab3:
        col1, col2 = st.columns(2)
        with col1:
            st.checkbox("매출액성장률 조건 사용", key="use_rev")
            linked_control("매출액성장률 이상 (%)", "rev", -50.0, 100.0, 0.0, 5.0, HELP_TEXT["rev_growth"])
        with col2:
            st.checkbox("영업이익성장률 조건 사용", key="use_op")
            linked_control("영업이익성장률 이상 (%)", "op", -50.0, 100.0, 10.0, 5.0, HELP_TEXT["op_growth"])

        st.divider()
        st.checkbox(
            "3년 연속 영업이익 흑자만 보기", key="use_3year_profit",
            help="최근 3개 사업연도(당기·전기·전전기) 영업이익이 모두 0보다 큰 종목만 남깁니다.\n\n"
                 "일시적 실적 개선이 아니라 꾸준히 돈을 버는 회사인지 확인하는 조건입니다. "
                 "데이터가 부족한 종목(최근 상장 등)은 이 조건에서 자동 제외됩니다."
        )

    with tab4:
        st.checkbox("시가총액 조건 사용", key="use_cap")
        linked_control("시가총액 이상 (억원)", "cap", 0.0, 50000.0, 1000.0, 100.0, HELP_TEXT["cap"])

        st.checkbox("거래대금 조건 사용", key="use_liquidity")
        linked_control("평균거래대금 이상 (억원)", "liquidity", 0.0, 1000.0, 5.0, 1.0, HELP_TEXT["liquidity"])

    with tab5:
        st.caption("기본적으로 꺼져 있습니다. 필요하실 때만 펼쳐서 사용하세요.")
        with st.expander("3개월 모멘텀", expanded=False):
            st.checkbox("3개월수익률 조건 사용", key="use_mom3")
            linked_control("3개월수익률 이상 (%)", "mom3", -80.0, 300.0, -20.0, 5.0, HELP_TEXT["mom_3m"])
        with st.expander("6개월 모멘텀", expanded=False):
            st.checkbox("6개월수익률 조건 사용", key="use_mom6")
            linked_control("6개월수익률 이상 (%)", "mom6", -80.0, 300.0, -20.0, 5.0, HELP_TEXT["mom_6m"])
        with st.expander("12개월 모멘텀", expanded=False):
            st.checkbox("12개월수익률 조건 사용", key="use_mom12")
            linked_control("12개월수익률 이상 (%)", "mom12", -80.0, 500.0, -20.0, 5.0, HELP_TEXT["mom_12m"])

    st.divider()

    current_criteria = gather_current_criteria()
    hard_filtered = filter_stocks(df, current_criteria)

    rank_cols_for_display = []

    if mode == "필터 모드":
        filtered = hard_filtered
        st.subheader(f"📊 {preset_name} (필터 모드)")
        col1, col2 = st.columns(2)
        col1.metric("조건 통과 종목 수", f"{len(filtered)}개")
        col2.metric("전체 대상", f"{len(df)}개")
    else:
        st.subheader("🏆 랭킹 설정")
        indicator_labels = [label for label, _, _ in RANKING_INDICATORS]
        default_labels = [l for l in indicator_labels if l.startswith(("PER", "PBR", "ROE"))]
        selected_labels = st.multiselect(
            "랭킹에 사용할 지표 (순위를 합산합니다)", indicator_labels, default=default_labels
        )
        top_n = st.number_input("상위 몇 개를 추출할까요?", min_value=1, max_value=200, value=20, step=1)

        st.caption(f"1차 필터 통과 종목({len(hard_filtered)}개) 중, 선택한 지표가 전부 존재하는 종목만 랭킹에 포함됩니다.")

        filtered, rank_cols_for_display = rank_stocks(hard_filtered, selected_labels, top_n)

        st.subheader(f"📊 {preset_name} (랭킹 모드 - 상위 {len(filtered)}개)")
        col1, col2, col3 = st.columns(3)
        col1.metric("1차 필터 통과", f"{len(hard_filtered)}개")
        col2.metric("최종 추출", f"{len(filtered)}개")
        col3.metric("전체 대상", f"{len(df)}개")
        st.caption("'최종순위'가 실제 등수(1등, 2등...)입니다. '합산순위'는 선택한 지표들의 순위를 더한 점수라 "
                   "종목마다 값이 다르며, 이 점수가 가장 낮은 종목이 최종순위 1등이 됩니다.")

    display_cols = ["종목코드", "종목명", "업종명", "시장구분", "현재가", "PBR", "PER", "ROE",
                     "부채비율(%)", "유동비율(%)", "매출액성장률(%)", "영업이익성장률(%)", "3년연속흑자",
                     "3개월수익률(%)", "6개월수익률(%)", "12개월수익률(%)",
                     "시가총액", "평균거래대금(억원)"]
    if mode == "랭킹 모드":
        display_cols = ["최종순위", "합산순위"] + display_cols
    display_cols = [c for c in display_cols if c in filtered.columns]

    sort_col = "최종순위" if mode == "랭킹 모드" else "시가총액"
    sort_asc = True if mode == "랭킹 모드" else False
    result_view = filtered[display_cols].sort_values(sort_col, ascending=sort_asc).reset_index(drop=True)

    select_all_results = st.checkbox("전체 선택", key="select_all_results",
                                      on_change=lambda: st.session_state.pop("result_editor", None))

    # 화면 표시용: 콤마 포맷 적용 (계산에는 안 씀, 순수 표시 목적)
    display_view = format_currency_cols(result_view, ["현재가", "시가총액", "매출액", "영업이익"])
    display_view.insert(0, "선택", select_all_results)

    edited = st.data_editor(
        display_view, use_container_width=True, hide_index=True,
        disabled=display_cols, key="result_editor"
    )

    st.divider()

    # ── 포트폴리오(모의매매) ──────────────────────────────
    st.header("💰 모의매매 (가상 거래)")

    portfolio = db.get_or_create_portfolio(preset_name)
    holdings = db.get_holdings(preset_name)

    col1, col2, col3 = st.columns(3)
    with col1:
        weighting = st.radio("매수 방식", ["균등배분", "시가총액가중"], horizontal=True)
    with col2:
        invest_amount = st.number_input("투자할 총 금액 (원)", min_value=0, value=1_000_000, step=100_000)
    with col3:
        st.metric("현재 가상 현금", f"{portfolio['cash_balance']:,.0f}원")

    with st.expander("💵 추가 입금"):
        st.caption("시드머니를 더 넣습니다. 벤치마크 비교에도 이 입금액이 그 시점부터 반영됩니다.")
        col_amt, col_btn = st.columns([3, 1])
        with col_amt:
            deposit_amount = st.number_input("입금할 금액 (원)", min_value=0, value=1_000_000, step=100_000,
                                              key="deposit_amount_input", label_visibility="collapsed")
        with col_btn:
            if st.button("입금하기", use_container_width=True):
                if deposit_amount > 0:
                    success, msg = db.add_deposit(preset_name, deposit_amount)
                    st.success(msg)
                    st.rerun()
                else:
                    st.warning("입금액을 입력해주세요.")

    selected_codes = edited[edited["선택"] == True]["종목코드"].tolist()
    # 계산은 항상 숫자 원본(filtered)에서 조회 - 화면 포맷 문자열과 완전히 분리
    selected_rows = filtered[filtered["종목코드"].isin(selected_codes)][["종목코드", "종목명", "현재가", "시가총액"]].copy()

    if st.button("✅ 선택한 종목 매수", type="primary"):
        if len(selected_rows) == 0:
            st.warning("선택된 종목이 없습니다.")
        else:
            with st.spinner("실시간 가격 조회 중..."):
                realtime_prices = kis.get_realtime_prices(selected_rows["종목코드"].tolist())

            price_warnings = []
            priced_rows = selected_rows.copy()
            for idx, row in priced_rows.iterrows():
                rt_price = realtime_prices.get(row["종목코드"])
                if rt_price:
                    priced_rows.at[idx, "현재가"] = rt_price
                else:
                    price_warnings.append(row["종목명"])

            if price_warnings:
                st.warning(f"다음 종목은 실시간 조회 실패로 저장된 가격을 사용합니다: {', '.join(price_warnings)}")

            if weighting == "균등배분":
                per_stock_amount = invest_amount / len(priced_rows)
                weights = {row["종목코드"]: per_stock_amount for _, row in priced_rows.iterrows()}
            else:
                total_cap = priced_rows["시가총액"].sum()
                weights = {row["종목코드"]: invest_amount * (row["시가총액"] / total_cap) for _, row in priced_rows.iterrows()}

            orders = []
            for _, row in priced_rows.iterrows():
                amount = weights[row["종목코드"]]
                price = row["현재가"]
                qty = int(amount // price) if price > 0 else 0
                if qty > 0:
                    orders.append({"stock_code": row["종목코드"], "stock_name": row["종목명"],
                                    "quantity": qty, "price": price})

            if orders:
                success, msg = db.buy_stocks(preset_name, orders)
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.warning("배분 금액이 너무 적어 1주도 매수할 수 없는 종목만 선택되었습니다.")

    st.subheader("📦 보유 현황")

    if len(holdings) == 0:
        st.info("아직 보유 중인 종목이 없습니다.")
    else:
        if st.button("🔄 보유종목 실시간 시세 새로고침"):
            with st.spinner("실시간 가격 조회 중..."):
                rt_prices = kis.get_realtime_prices(holdings["stock_code"].tolist())
            st.session_state["_holdings_rt_prices"] = rt_prices
            st.rerun()

        rt_prices = st.session_state.get("_holdings_rt_prices", {})
        price_map = df.set_index("종목코드")["현재가"].to_dict()
        # 실시간으로 새로고침한 값이 있으면 그걸 우선 사용, 없으면 저장된 스냅샷 가격
        holdings["현재가"] = holdings["stock_code"].apply(lambda c: rt_prices.get(c) or price_map.get(c))
        holdings["평가금액"] = holdings["quantity"] * holdings["현재가"]
        holdings["수익률(%)"] = ((holdings["현재가"] - holdings["avg_buy_price"]) / holdings["avg_buy_price"] * 100).round(2)

        if rt_prices:
            st.caption("✅ 실시간 가격이 반영된 상태입니다.")
        else:
            st.caption("⚠️ 아직 저장된 스냅샷 가격입니다. 매도 시에는 자동으로 실시간 가격을 재조회합니다.")

        holdings_view = holdings[["stock_code", "stock_name", "quantity", "avg_buy_price", "현재가", "평가금액", "수익률(%)"]].copy()
        holdings_view.columns = ["종목코드", "종목명", "수량", "평균매입가", "현재가", "평가금액", "수익률(%)"]

        select_all_holdings = st.checkbox("전체 선택", key="select_all_holdings",
                                           on_change=lambda: st.session_state.pop("holdings_editor", None))

        # 화면 표시용: 콤마 포맷 (계산에는 원본 holdings 사용)
        holdings_display = format_currency_cols(holdings_view, ["평균매입가", "현재가", "평가금액"])
        holdings_display.insert(0, "선택", select_all_holdings)

        edited_holdings = st.data_editor(
            holdings_display, use_container_width=True, hide_index=True,
            disabled=["종목코드", "종목명", "수량", "평균매입가", "현재가", "평가금액", "수익률(%)"],
            key="holdings_editor"
        )

        if st.button("🔻 선택한 종목 매도"):
            sell_codes = edited_holdings[edited_holdings["선택"] == True]["종목코드"].tolist()
            if len(sell_codes) == 0:
                st.warning("선택된 종목이 없습니다.")
            else:
                sell_selected = holdings[holdings["stock_code"].isin(sell_codes)][["stock_code", "stock_name", "현재가"]].copy()
                sell_selected.columns = ["종목코드", "종목명", "현재가"]

                with st.spinner("매도 전 실시간 가격 재확인 중..."):
                    sell_rt_prices = kis.get_realtime_prices(sell_selected["종목코드"].tolist())

                sell_orders = []
                for _, row in sell_selected.iterrows():
                    final_price = sell_rt_prices.get(row["종목코드"]) or row["현재가"]
                    sell_orders.append({"stock_code": row["종목코드"], "stock_name": row["종목명"], "price": final_price})

                success, msg = db.sell_stocks(preset_name, sell_orders)
                st.session_state.pop("_holdings_rt_prices", None)
                st.success(msg)
                st.rerun()

        total_eval = holdings["평가금액"].sum()
        total_asset = portfolio["cash_balance"] + total_eval
        total_return = (total_asset - portfolio["initial_cash"]) / portfolio["initial_cash"] * 100

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("보유 종목 평가금액", f"{total_eval:,.0f}원")
        col2.metric("현금 잔고", f"{portfolio['cash_balance']:,.0f}원")
        col3.metric("총 자산", f"{total_asset:,.0f}원")
        col4.metric("총 수익률", f"{total_return:+.2f}%")


# ══════════════════════════════════════════════════════════
# 프리셋 비교 화면
# ══════════════════════════════════════════════════════════
else:
    st.title("📊 프리셋 비교")

    if not saved_presets:
        st.info("아직 저장된 프리셋이 없습니다. '스크리너 & 모의매매' 화면에서 조건을 설정하고 저장해주세요.")
    else:
        if st.button("🔄 전체 프리셋 시세 새로고침"):
            all_codes = set()
            for name in saved_presets:
                h = db.get_holdings(name)
                all_codes.update(h["stock_code"].tolist())

            if all_codes:
                with st.spinner(f"{len(all_codes)}개 종목 실시간 가격 조회 중..."):
                    st.session_state["_compare_rt_prices"] = kis.get_realtime_prices(list(all_codes))
                st.success("새로고침 완료!")
            else:
                st.info("보유 중인 종목이 있는 프리셋이 없습니다.")
            st.rerun()

        compare_rt_prices = st.session_state.get("_compare_rt_prices", {})
        if compare_rt_prices:
            st.caption("✅ 실시간 가격이 반영된 상태입니다.")
        else:
            st.caption("⚠️ 스냅샷 가격 기준입니다. 위 버튼으로 새로고침할 수 있습니다.")

        summary_rows = []
        for name in saved_presets:
            criteria = db.load_preset_criteria(name)
            matched = filter_stocks(df, criteria)
            portfolio = db.get_or_create_portfolio(name)
            holdings = db.get_holdings(name)

            if len(holdings) > 0:
                price_map = df.set_index("종목코드")["현재가"].to_dict()
                holdings["현재가"] = holdings["stock_code"].apply(
                    lambda c: compare_rt_prices.get(c) or price_map.get(c)
                )
                total_eval = (holdings["quantity"] * holdings["현재가"]).sum()
            else:
                total_eval = 0

            total_asset = portfolio["cash_balance"] + total_eval
            total_return = (total_asset - portfolio["initial_cash"]) / portfolio["initial_cash"] * 100 if portfolio["initial_cash"] else 0

            summary_rows.append({
                "name": name, "criteria": criteria, "matched": len(matched),
                "holdings_count": len(holdings), "total_asset": total_asset, "total_return": total_return
            })

        # 수익률 높은 순으로 정렬해서 카드 표시
        summary_rows.sort(key=lambda r: r["total_return"], reverse=True)

        # 현재 벤치마크 ETF 가격은 한 번만 조회해서 재사용 (프리셋마다 반복 호출 방지)
        current_benchmark_prices = None

        for i, row in enumerate(summary_rows):
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                with col1:
                    rank_emoji = "🥇" if i == 0 else ("🥈" if i == 1 else ("🥉" if i == 2 else "▫️"))
                    st.markdown(f"### {rank_emoji} {row['name']}")
                col2.metric("조건 통과", f"{row['matched']}개")
                col3.metric("보유 종목", f"{row['holdings_count']}개")
                col4.metric("총 수익률", f"{row['total_return']:+.2f}%")

                with st.expander("조건 상세 보기"):
                    for line in summarize_criteria_lines(row["criteria"]):
                        st.markdown(line)

                with st.expander("📈 벤치마크와 비교하기"):
                    funding_events = db.backfill_initial_funding_event(row["name"])

                    if not funding_events:
                        st.caption("아직 매수 이력이 없어 비교할 수 없습니다.")
                    else:
                        # 이벤트 중 벤치마크 가격이 아직 없는 게 있는지 확인
                        missing = [e for e in funding_events if not db.get_benchmark_event_prices(row["name"], e["event_date"])]

                        if missing:
                            if st.button(f"벤치마크 기록하기 ({len(missing)}건 대기중)", key=f"init_bench_{row['name']}"):
                                with st.spinner("자금투입 시점 기준 벤치마크 가격 조회 중..."):
                                    ensure_benchmark_events(row["name"])
                                st.rerun()
                            st.caption(f"자금투입 이벤트 {len(funding_events)}건 중 {len(missing)}건의 벤치마크 가격이 아직 기록되지 않았습니다.")
                        else:
                            selected_benchmarks = st.multiselect(
                                "비교할 벤치마크 선택", list(BENCHMARK_ETFS.keys()),
                                default=[], key=f"bench_select_{row['name']}"
                            )
                            if selected_benchmarks:
                                if current_benchmark_prices is None:
                                    with st.spinner("벤치마크 현재가 조회 중..."):
                                        current_benchmark_prices = bp.get_all_current_prices()

                                event_summary = ", ".join(
                                    f"{e['event_date']}({e['event_type']}) {e['amount']:,.0f}원" for e in funding_events
                                )
                                st.caption(f"자금투입 내역: {event_summary}")

                                for bname in selected_benchmarks:
                                    now_price = current_benchmark_prices.get(bname)
                                    bench_return = compute_benchmark_return(row["name"], bname, now_price)
                                    if bench_return is None:
                                        st.caption(f"{bname}: 가격 정보 부족으로 비교 불가")
                                        continue
                                    alpha = row["total_return"] - bench_return
                                    arrow = "▲" if alpha >= 0 else "▼"
                                    color = "green" if alpha >= 0 else "red"
                                    st.markdown(
                                        f"**{bname}**: 벤치마크 {bench_return:+.2f}% · "
                                        f":{color}[알파 {arrow} {alpha:+.2f}%p]"
                                    )

        st.caption("💡 '조건 통과 종목 수'는 현재 데이터 기준 실시간 계산, '총 수익률'은 각 프리셋의 모의매매 실적입니다.")