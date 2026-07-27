"""
8개의 분기별 재무데이터 파일을 하나의 '재무 이벤트 타임라인'으로 합친다.
각 종목마다 "언제, 어떤 보고서가, 어떤 실적을 담아 공시됐는지"를 시간순으로 정리해서,
백테스터가 특정 과거 날짜에 '그 시점까지 공시된 가장 최근 실적'을 정확히 찾을 수 있게 한다.
"""
import pandas as pd
from datetime import datetime

# (보고서명, 파일명 접두어, 예상 공시일 생성 함수)
REPORT_CONFIGS = [
    ("1분기", lambda y: datetime(y, 6, 1)),
    ("반기", lambda y: datetime(y, 9, 1)),
    ("3분기", lambda y: datetime(y, 12, 1)),
    ("연간", lambda y: datetime(y + 1, 4, 1)),
]
ANCHOR_YEARS = [2025, 2023]

METRICS = ["매출액", "영업이익", "당기순이익", "부채총계", "자본총계", "유동자산", "유동부채"]


def load_all_quarterly_files():
    """8개 파일을 다 읽어서 하나의 딕셔너리로: {(보고서명, 종목코드, 연도): {지표: 값}}"""
    data = {}
    for report_name, _ in REPORT_CONFIGS:
        for anchor_year in ANCHOR_YEARS:
            filename = f"quarterly_financials_{report_name}_{anchor_year}.csv"
            try:
                df = pd.read_csv(filename, dtype={"종목코드": str})
            except FileNotFoundError:
                print(f"⚠️ 파일 없음: {filename} (건너뜀)")
                continue

            for _, row in df.iterrows():
                code = row["종목코드"]
                for year in [anchor_year, anchor_year - 1]:
                    key = (report_name, code, year)
                    if key in data:
                        continue  # 이미 다른 anchor_year에서 확보된 경우 중복 방지
                    values = {}
                    for metric in METRICS:
                        col = f"{metric}_{year}"
                        values[metric] = row[col] if col in df.columns and pd.notna(row.get(col)) else None
                    data[key] = values
    return data


def add_ttm_and_growth(timeline):
    """
    각 보고서 시점마다:
    - '전년동기' 값(같은 보고서종류의 1년 전 수치) → 성장률 계산에 사용
    - '전년도 연간' 값 → TTM(최근 12개월 누적) 계산에 사용
    TTM = 전년도 연간 실적 + 이번 누적 실적 - 전년동기 누적 실적
    (연간 보고서 자체는 이 공식이 자동으로 '그 해 전체값'과 같아져서 별도 예외처리가 필요 없음)
    """
    flow_metrics = ["매출액", "영업이익", "당기순이익"]

    # 전년동기(같은 보고서종류, 1년 전) 값 붙이기
    prev_same_type = timeline.copy()
    prev_same_type["회계연도"] = prev_same_type["회계연도"] + 1
    prev_same_type = prev_same_type[["종목코드", "보고서종류", "회계연도"] + flow_metrics]
    prev_same_type = prev_same_type.rename(columns={m: f"전년동기_{m}" for m in flow_metrics})
    timeline = timeline.merge(prev_same_type, on=["종목코드", "보고서종류", "회계연도"], how="left")

    # 전년도 '연간' 실적 붙이기 (TTM 계산용)
    prev_annual = timeline[timeline["보고서종류"] == "연간"][["종목코드", "회계연도"] + flow_metrics].copy()
    prev_annual["회계연도"] = prev_annual["회계연도"] + 1
    prev_annual = prev_annual.rename(columns={m: f"전년도연간_{m}" for m in flow_metrics})
    timeline = timeline.merge(prev_annual, on=["종목코드", "회계연도"], how="left")

    for m in flow_metrics:
        # TTM(최근 12개월 누적)
        timeline[f"TTM_{m}"] = timeline[f"전년도연간_{m}"] + timeline[m] - timeline[f"전년동기_{m}"]
        # 전년동기 대비 성장률(%)
        prev_col = f"전년동기_{m}"
        timeline[f"{m}성장률(%)"] = (
            (timeline[m] - timeline[prev_col]) / timeline[prev_col].abs() * 100
        ).round(2)

    # 중간 계산용 컬럼 정리
    drop_cols = [f"전년동기_{m}" for m in flow_metrics] + [f"전년도연간_{m}" for m in flow_metrics]
    timeline = timeline.drop(columns=drop_cols)
    return timeline


def main():
    print("시작:", datetime.now().strftime("%H:%M:%S"))

    static_info = pd.read_csv("all_stocks.csv", dtype={"종목코드": str})[["종목코드", "종목명"]]
    all_data = load_all_quarterly_files()

    events = []
    for report_name, disclose_fn in REPORT_CONFIGS:
        years_covered = set()
        for anchor_year in ANCHOR_YEARS:
            years_covered.add(anchor_year)
            years_covered.add(anchor_year - 1)

        for year in years_covered:
            disclose_date = disclose_fn(year)
            for _, row in static_info.iterrows():
                code = row["종목코드"]
                key = (report_name, code, year)
                values = all_data.get(key)
                if values is None or all(v is None for v in values.values()):
                    continue

                event = {
                    "종목코드": code, "종목명": row["종목명"],
                    "보고서종류": report_name, "회계연도": year,
                    "공시일_추정": disclose_date,
                }
                event.update(values)
                events.append(event)

    timeline = pd.DataFrame(events)
    timeline = add_ttm_and_growth(timeline)
    timeline = timeline.sort_values(["종목코드", "공시일_추정"]).reset_index(drop=True)
    timeline.to_csv("financial_timeline.csv", index=False, encoding="utf-8-sig")

    print(f"완료! financial_timeline.csv 저장됨, 총 {len(timeline)}행")
    print(f"고유 종목 수: {timeline['종목코드'].nunique()}")
    print("\n[샘플: 삼성전자 타임라인]")
    sample = timeline[timeline["종목코드"] == "005930"][
        ["보고서종류", "회계연도", "공시일_추정", "매출액", "영업이익", "당기순이익",
         "TTM_매출액", "TTM_영업이익", "TTM_당기순이익", "매출액성장률(%)", "영업이익성장률(%)"]
    ]
    print(sample.to_string(index=False))


if __name__ == "__main__":
    main()