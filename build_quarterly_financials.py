"""
백테스터 정밀화용 분기별 재무데이터 수집 (밤새 실행용).
1분기/반기/3분기/연간 보고서 x 2개 기준연도(2025, 2023) = 총 8번의 전종목 수집을 자동으로 순차 실행.
각 조합마다 결과를 즉시 저장하므로, 중간에 멈춰도 그때까지 완료된 분량은 안전하게 남습니다.
"""
import os
import time
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
DART_API_KEY = os.getenv("DART_API_KEY")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# (보고서코드, 이름) - 분기 보고서는 당기/전기 2개년만 제공됨
REPORT_TYPES = [
    ("11013", "1분기"),
    ("11012", "반기"),
    ("11014", "3분기"),
    ("11011", "연간"),
]
ANCHOR_YEARS = ["2025", "2023"]  # 이 두 기준연도로 조회하면 2022~2025년이 다 커버됨

IS_TARGETS = {"매출액": "매출액", "영업이익": "영업이익", "당기순이익(손실)": "당기순이익"}
BS_TARGETS = {"부채총계": "부채총계", "자본총계": "자본총계", "유동자산": "유동자산", "유동부채": "유동부채"}


def to_number(val):
    if val is None or val == "":
        return None
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None


def get_financials(corp_code, bsns_year, reprt_code):
    """당기(요청연도)/전기(요청연도-1) 2개 기간의 재무데이터 추출"""
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"
    Y = int(bsns_year)
    years = [Y, Y - 1]
    period_keys = ["thstrm_amount", "frmtrm_amount"]

    for fs_div in ["CFS", "OFS"]:
        params = {
            "crtfc_key": DART_API_KEY, "corp_code": corp_code,
            "bsns_year": str(bsns_year), "reprt_code": reprt_code, "fs_div": fs_div
        }
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=5)
            data = response.json()
            if data.get("status") != "000":
                continue

            result = {"재무제표종류": fs_div}
            found_any = False
            seen_keys = set()

            for item in data.get("list", []):
                sj = item.get("sj_div")
                raw_name = item.get("account_nm", "")

                if sj == "IS" and raw_name in IS_TARGETS:
                    clean_name = IS_TARGETS[raw_name]
                elif sj == "BS" and raw_name in BS_TARGETS:
                    clean_name = BS_TARGETS[raw_name]
                else:
                    continue

                if clean_name in seen_keys:
                    continue
                seen_keys.add(clean_name)

                for year, pkey in zip(years, period_keys):
                    val = to_number(item.get(pkey))
                    if val is not None:
                        found_any = True
                    result[f"{clean_name}_{year}"] = val

            if found_any:
                return result
        except Exception:
            continue

    return {"재무제표종류": None}


def collect_one_combo(stocks, corp_map, bsns_year, reprt_code, report_name):
    """한 조합(보고서종류 x 기준연도)에 대해 전종목 수집"""
    merged = stocks.merge(corp_map[["종목코드", "고유번호"]], on="종목코드", how="left")
    total = len(merged)
    results = []

    for idx, row in merged.iterrows():
        corp_code = row["고유번호"]
        if pd.isna(corp_code):
            results.append({"재무제표종류": None})
        else:
            results.append(get_financials(corp_code, bsns_year, reprt_code))
            time.sleep(0.2)

        if (idx + 1) % 300 == 0 or (idx + 1) == total:
            print(f"    진행: {idx + 1} / {total}")

    fin_df = pd.DataFrame(results)
    final = pd.concat([merged[["종목코드", "종목명"]].reset_index(drop=True), fin_df], axis=1)

    filename = f"quarterly_financials_{report_name}_{bsns_year}.csv"
    final.to_csv(filename, index=False, encoding="utf-8-sig")
    print(f"    저장 완료: {filename}")
    return final


def main():
    overall_start = datetime.now()
    print("=" * 60)
    print("분기별 재무데이터 수집 시작 (밤새 실행용, 총 8개 조합)")
    print("시작 시각:", overall_start.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    stocks = pd.read_csv("all_stocks.csv", dtype={"종목코드": str})
    corp_map = pd.read_csv("dart_corp_codes.csv", dtype={"종목코드": str, "고유번호": str})

    combo_num = 0
    total_combos = len(REPORT_TYPES) * len(ANCHOR_YEARS)

    for reprt_code, report_name in REPORT_TYPES:
        for anchor_year in ANCHOR_YEARS:
            combo_num += 1
            combo_start = datetime.now()
            print(f"\n[{combo_num}/{total_combos}] {report_name}보고서 - 기준연도 {anchor_year} 시작 "
                  f"({combo_start.strftime('%H:%M:%S')})")

            try:
                collect_one_combo(stocks, corp_map, anchor_year, reprt_code, report_name)
            except Exception as e:
                print(f"    !! 이 조합에서 에러 발생, 건너뜀: {e}")
                continue

            elapsed = (datetime.now() - combo_start).total_seconds()
            print(f"    이 조합 소요시간: {elapsed/60:.1f}분")

    overall_elapsed = (datetime.now() - overall_start).total_seconds()
    print("\n" + "=" * 60)
    print(f"전체 완료! 총 소요시간: {overall_elapsed/60:.1f}분 ({overall_elapsed/3600:.1f}시간)")
    print("=" * 60)


if __name__ == "__main__":
    main()