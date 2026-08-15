import streamlit as st
import pandas as pd
import json
import auth_manager as auth
import portfolio_db as db
import kis_realtime as kis
import benchmark_prices as bp
from benchmark_config import BENCHMARK_ETFS
import backtest_engine as bt
from screener_logic import (
    CRITERIA_DEFS, FILTER_COLUMN_MAP, RANKING_INDICATORS,
    filter_stocks, summarize_criteria, summarize_criteria_lines, rank_stocks
)

st.set_page_config(page_title="퀀트 스크리너", layout="wide")


# ══════════════════════════════════════════════════════════
# 인증 + 모드 선택 게이트 (통과해야 아래 실제 앱이 실행됨)
# ══════════════════════════════════════════════════════════

def render_setup_screen():
    st.title("🔐 처음 오셨네요 - API 설정")
    st.markdown("이 프로그램은 **본인 명의의 API 키**로 작동합니다. 아래 안내를 따라 발급받아 입력해주세요.")

    with st.expander("📖 API 키 발급받는 방법 (처음이시면 꼭 읽어주세요)", expanded=True):
        st.markdown("""
**1) 한국투자증권(KIS) — 실전투자 앱키·시크릿·계좌번호**

1. [KIS Developers 포털](https://apiportal.koreainvestment.com) 접속
2. 보유하신 한투 계좌 로그인 정보로 로그인 (로그인이 안 되면 한투 고객센터 ☎1544-5000 문의)
3. "API 신청하기" 클릭 → **실전투자계좌** 체크 → 계좌번호 선택 → 비밀번호 입력 → 인증
4. 발급된 **APP Key**, **APP Secret**을 복사해서 아래에 입력

**2) DART(전자공시시스템) — 인증키**

1. [OPEN DART](https://opendart.fss.or.kr) 접속 (KIS와 별개로, 본인 이메일로 새로 가입)
2. 회원가입 (이메일 인증만 하면 됨, 증권계좌 불필요)
3. 상단 메뉴 "인증키 신청/관리" → 인증키 신청 (이용목적: "개인 투자 참고용 프로그램 개발" 정도로 작성)
4. 발급된 **인증키**를 복사해서 아래에 입력
        """)

    st.subheader("API 키 입력")
    kis_app_key = st.text_input("한투 APP Key", type="password", key="setup_kis_app_key")
    kis_app_secret = st.text_input("한투 APP Secret", type="password", key="setup_kis_app_secret")
    kis_account_no = st.text_input("한투 계좌번호 (숫자만, 예: 12345678)", key="setup_kis_account_no")
    dart_api_key = st.text_input("DART 인증키", type="password", key="setup_dart_api_key")

    current_keys_tuple = (kis_app_key, kis_app_secret, dart_api_key)

    if st.button("🔍 인증키 확인", type="primary"):
        if not all([kis_app_key, kis_app_secret, kis_account_no, dart_api_key]):
            st.error("API 키 4개를 모두 입력해주세요.")
        else:
            with st.spinner("한투 · DART 서버에 실제로 접속해서 확인하는 중..."):
                ok, msg = auth.verify_all_credentials(kis_app_key, kis_app_secret, dart_api_key)
            st.session_state["_verify_result"] = ok
            st.session_state["_verify_message"] = msg
            st.session_state["_verified_keys"] = current_keys_tuple

    # 키를 검증 이후에 바꿨다면, 검증 결과를 무효화 (다시 확인하도록 유도)
    keys_changed_since_verify = st.session_state.get("_verified_keys") != current_keys_tuple
    verified_ok = st.session_state.get("_verify_result", False) and not keys_changed_since_verify

    if st.session_state.get("_verify_message") and not keys_changed_since_verify:
        if st.session_state["_verify_result"]:
            st.success(st.session_state["_verify_message"])
        else:
            st.error(st.session_state["_verify_message"])
    elif keys_changed_since_verify and st.session_state.get("_verify_message"):
        st.warning("키 입력값이 바뀌었습니다. '인증키 확인'을 다시 눌러주세요.")

    st.divider()
    st.subheader("비밀번호 설정")
    st.caption("프로그램을 켤 때마다 입력할 비밀번호입니다. 같은 컴퓨터를 쓰는 다른 사람으로부터의 "
               "가벼운 보호 목적이며, 강력한 보안 장치는 아닙니다.")
    password1 = st.text_input("비밀번호", type="password", key="setup_password1")
    password2 = st.text_input("비밀번호 확인", type="password", key="setup_password2")

    if not verified_ok:
        st.info("먼저 위에서 '인증키 확인'을 통과해야 저장할 수 있습니다.")

    if st.button("저장하고 시작하기", type="primary", disabled=not verified_ok):
        if not password1:
            st.error("비밀번호를 입력해주세요.")
        elif password1 != password2:
            st.error("비밀번호가 서로 다릅니다.")
        elif len(password1) < 4:
            st.error("비밀번호는 4자 이상으로 설정해주세요.")
        else:
            auth.save_credentials(kis_app_key, kis_app_secret, kis_account_no, dart_api_key, password1)
            st.success("저장 완료! 다시 시작합니다...")
            st.session_state["_authenticated"] = True
            st.rerun()


def render_login_screen():
    st.title("🔒 로그인")

    with st.form("login_form"):
        password = st.text_input("비밀번호", type="password")
        col1, col2 = st.columns(2)
        with col1:
            login_clicked = st.form_submit_button("로그인", type="primary", use_container_width=True)
        with col2:
            reset_clicked = st.form_submit_button("API 재설정", use_container_width=True)

    if login_clicked:
        if auth.verify_password(password):
            st.session_state["_authenticated"] = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸습니다.")

    if reset_clicked:
        st.session_state["_show_api_reset"] = True

    if st.session_state.get("_show_api_reset"):
        render_api_reset_section()


def render_api_reset_section():
    """API 키 재설정 폼. 로그인 화면과 모드 선택 화면 양쪽에서 재사용됨"""
    st.divider()
    st.subheader("API 키 재설정")
    st.caption("비밀번호는 그대로 유지되고, API 키만 새로 바뀝니다.")
    current = auth.get_current_keys()

    new_app_key = st.text_input("한투 APP Key", value=current["kis_app_key"], type="password", key="reset_app_key")
    new_app_secret = st.text_input("한투 APP Secret", value=current["kis_app_secret"], type="password", key="reset_app_secret")
    new_account_no = st.text_input("한투 계좌번호", value=current["kis_account_no"], key="reset_account_no")
    new_dart_key = st.text_input("DART 인증키", value=current["dart_api_key"], type="password", key="reset_dart_key")

    reset_keys_tuple = (new_app_key, new_app_secret, new_dart_key)

    if st.button("🔍 인증키 확인", key="reset_verify_btn"):
        with st.spinner("한투 · DART 서버에 실제로 접속해서 확인하는 중..."):
            ok, msg = auth.verify_all_credentials(new_app_key, new_app_secret, new_dart_key)
        st.session_state["_reset_verify_result"] = ok
        st.session_state["_reset_verify_message"] = msg
        st.session_state["_reset_verified_keys"] = reset_keys_tuple

    reset_keys_changed = st.session_state.get("_reset_verified_keys") != reset_keys_tuple
    reset_verified_ok = st.session_state.get("_reset_verify_result", False) and not reset_keys_changed

    if st.session_state.get("_reset_verify_message") and not reset_keys_changed:
        if st.session_state["_reset_verify_result"]:
            st.success(st.session_state["_reset_verify_message"])
        else:
            st.error(st.session_state["_reset_verify_message"])
    elif reset_keys_changed and st.session_state.get("_reset_verify_message"):
        st.warning("키 입력값이 바뀌었습니다. '인증키 확인'을 다시 눌러주세요.")

    if st.button("API 키 업데이트", type="primary", disabled=not reset_verified_ok, key="reset_submit_btn"):
        auth.update_api_keys_only(new_app_key, new_app_secret, new_account_no, new_dart_key)
        st.success("API 키가 업데이트되었습니다.")
        st.session_state["_show_api_reset"] = False
        st.rerun()


def render_mode_selection():
    st.title("📈 모드 선택")
    st.caption("어떤 모드로 시작하시겠어요?")

    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.subheader("🧪 모의매매")
            st.write("가상의 자금으로 스크리닝, 백테스트, 모의 매수/매도를 체험합니다.")
            if st.button("모의매매 시작", type="primary", use_container_width=True):
                st.session_state["_trade_mode"] = "모의매매"
                st.rerun()
    with col2:
        with st.container(border=True):
            st.subheader("💰 실전매매")
            st.write("실제 증권계좌로 주문을 실행합니다.")
            if st.button("실전매매 시작", use_container_width=True):
                st.session_state["_trade_mode"] = "실전매매"
                st.rerun()

    st.divider()
    with st.expander("⚙️ API 키 재설정"):
        render_api_reset_section()


if not auth.is_configured():
    render_setup_screen()
    st.stop()

if not st.session_state.get("_authenticated"):
    render_login_screen()
    st.stop()

if st.session_state.get("_trade_mode") is None:
    render_mode_selection()
    st.stop()

if st.session_state["_trade_mode"] == "실전매매":
    st.title("💰 실전매매")
    st.info("아직 준비 중입니다. 모의매매로 충분히 검증한 뒤 추가될 예정이에요.")
    if st.button("← 모드 선택으로 돌아가기"):
        st.session_state["_trade_mode"] = None
        st.rerun()
    st.stop()

# ══════════════════════════════════════════════════════════
# 여기서부터는 "모의매매" 모드로 확정된 상태에서만 실행됨
# ══════════════════════════════════════════════════════════

db.init_db()

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
    result["mode"] = "랭킹 모드" if st.session_state.get("scr_use_ranking", False) else "필터 모드"
    result["ranking_labels"] = st.session_state.get("scr_ranking_labels", [])
    result["top_n"] = st.session_state.get("scr_top_n", 20)
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
    if "mode" in criteria:
        st.session_state["scr_use_ranking"] = (criteria["mode"] == "랭킹 모드")
    if "ranking_labels" in criteria:
        st.session_state["scr_ranking_labels"] = criteria["ranking_labels"]
    if "top_n" in criteria:
        st.session_state["scr_top_n"] = criteria["top_n"]


def normalize_date_index(df, date_col="날짜", value_col="총자산", new_name=None):
    """서로 다른 백테스트 실행 간 미세한 시각 차이를 없애기 위해 날짜만 남기고 인덱스로 설정"""
    out = df[[date_col, value_col]].copy()
    out[date_col] = pd.to_datetime(out[date_col]).dt.normalize()
    if new_name:
        out = out.rename(columns={value_col: new_name})
    return out.set_index(date_col)


def format_currency_cols(view_df, cols):
    """지정한 컬럼들을 천단위 콤마가 붙은 문자열로 변환 (표시 전용)"""
    view_df = view_df.copy()
    for c in cols:
        if c in view_df.columns:
            view_df[c] = view_df[c].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else x)
    return view_df


def build_preset_report_text(name, criteria, holdings_df, portfolio, total_asset, total_return, transactions_df, earliest_buy_date):
    """프리셋 하나의 조건/수익률/보유종목/거래내역을 AI 상담용 텍스트로 정리.
    holdings_df는 '현재가' 컬럼이 이미 채워져 있어야 함 (호출부에서 실시간/스냅샷 가격 반영 후 넘길 것)."""
    lines = [f"## 프리셋: {name}", "", "### 조건", summarize_criteria(criteria), ""]

    lines.append("### 매매 정보")
    lines.append(f"- 매매 시작일: {earliest_buy_date or '아직 매수 이력 없음'}")
    lines.append(f"- 시작 자금: {portfolio['initial_cash']:,.0f}원")
    lines.append(f"- 현재 평가자산: {total_asset:,.0f}원 (현금 {portfolio['cash_balance']:,.0f}원 포함)")
    lines.append(f"- 총 수익률: {total_return:+.2f}%")
    lines.append("")

    lines.append(f"### 보유 종목 ({len(holdings_df)}개)")
    if len(holdings_df) == 0:
        lines.append("- 없음")
    else:
        for _, row in holdings_df.iterrows():
            buy_price = row["avg_buy_price"]
            stock_return = ((row["현재가"] - buy_price) / buy_price * 100) if buy_price else 0
            lines.append(
                f"- {row['stock_name']}({row['stock_code']}) {row['quantity']}주 · "
                f"평균매입가 {buy_price:,.0f}원 · 현재가 {row['현재가']:,.0f}원 · 수익률 {stock_return:+.2f}%"
            )
    lines.append("")

    lines.append(f"### 거래 이력 ({len(transactions_df)}건, 최신순)")
    if len(transactions_df) == 0:
        lines.append("- 없음")
    else:
        for _, row in transactions_df.iterrows():
            lines.append(
                f"- {str(row['timestamp'])[:16].replace('T', ' ')} {row['action']} "
                f"{row['stock_name']}({row['stock_code']}) {row['quantity']}주 @ {row['price']:,.0f}원 "
                f"(금액 {row['amount']:,.0f}원)"
            )
    lines.append("")
    return "\n".join(lines)


def render_data_freshness_notice(result):
    """백테스터가 실제로 갖고 있는 과거 주가 데이터가 최신 시점 기준 며칠 전까지인지 표시.
    많이 오래됐으면(허용범위 21일 초과) 마지막 시점 결과가 부정확할 수 있다고 경고한다
    (역사적으로, 데이터가 밀린 상태로 백테스트하면 마지막 달 수익률이 크게 왜곡된 적이 있었음)."""
    staleness = result.get("data_staleness_days")
    latest_date = result.get("data_latest_price_date")
    if staleness is None or latest_date is None:
        return
    latest_str = pd.to_datetime(latest_date).strftime("%Y-%m-%d")
    if staleness > 21:
        st.warning(
            f"⚠️ 보유 중인 과거 주가 데이터가 **{latest_str}**까지만 있습니다 (백테스트 마지막 시점과 "
            f"**{staleness}일** 차이). 이 기간 동안은 마지막으로 알려진 가격으로 대체해서 계산했으니, "
            f"최근 구간(특히 마지막 달) 수익률은 참고용으로만 봐주세요. 정확히 보려면 과거 주가 데이터를 "
            f"새로고침한 뒤 다시 실행해주세요."
        )
    else:
        st.caption(f"📅 가격 데이터 최신 기준일: {latest_str}")


def build_backtest_report_text(preset_name, criteria, months_option, result, mode_label):
    """백테스트 결과 하나(또는 종목 수 비교의 N 하나)를 AI 상담용 텍스트로 정리"""
    lines = [f"## 백테스트: {preset_name} ({mode_label})", "", "### 조건", summarize_criteria(criteria), ""]

    lines.append("### 백테스트 설정 및 결과")
    lines.append(f"- 기간: {months_option}개월 전부터")
    lines.append(f"- 시작 자금: {result['initial_amount']:,.0f}원")
    lines.append(f"- 최종 자산: {result['final_value']:,.0f}원")
    lines.append(f"- 총 수익률: {result['final_return']:+.2f}%")
    if result.get("data_staleness_days") is not None and result.get("data_latest_price_date") is not None:
        latest_str = pd.to_datetime(result["data_latest_price_date"]).strftime("%Y-%m-%d")
        lines.append(f"- 가격 데이터 최신 기준일: {latest_str} (이보다 최근 구간은 참고용)")
    lines.append("")

    lines.append("### 벤치마크 대비")
    for name, series in result["benchmarks"].items():
        final_bench = series[-1]["총자산"] if series else None
        if final_bench is None:
            lines.append(f"- {name}: 데이터 부족으로 비교 불가")
            continue
        bench_return = (final_bench - result["initial_amount"]) / result["initial_amount"] * 100
        alpha = result["final_return"] - bench_return
        lines.append(f"- {name}: {bench_return:+.2f}% (알파 {alpha:+.2f}%p)")
    lines.append("")

    last_row = result["portfolio"][-1] if result["portfolio"] else None
    lines.append("### 최종 시점 보유 종목")
    lines.append(f"- {last_row['보유종목']}" if last_row and last_row.get("보유종목") else "- 없음")
    lines.append("")
    return "\n".join(lines)


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
    st.session_state["scr_use_ranking"] = False
    st.session_state["scr_ranking_labels"] = []
    st.session_state["scr_top_n"] = 20
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
if st.sidebar.button("🔴 프로그램 종료"):
    st.sidebar.warning("프로그램을 종료합니다. 잠시 후 이 창을 닫으셔도 됩니다.")
    import threading

    def _shutdown():
        os._exit(0)

    threading.Timer(1.5, _shutdown).start()
if st.sidebar.button("🔄 모드 변경"):
    st.session_state["_trade_mode"] = None
    st.rerun()
st.sidebar.caption(f"📅 데이터 기준: {get_data_timestamp()}")

page = st.sidebar.radio("화면 선택", ["스크리너 & 모의매매", "프리셋 비교", "백테스터"])

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
        quick_progress = st.sidebar.progress(0.0, text="빠른 새로고침 준비 중...")

        def _quick_progress_cb(step, total):
            quick_progress.progress(step / total, text=f"빠른 새로고침 중... ({step}/{total}배치)")

        result = kis_batch_refresh.main(progress_callback=_quick_progress_cb)
        quick_progress.empty()
        st.sidebar.success(f"완료! {result['success_count']}/{result['total']}개 갱신 "
                            f"({result['elapsed_sec']:.0f}초)")
        st.cache_data.clear()
        st.rerun()

    with st.sidebar.expander("🐢 재무 데이터 새로고침 (전체, ~1~1.5시간)"):
        st.caption("성장률/부채비율/유동비율/업종/회사개요/모멘텀까지 전부 갱신합니다. "
                   "시간이 오래 걸리니 실행 중 페이지를 닫지 마세요.")
        if st.button("재무 데이터 새로고침 시작"):
            import full_refresh
            full_progress = st.progress(0.0, text="재무 데이터 새로고침 준비 중...")

            step_labels = {
                "universe": "시세·PBR·PER·EPS·BPS", "momentum": "모멘텀·거래대금",
                "sector": "업종 정보", "growth": "재무제표(성장률 등)",
                "company": "회사개요", "merge": "최종 병합",
            }

            def _full_progress_cb(overall, step_name):
                label = step_labels.get(step_name, step_name)
                full_progress.progress(overall, text=f"재무 데이터 새로고침 중... {label} ({overall*100:.0f}%)")

            result = full_refresh.main(progress_callback=_full_progress_cb)
            full_progress.empty()
            st.sidebar.success(f"완료! 총 {result['elapsed_sec']/60:.1f}분 소요")
            st.cache_data.clear()
            st.rerun()

    with st.sidebar.expander("📈 과거 주가 새로고침 (백테스터용)"):
        st.caption("백테스터가 쓰는 과거 주가 데이터(historical_prices.csv)를 최신 날짜까지 채워넣습니다. "
                   "지난번 받아둔 것 이후분만 받아오는 방식이라, 자주 돌릴수록 빨라집니다 "
                   "(오래 밀려있으면 전종목 기준 20~30분 정도 걸릴 수 있어요). "
                   "이걸 오래 안 돌리면 백테스터 최근 구간 결과가 부정확해질 수 있습니다.")
        if st.button("과거 주가 새로고침 시작"):
            import build_historical_prices
            hist_progress = st.progress(0.0, text="과거 주가 새로고침 준비 중...")

            def _hist_progress_cb(step, total):
                hist_progress.progress(step / total, text=f"과거 주가 새로고침 중... ({step}/{total}종목)")

            result = build_historical_prices.main(progress_callback=_hist_progress_cb)
            hist_progress.empty()
            st.sidebar.success(
                f"완료! {result['elapsed_sec']/60:.1f}분 소요 · "
                f"{result['added_rows']:,}행 추가 · {result['skipped']}개 종목은 이미 최신이라 건너뜀"
            )
            st.rerun()

    st.divider()

    use_ranking_toggle = st.checkbox(
        "결과를 정렬해서 상위 N개만 보기 (랭킹)", key="scr_use_ranking",
        help="꺼두면: 아래 조건을 만족하는 종목을 전부 보여줍니다.\n\n"
             "켜두면: 조건을 만족하는 종목들 중, 선택한 지표들의 순위를 합산해 상위 N개만 정렬해서 보여줍니다 (마법공식 방식)."
    )
    st.caption("아래 탭의 조건은 필터로 항상 적용됩니다. 랭킹은 그 결과를 정렬해서 상위 N개만 추려주는 추가 옵션입니다.")

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

    if use_ranking_toggle:
        st.subheader("🏆 랭킹 설정")
        indicator_labels = [label for label, _, _ in RANKING_INDICATORS]
        default_labels = [l for l in indicator_labels if l.startswith(("PER", "PBR", "ROE"))]
        selected_labels = st.multiselect(
            "랭킹에 사용할 지표 (순위를 합산합니다)", indicator_labels, default=default_labels,
            key="scr_ranking_labels"
        )
        top_n = st.number_input("상위 몇 개를 추출할까요?", min_value=1, max_value=200, value=20, step=1, key="scr_top_n")

        st.caption(f"필터 통과 종목({len(hard_filtered)}개) 중, 선택한 지표가 전부 존재하는 종목만 랭킹에 포함됩니다.")

        filtered, rank_cols_for_display = rank_stocks(hard_filtered, selected_labels, top_n)

        st.subheader(f"📊 {preset_name} (정렬 상위 {len(filtered)}개)")
        col1, col2, col3 = st.columns(3)
        col1.metric("필터 통과", f"{len(hard_filtered)}개")
        col2.metric("최종 추출", f"{len(filtered)}개")
        col3.metric("전체 대상", f"{len(df)}개")
        st.caption("'최종순위'가 실제 등수(1등, 2등...)입니다. '합산순위'는 선택한 지표들의 순위를 더한 점수라 "
                   "종목마다 값이 다르며, 이 점수가 가장 낮은 종목이 최종순위 1등이 됩니다.")
    else:
        filtered = hard_filtered
        st.subheader(f"📊 {preset_name}")
        col1, col2 = st.columns(2)
        col1.metric("조건 통과 종목 수", f"{len(filtered)}개")
        col2.metric("전체 대상", f"{len(df)}개")

    display_cols = ["종목코드", "종목명", "업종명", "시장구분", "현재가", "PBR", "PER", "ROE",
                     "부채비율(%)", "유동비율(%)", "매출액성장률(%)", "영업이익성장률(%)", "3년연속흑자",
                     "3개월수익률(%)", "6개월수익률(%)", "12개월수익률(%)",
                     "시가총액", "평균거래대금(억원)"]
    if use_ranking_toggle:
        display_cols = ["최종순위", "합산순위"] + display_cols
    display_cols = [c for c in display_cols if c in filtered.columns]

    sort_col = "최종순위" if use_ranking_toggle else "시가총액"
    sort_asc = True if use_ranking_toggle else False
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

    st.divider()
    st.subheader("🔄 리밸런싱")
    st.caption("이 프리셋에 **저장된 조건**(화면에서 지금 만지고 있는 슬라이더 값이 아니라 마지막으로 저장한 조건) 기준으로, "
               "보유 종목 중 조건을 벗어난 건 팔고 새로 조건에 맞는 건 삽니다. 실행 전에 무엇을 팔고 살지 먼저 보여드리고, "
               "체크 해제한 종목은 거래하지 않습니다.")

    reb_portfolio = db.get_or_create_portfolio(preset_name)
    last_reb = reb_portfolio.get("last_rebalanced_at")
    if last_reb:
        days_since = (datetime.now() - datetime.fromisoformat(last_reb)).days
        st.caption(f"📅 마지막 리밸런싱: {last_reb[:10]} ({days_since}일 경과)")
    else:
        st.caption("📅 아직 리밸런싱을 실행한 적이 없습니다.")

    if st.button("🔄 리밸런싱 대상 확인"):
        reb_criteria = db.load_preset_criteria(preset_name)
        if reb_criteria is None:
            st.warning("이 프리셋은 아직 저장된 조건이 없습니다. 먼저 조건을 저장해주세요.")
        else:
            reb_matched = filter_stocks(df, reb_criteria)
            if reb_criteria.get("mode") == "랭킹 모드" and reb_criteria.get("ranking_labels"):
                reb_matched, _ = rank_stocks(reb_matched, reb_criteria["ranking_labels"], reb_criteria.get("top_n", 20))

            reb_passing_codes = set(reb_matched["종목코드"])
            reb_holdings_now = db.get_holdings(preset_name)
            reb_current_codes = set(reb_holdings_now["stock_code"])

            reb_to_sell = reb_holdings_now[reb_holdings_now["stock_code"].isin(reb_current_codes - reb_passing_codes)]
            reb_to_buy = reb_matched[reb_matched["종목코드"].isin(reb_passing_codes - reb_current_codes)]

            st.session_state["_rebalance_plan"] = {
                "preset_name": preset_name,
                "sell": reb_to_sell[["stock_code", "stock_name", "quantity"]].to_dict("records"),
                "buy": reb_to_buy[["종목코드", "종목명", "현재가"]].to_dict("records"),
            }
            st.rerun()

    reb_plan = st.session_state.get("_rebalance_plan")
    if reb_plan and reb_plan["preset_name"] == preset_name:
        if not reb_plan["sell"] and not reb_plan["buy"]:
            st.success("✅ 이미 조건에 다 맞습니다. 리밸런싱할 대상이 없습니다.")
            st.session_state.pop("_rebalance_plan", None)
        else:
            reb_price_map = df.set_index("종목코드")["현재가"].to_dict()

            if reb_plan["sell"]:
                st.markdown(f"**🔻 매도 예정 ({len(reb_plan['sell'])}개, 조건 이탈)**")
                for item in reb_plan["sell"]:
                    ref_price = reb_price_map.get(item["stock_code"])
                    label = f"{item['stock_name']}({item['stock_code']}) {item['quantity']}주"
                    if ref_price:
                        label += f" · 약 {ref_price:,.0f}원"
                    st.checkbox(label, value=True, key=f"reb_sell_{item['stock_code']}")

            if reb_plan["buy"]:
                st.markdown(f"**🔺 매수 예정 ({len(reb_plan['buy'])}개, 신규 조건 충족)**")
                for item in reb_plan["buy"]:
                    label = f"{item['종목명']}({item['종목코드']}) · 약 {item['현재가']:,.0f}원"
                    st.checkbox(label, value=True, key=f"reb_buy_{item['종목코드']}")

            st.caption("💡 체크 해제한 종목은 거래되지 않습니다. 매수 금액은 확정 시점의 현금을 체크된 매수 종목 수만큼 균등분배합니다.")

            col_confirm, col_cancel = st.columns(2)
            confirm_clicked = col_confirm.button("✅ 리밸런싱 확정", type="primary", key="reb_confirm_btn")
            cancel_clicked = col_cancel.button("취소", key="reb_cancel_btn")

            def _clear_rebalance_state(plan):
                for item in plan["sell"]:
                    st.session_state.pop(f"reb_sell_{item['stock_code']}", None)
                for item in plan["buy"]:
                    st.session_state.pop(f"reb_buy_{item['종목코드']}", None)
                st.session_state.pop("_rebalance_plan", None)

            if cancel_clicked:
                _clear_rebalance_state(reb_plan)
                st.rerun()

            if confirm_clicked:
                sell_items = [i for i in reb_plan["sell"] if st.session_state.get(f"reb_sell_{i['stock_code']}")]
                buy_items = [i for i in reb_plan["buy"] if st.session_state.get(f"reb_buy_{i['종목코드']}")]

                msgs = []
                if sell_items:
                    with st.spinner("매도 실시간 가격 조회 중..."):
                        sell_rt = kis.get_realtime_prices([i["stock_code"] for i in sell_items])
                    sell_orders = []
                    for i in sell_items:
                        price = sell_rt.get(i["stock_code"]) or reb_price_map.get(i["stock_code"])
                        if not price:
                            continue
                        sell_orders.append({"stock_code": i["stock_code"], "stock_name": i["stock_name"], "price": price})
                    if sell_orders:
                        ok, msg = db.sell_stocks(preset_name, sell_orders)
                        msgs.append(f"매도 - {msg}")

                if buy_items:
                    with st.spinner("매수 실시간 가격 조회 중..."):
                        buy_rt = kis.get_realtime_prices([i["종목코드"] for i in buy_items])
                    priced_buy = []
                    for i in buy_items:
                        price = buy_rt.get(i["종목코드"]) or i["현재가"]
                        if price and price > 0:
                            priced_buy.append({"stock_code": i["종목코드"], "stock_name": i["종목명"], "price": price})
                    if priced_buy:
                        cash_now = db.get_or_create_portfolio(preset_name)["cash_balance"]
                        per_stock_amount = cash_now / len(priced_buy)
                        buy_orders = []
                        for p in priced_buy:
                            qty = int(per_stock_amount // p["price"])
                            if qty > 0:
                                buy_orders.append({"stock_code": p["stock_code"], "stock_name": p["stock_name"],
                                                    "quantity": qty, "price": p["price"]})
                        if buy_orders:
                            ok, msg = db.buy_stocks(preset_name, buy_orders)
                            msgs.append(f"매수 - {msg}")

                db.mark_rebalanced(preset_name)
                _clear_rebalance_state(reb_plan)
                if not msgs:
                    st.warning("체크된 거래가 없어 아무 것도 실행하지 않았습니다.")
                else:
                    for m in msgs:
                        st.success(m)
                st.rerun()


# ══════════════════════════════════════════════════════════
# 프리셋 비교 화면
# ══════════════════════════════════════════════════════════
elif page == "프리셋 비교":
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
                "holdings_count": len(holdings), "total_asset": total_asset, "total_return": total_return,
                "holdings": holdings, "portfolio": portfolio,
            })

        # 수익률 높은 순으로 정렬해서 카드 표시
        summary_rows.sort(key=lambda r: r["total_return"], reverse=True)

        # 현재 벤치마크 ETF 가격은 한 번만 조회해서 재사용 (프리셋마다 반복 호출 방지)
        current_benchmark_prices = None

        for i, row in enumerate(summary_rows):
            with st.container(border=True):
                col0, col1, col2, col3, col4 = st.columns([0.4, 1.8, 1, 1, 1])
                with col0:
                    st.checkbox("출력용 선택", key=f"export_select_{row['name']}", label_visibility="collapsed")
                with col1:
                    rank_emoji = "🥇" if i == 0 else ("🥈" if i == 1 else ("🥉" if i == 2 else "▫️"))
                    st.markdown(f"### {rank_emoji} {row['name']}")
                col2.metric("조건 통과", f"{row['matched']}개")
                col3.metric("보유 종목", f"{row['holdings_count']}개")
                col4.metric("총 수익률", f"{row['total_return']:+.2f}%")

                last_reb = row["portfolio"].get("last_rebalanced_at")
                if last_reb:
                    days_since = (datetime.now() - datetime.fromisoformat(last_reb)).days
                    st.caption(f"📅 마지막 리밸런싱: {last_reb[:10]} ({days_since}일 경과)")
                else:
                    st.caption("📅 아직 리밸런싱을 실행한 적이 없습니다.")

                with st.expander("조건 상세 보기"):
                    for line in summarize_criteria_lines(row["criteria"]):
                        st.markdown(line)

                with st.expander(f"📦 보유 종목 상세 ({row['holdings_count']}개)"):
                    if row["holdings_count"] == 0:
                        st.caption("보유 중인 종목이 없습니다.")
                    else:
                        hv = row["holdings"].copy()
                        hv["평가금액"] = hv["quantity"] * hv["현재가"]
                        hv["수익률(%)"] = ((hv["현재가"] - hv["avg_buy_price"]) / hv["avg_buy_price"] * 100).round(2)
                        hv = hv[["stock_code", "stock_name", "quantity", "avg_buy_price", "현재가", "평가금액", "수익률(%)"]]
                        hv.columns = ["종목코드", "종목명", "수량", "평균매입가", "현재가", "평가금액", "수익률(%)"]
                        hv = format_currency_cols(hv, ["평균매입가", "현재가", "평가금액"])
                        st.dataframe(hv, use_container_width=True, hide_index=True)

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

        st.divider()
        st.subheader("📋 상태 요약 출력")
        st.caption("위에서 '출력용 선택' 체크박스로 프리셋을 고른 뒤 아래 버튼을 누르면, "
                   "조건 · 수익률 · 보유종목 · 거래내역을 정리한 텍스트가 나옵니다. "
                   "그대로 복사해서 AI(클로드, 챗GPT 등)에게 붙여넣어 상담받기 좋은 형식입니다.")

        if st.button("📋 선택한 프리셋 결과 출력"):
            selected_rows = [r for r in summary_rows if st.session_state.get(f"export_select_{r['name']}")]
            if not selected_rows:
                st.warning("먼저 출력할 프리셋을 하나 이상 선택해주세요.")
            else:
                report_blocks = []
                for row in selected_rows:
                    transactions = db.get_transactions(row["name"])
                    earliest_buy_date = db.get_earliest_buy_date(row["name"])
                    report_blocks.append(build_preset_report_text(
                        row["name"], row["criteria"], row["holdings"], row["portfolio"],
                        row["total_asset"], row["total_return"], transactions, earliest_buy_date
                    ))
                report_text = "\n\n---\n\n".join(report_blocks)
                st.text_area("아래 내용을 전체 선택(Ctrl+A) 후 복사(Ctrl+C)하세요",
                             value=report_text, height=400)


# ══════════════════════════════════════════════════════════
# 백테스터 화면
# ══════════════════════════════════════════════════════════
else:
    st.title("⏱️ 백테스터")
    st.caption("과거 특정 시점부터 이 프리셋 조건으로 매달 리밸런싱했다면 어땠을지 계산합니다. "
               "API 호출 없이 미리 받아둔 데이터로만 계산해서 몇 초~몇 분이면 끝납니다.")

    st.warning(
        "⚠️ 이 백테스트는 다음과 같은 한계가 있습니다:\n"
        "- **생존편향**: 현재 상장된 종목만 대상이라, 그 사이 상장폐지된 종목은 반영되지 않아 실제보다 유리하게 나올 수 있습니다.\n"
        "- **발행주식수**: 과거 시점이 아닌 현재 발행주식수를 사용해 시가총액/PBR/PER을 근사 계산합니다.\n"
        "- **재무데이터 공시시차**: 4월 1일을 기준으로 전년도/재작년도 실적 중 '그 시점에 이미 공시됐을' 데이터를 근사적으로 사용합니다.\n"
        "- **필터 모드 조건만 지원**: 랭킹 모드로 저장된 조건은 아직 지원하지 않습니다."
    )

    if not saved_presets:
        st.info("저장된 프리셋이 없습니다. 먼저 '스크리너 & 모의매매' 화면에서 조건을 저장해주세요.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            bt_preset = st.selectbox("백테스트할 프리셋", saved_presets, key="bt_preset_select")

        # 프리셋을 바꿨을 때만, 그 프리셋에 저장된 랭킹모드 설정을 자동으로 불러옴
        if st.session_state.get("_loaded_bt_preset") != bt_preset:
            preset_criteria = db.load_preset_criteria(bt_preset)
            if preset_criteria:
                st.session_state["bt_use_ranking"] = (preset_criteria.get("mode") == "랭킹 모드")
                st.session_state["bt_ranking_indicators"] = preset_criteria.get("ranking_labels", [])
                st.session_state["bt_top_n"] = preset_criteria.get("top_n", 20)
            st.session_state["_loaded_bt_preset"] = bt_preset

        with col2:
            months_option = st.selectbox(
                "시작 시점", [3, 6, 12, 24, 36],
                index=2, format_func=lambda m: f"{m}개월 전부터", key="bt_months_back"
            )
        with col3:
            bt_initial_amount = st.number_input(
                "시작 자금 (원)", min_value=100_000, value=10_000_000, step=1_000_000, key="bt_initial_amount"
            )

        bt_use_ranking = st.checkbox(
            "상위 N개만 골라 매달 리밸런싱 (랭킹 모드)", key="bt_use_ranking",
            help="1차 필터를 통과한 종목 중, 선택한 지표들의 순위를 합산해 상위 N개만 매달 다시 선정합니다."
        )
        bt_ranking_indicators = None
        bt_top_n = 20
        compare_n_values = []
        if bt_use_ranking:
            bt_ranking_indicators = st.multiselect(
                "랭킹에 사용할 지표", [label for label, _, _ in RANKING_INDICATORS],
                default=[l for l in [label for label, _, _ in RANKING_INDICATORS] if l.startswith(("PER", "PBR", "ROE"))],
                key="bt_ranking_indicators"
            )

            compare_n_values = st.multiselect(
                "종목 수를 바꿔가며 비교해보기 (선택하면 아래 '상위 몇 개'는 무시됩니다)",
                [3, 5, 10, 15, 20, 30, 50],
                default=[], key="bt_compare_n_values"
            )

            if not compare_n_values:
                bt_top_n = st.number_input("상위 몇 개", min_value=1, max_value=100, value=20, step=1, key="bt_top_n")

        if st.button("▶️ 백테스트 실행", type="primary"):
            criteria = db.load_preset_criteria(bt_preset)
            if criteria is None:
                st.error("이 프리셋의 조건을 불러올 수 없습니다.")
            elif bt_use_ranking and compare_n_values:
                # 종목 수 비교 모드: 여러 top_n으로 반복 실행
                progress_bar = st.progress(0.0, text="종목 수별 비교 계산 중...")
                n_list = sorted(compare_n_values)
                comparison_results = {}

                for i, n in enumerate(n_list):
                    def _update_progress(step, total, n=n, i=i):
                        overall = (i + step / total) / len(n_list)
                        progress_bar.progress(overall, text=f"{n}개 종목 기준 계산 중... ({i+1}/{len(n_list)})")

                    try:
                        comparison_results[n] = bt.run_backtest(
                            criteria, months_back=months_option,
                            initial_amount=bt_initial_amount, progress_callback=_update_progress,
                            use_ranking=True, ranking_indicators=bt_ranking_indicators, top_n=n
                        )
                    except FileNotFoundError as e:
                        st.error(f"필요한 데이터 파일을 찾을 수 없습니다: {e}")
                        comparison_results = None
                        break

                progress_bar.empty()
                st.session_state["_backtest_n_comparison"] = comparison_results
                st.session_state["_backtest_result"] = None  # 단일결과는 비교모드에서 숨김
                st.session_state["_backtest_preset_name"] = bt_preset
            else:
                progress_bar = st.progress(0.0, text="백테스트 계산 중...")

                def _update_progress(step, total):
                    progress_bar.progress(step / total, text=f"백테스트 계산 중... ({step}/{total}개월)")

                try:
                    result = bt.run_backtest(
                        criteria, months_back=months_option,
                        initial_amount=bt_initial_amount, progress_callback=_update_progress,
                        use_ranking=bt_use_ranking, ranking_indicators=bt_ranking_indicators, top_n=bt_top_n
                    )
                    progress_bar.empty()
                    st.session_state["_backtest_result"] = result
                    st.session_state["_backtest_n_comparison"] = None  # 비교모드 결과는 단일실행에서 숨김
                    st.session_state["_backtest_preset_name"] = bt_preset
                except FileNotFoundError as e:
                    progress_bar.empty()
                    st.error(f"필요한 데이터 파일을 찾을 수 없습니다: {e}\n"
                             "historical_financials.csv, historical_prices.csv가 있는지 확인해주세요.")

        result = st.session_state.get("_backtest_result")
        if result:
            st.divider()
            st.subheader(f"📊 결과: {st.session_state.get('_backtest_preset_name')}")

            col1, col2, col3 = st.columns(3)
            col1.metric("시작 자금", f"{result['initial_amount']:,.0f}원")
            col2.metric("최종 자산", f"{result['final_value']:,.0f}원")
            col3.metric("총 수익률", f"{result['final_return']:+.2f}%")

            render_data_freshness_notice(result)

            st.caption("그래프에 표시할 벤치마크 선택")
            bench_toggle_cols = st.columns(len(result["benchmarks"]))
            selected_benches_single = {}
            for i, name in enumerate(result["benchmarks"].keys()):
                selected_benches_single[name] = bench_toggle_cols[i].checkbox(
                    name, value=True, key=f"bt_single_bench_{name}"
                )

            # 차트용 데이터프레임 구성 (날짜 정규화로 시각 오차 제거)
            chart_df = normalize_date_index(pd.DataFrame(result["portfolio"]), value_col="총자산", new_name="내 프리셋")

            for name, series in result["benchmarks"].items():
                if not selected_benches_single.get(name):
                    continue
                bench_df = normalize_date_index(pd.DataFrame(series), value_col="총자산", new_name=name)
                chart_df = chart_df.join(bench_df, how="outer")

            st.line_chart(chart_df)

            st.subheader("벤치마크 대비 알파")
            for name, series in result["benchmarks"].items():
                final_bench = series[-1]["총자산"]
                if final_bench is None:
                    st.caption(f"{name}: 데이터 부족으로 비교 불가")
                    continue
                bench_return = (final_bench - result["initial_amount"]) / result["initial_amount"] * 100
                alpha = result["final_return"] - bench_return
                arrow = "▲" if alpha >= 0 else "▼"
                color = "green" if alpha >= 0 else "red"
                st.markdown(f"**{name}**: {bench_return:+.2f}% · :{color}[알파 {arrow} {alpha:+.2f}%p]")

            with st.expander("월별 상세 내역"):
                detail_df = format_currency_cols(pd.DataFrame(result["portfolio"]), ["총자산", "현금"])
                st.dataframe(detail_df, use_container_width=True, hide_index=True)

            if st.button("📋 이 백테스트 결과 출력", key="bt_export_single"):
                bt_preset_name = st.session_state.get("_backtest_preset_name")
                bt_criteria = db.load_preset_criteria(bt_preset_name)
                report_text = build_backtest_report_text(
                    bt_preset_name, bt_criteria, result["months_back"], result, "단일 실행"
                )
                st.text_area("아래 내용을 전체 선택(Ctrl+A) 후 복사(Ctrl+C)하세요",
                             value=report_text, height=300, key="bt_export_single_text")

        n_comparison = st.session_state.get("_backtest_n_comparison")
        if n_comparison:
            st.divider()
            st.subheader(f"📊 종목 수별 비교: {st.session_state.get('_backtest_preset_name')}")

            # 종목 수별 최종수익률 요약 표 (최종 자산은 콤마 포맷)
            summary_rows = []
            series_map = {}
            for n, res in sorted(n_comparison.items()):
                summary_rows.append({
                    "종목 수": n,
                    "최종 자산": f"{res['final_value']:,.0f}",
                    "총 수익률(%)": round(res["final_return"], 2)
                })
                series_map[n] = normalize_date_index(pd.DataFrame(res["portfolio"]), value_col="총자산", new_name=f"{n}개 종목")

            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

            render_data_freshness_notice(list(n_comparison.values())[0])

            if st.button("📋 종목 수별 비교 결과 출력", key="bt_export_comparison"):
                bt_preset_name = st.session_state.get("_backtest_preset_name")
                bt_criteria = db.load_preset_criteria(bt_preset_name)
                report_blocks = [
                    build_backtest_report_text(
                        bt_preset_name, bt_criteria, res["months_back"], res, f"종목 수 비교 - 상위 {n}개"
                    )
                    for n, res in sorted(n_comparison.items())
                ]
                report_text = "\n\n---\n\n".join(report_blocks)
                st.text_area("아래 내용을 전체 선택(Ctrl+A) 후 복사(Ctrl+C)하세요",
                             value=report_text, height=400, key="bt_export_comparison_text")

            st.caption("그래프에 표시할 종목 수 선택")
            n_toggle_cols = st.columns(len(series_map))
            selected_n_values = {}
            for i, n in enumerate(sorted(series_map.keys())):
                selected_n_values[n] = n_toggle_cols[i].checkbox(f"{n}개", value=True, key=f"bt_compare_n_toggle_{n}")

            chart_df = None
            for n in sorted(series_map.keys()):
                if not selected_n_values.get(n):
                    continue
                chart_df = series_map[n] if chart_df is None else chart_df.join(series_map[n], how="outer")

            # 벤치마크는 종목 수와 무관하게 동일하므로, 첫 번째 결과의 것을 재사용
            first_result = list(n_comparison.values())[0]
            st.caption("그래프에 표시할 벤치마크 선택")
            bench_toggle_cols2 = st.columns(len(first_result["benchmarks"]))
            selected_benches_compare = {}
            for i, name in enumerate(first_result["benchmarks"].keys()):
                selected_benches_compare[name] = bench_toggle_cols2[i].checkbox(
                    name, value=True, key=f"bt_compare_bench_{name}"
                )

            for name, series in first_result["benchmarks"].items():
                if not selected_benches_compare.get(name):
                    continue
                bench_df = normalize_date_index(pd.DataFrame(series), value_col="총자산", new_name=name)
                chart_df = bench_df if chart_df is None else chart_df.join(bench_df, how="outer")

            if chart_df is not None and len(chart_df.columns) > 0:
                st.line_chart(chart_df)
            else:
                st.info("표시할 항목을 하나 이상 선택해주세요.")

            st.subheader("벤치마크 대비 알파 (종목 수별)")
            alpha_rows = []
            for n, res in sorted(n_comparison.items()):
                row = {"종목 수": n, "총 수익률(%)": round(res["final_return"], 2)}
                for name, series in res["benchmarks"].items():
                    final_bench = series[-1]["총자산"]
                    if final_bench is None:
                        row[f"알파_{name}"] = None
                        continue
                    bench_return = (final_bench - res["initial_amount"]) / res["initial_amount"] * 100
                    row[f"알파_{name}"] = round(res["final_return"] - bench_return, 2)
                alpha_rows.append(row)
            st.dataframe(pd.DataFrame(alpha_rows), use_container_width=True, hide_index=True)

            st.caption("💡 종목 수를 줄일수록 수익률이 계속 좋아진다면, 이 전략은 '소수의 대박 종목'에 의존하는 저격형일 가능성이 높습니다. "
                       "종목 수를 바꿔도 수익률이 비슷하다면, 더 폭넓게 통하는 전략이라는 뜻입니다.")

            st.subheader("종목 수별 월별 보유 종목 상세")
            for n, res in sorted(n_comparison.items()):
                with st.expander(f"📦 {n}개 종목 기준 - 월별 보유 내역"):
                    detail_df = format_currency_cols(pd.DataFrame(res["portfolio"]), ["총자산", "현금"])
                    st.dataframe(detail_df, use_container_width=True, hide_index=True)