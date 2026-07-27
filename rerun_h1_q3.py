"""
반기/3분기 데이터만 재수집 (누적값 버그 수정 반영).
1분기/연간 데이터는 문제없어서 그대로 두고, 이 4개 조합만 다시 받는다.
"""
from build_quarterly_financials import collect_one_combo
import pandas as pd
from datetime import datetime

REPORT_CONFIGS = [("11012", "반기"), ("11014", "3분기")]
ANCHOR_YEARS = ["2025", "2023"]


def main():
    start = datetime.now()
    print("반기/3분기 재수집 시작 (누적값 버그 수정):", start.strftime("%H:%M:%S"))

    stocks = pd.read_csv("all_stocks.csv", dtype={"종목코드": str})
    corp_map = pd.read_csv("dart_corp_codes.csv", dtype={"종목코드": str, "고유번호": str})

    for reprt_code, report_name in REPORT_CONFIGS:
        for anchor_year in ANCHOR_YEARS:
            print(f"\n{report_name}보고서 - 기준연도 {anchor_year}")
            collect_one_combo(stocks, corp_map, anchor_year, reprt_code, report_name)

    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n완료! 총 소요시간: {elapsed/60:.1f}분")


if __name__ == "__main__":
    main()