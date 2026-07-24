import streamlit as st
import pandas as pd

st.set_page_config(page_title="퀀트 스크리너", layout="wide")

# ── 지표 설명 (도움말 툴팁용) ──────────────────────────────
HELP_TEXT = {
    "pbr": "주가가 회사의 순자산(장부가치) 대비 몇 배로 거래되는지 나타냅니다.\n\n"
           "**낮을수록 저평가**로 봅니다. 1 이하면 회사가 가진 자산보다 싸게 거래된다는 뜻입니다.",
    "per": "주가가 회사의 연간 순이익 대비 몇 배인지 나타냅니다.\n\n"
           "**낮을수록 저평가**로 봅니다. 단, 너무 낮으면 시장이 그 회사 실적을 불신하고 있다는 신호일 수도 있습니다.",
    "roe": "회사가 자기 자본으로 얼마나 효율적으로 돈을 버는지(%) 나타냅니다.\n\n"
           "**높을수록 좋습니다.** 다만 부채가 과도해서 ROE가 인위적으로 높아진 경우도 있어 부채비율과 함께 보는 것이 안전합니다.",
    "rev_growth": "작년 대비 매출이 얼마나 늘었는지(%) 나타냅니다.\n\n**높을수록** 성장하는 회사입니다.",
    "op_growth": "작년 대비 영업이익이 얼마나 늘었는지(%) 나타냅니다.\n\n"
                 "**높을수록 좋으나**, 기저효과(작년이 유난히 안 좋았던 경우)로 왜곡될 수 있습니다.",
    "cap": "회사 전체 가치(주가 × 발행주식수)를 나타냅니다.\n\n"
           "**너무 작으면** 거래량이 적어 매매 자체가 어렵거나 가격 변동이 심할 위험이 있습니다.",
}


# ── 슬라이더 ↔ 숫자입력 동기화 콜백 ──────────────────────────────
def sync_from_slider(key):
    st.session_state[f"{key}_num"] = st.session_state[f"{key}_slider"]

def sync_from_number(key):
    st.session_state[f"{key}_slider"] = st.session_state[f"{key}_num"]


def linked_control(label, key, min_v, max_v, default, step, help_text=None):
    """슬라이더와 숫자입력칸이 서로 실시간 동기화되는 컨트롤"""
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


# ── 데이터 불러오기 ──────────────────────────────
@st.cache_data
def load_data():
    return pd.read_csv("screener_data.csv", dtype={"종목코드": str})

df = load_data()

st.title("나만의 퀀트 스크리너")
st.caption(f"전체 대상 종목: {len(df)}개")

preset_name = st.text_input("프리셋 이름", value="프리셋 1: 저평가 우량주")

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["가치 (Value)", "퀄리티 (Quality)", "성장 (Growth)", "규모 (Size)"])

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        use_pbr = st.checkbox("PBR 조건 사용", value=True, key="use_pbr")
        pbr_max = linked_control("PBR 이하", "pbr", 0.0, 5.0, 1.0, 0.1, HELP_TEXT["pbr"])
    with col2:
        use_per = st.checkbox("PER 조건 사용", value=True, key="use_per")
        per_max = linked_control("PER 이하", "per", 0.0, 50.0, 15.0, 1.0, HELP_TEXT["per"])

with tab2:
    use_roe = st.checkbox("ROE 조건 사용", value=True, key="use_roe")
    roe_min = linked_control("ROE 이상 (%)", "roe", -20.0, 50.0, 5.0, 1.0, HELP_TEXT["roe"])

with tab3:
    col1, col2 = st.columns(2)
    with col1:
        use_rev_growth = st.checkbox("매출액성장률 조건 사용", value=False, key="use_rev")
        rev_growth_min = linked_control("매출액성장률 이상 (%)", "rev", -50.0, 100.0, 0.0, 5.0, HELP_TEXT["rev_growth"])
    with col2:
        use_op_growth = st.checkbox("영업이익성장률 조건 사용", value=False, key="use_op")
        op_growth_min = linked_control("영업이익성장률 이상 (%)", "op", -50.0, 100.0, 10.0, 5.0, HELP_TEXT["op_growth"])

with tab4:
    use_cap = st.checkbox("시가총액 조건 사용", value=True, key="use_cap")
    cap_min = linked_control("시가총액 이상 (억원)", "cap", 0.0, 50000.0, 1000.0, 100.0, HELP_TEXT["cap"])

st.divider()

# ── 필터링 로직 ──────────────────────────────
filtered = df.copy()

if use_pbr:
    filtered = filtered[filtered["PBR"] <= pbr_max]
if use_per:
    filtered = filtered[(filtered["PER"] <= per_max) & (filtered["PER"] > 0)]
if use_roe:
    filtered = filtered[filtered["ROE"] >= roe_min]
if use_rev_growth:
    filtered = filtered[filtered["매출액성장률(%)"] >= rev_growth_min]
if use_op_growth:
    filtered = filtered[filtered["영업이익성장률(%)"] >= op_growth_min]
if use_cap:
    filtered = filtered[filtered["시가총액"] >= cap_min]

# ── 결과 표시 ──────────────────────────────
st.subheader(f"📊 {preset_name}")
col1, col2 = st.columns(2)
col1.metric("조건 통과 종목 수", f"{len(filtered)}개")
col2.metric("전체 대상", f"{len(df)}개")

display_cols = ["종목코드", "종목명", "업종명", "시장구분", "현재가", "PBR", "PER", "ROE",
                 "매출액성장률(%)", "영업이익성장률(%)", "시가총액"]
display_cols = [c for c in display_cols if c in filtered.columns]

st.dataframe(
    filtered[display_cols].sort_values("시가총액", ascending=False),
    use_container_width=True,
    hide_index=True
)