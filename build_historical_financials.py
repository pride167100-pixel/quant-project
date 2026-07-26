"""
백테스터용 과거 재무데이터 수집.
DART 재무제표 API 한 번 호출로 당기/전기/전전기(3개년) 데이터를 동시에 받아,
연도별 ROE/부채비율/유동비율/성장률까지 계산해서 저장한다.

사용법:
  python build_historical_financials.py 2025   → 2023,2024,2025년 데이터 확보
  python build_historical_financials.py 2023   → 2021,2022,2023년 데이터 확보
(두 번 실행하면 2021~2025년 5개년치가 모두 확보됨)
"""
import os
import sys
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


def to_number(val):
    if val is None or val == "":
        return None
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None


def get_financials_full(corp_code, bsns_year, reprt_code="11011"):
    """당기(Y)/전기(Y-1)/전전기(Y-2) 3개년의 매출액/영업이익/당기순이익/부채총계/자본총계/유동자산/유동부채를 모두 추출"""
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"
    Y = int(bsns_year)
    years = [Y, Y - 1, Y - 2]
    period_keys = ["thstrm_amount", "frmtrm_amount", "bfefrmtrm_amount"]

    # (DART 실제 계정과목명, 우리가 쓸 컬럼명) 매핑 - 당기순이익은 "(손실)"이 붙은 실제 명칭 사용
    is_targets = {"매출액": "매출액", "영업이익": "영업이익", "당기순이익(손실)": "당기순이익"}
    bs_targets = {"부채총계": "부채총계", "자본총계": "자본총계", "유동자산": "유동자산", "유동부채": "유동부채"}

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
            seen_keys = set()  # 같은 계정과목이 중복 등장하면 첫 값만 사용

            for item in data.get("list", []):
                sj = item.get("sj_div")
                raw_name = item.get("account_nm", "")

                if sj == "IS" and raw_name in is_targets:
                    clean_name = is_targets[raw_name]
                elif sj == "BS" and raw_name in bs_targets:
                    clean_name = bs_targets[raw_name]
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


def calc_growth(this, prev):
    if this is None or prev is None or prev == 0:
        return None
    return round((this - prev) / abs(prev) * 100, 2)


def calc_ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator == 0:
        return None
    return round(numerator / denominator * 100, 2)


def main(bsns_year=None):
    if bsns_year is None:
        if len(sys.argv) < 2:
            print("사용법: python build_historical_financials.py <연도>  예) python build_historical_financials.py 2025")
            return
        bsns_year = sys.argv[1]

    Y = int(bsns_year)
    start_time = datetime.now()
    print(f"=== {Y}년 기준 재무데이터 수집 시작 ({Y-2}~{Y}년치 확보) ===")
    print("시작 시각:", start_time.strftime("%H:%M:%S"))

    stocks = pd.read_csv("all_stocks.csv", dtype={"종목코드": str})
    corp_map = pd.read_csv("dart_corp_codes.csv", dtype={"종목코드": str, "고유번호": str})
    merged = stocks.merge(corp_map[["종목코드", "고유번호"]], on="종목코드", how="left")

    results = []
    total = len(merged)

    for idx, row in merged.iterrows():
        corp_code = row["고유번호"]
        if pd.isna(corp_code):
            results.append({"재무제표종류": None})
        else:
            results.append(get_financials_full(corp_code, bsns_year))
            time.sleep(0.2)

        if (idx + 1) % 100 == 0 or (idx + 1) == total:
            print(f"진행: {idx + 1} / {total}")

        if (idx + 1) % 500 == 0:
            temp = pd.concat([merged.iloc[:idx + 1][["종목코드"]].reset_index(drop=True),
                               pd.DataFrame(results)], axis=1)
            temp.to_csv(f"historical_financials_{Y}_checkpoint.csv", index=False, encoding="utf-8-sig")

    fin_df = pd.DataFrame(results)
    final = pd.concat([merged[["종목코드", "종목명"]].reset_index(drop=True), fin_df], axis=1)

    # 연도별 비율/성장률 계산
    for year in [Y, Y - 1, Y - 2]:
        final[f"ROE_{year}"] = final.apply(
            lambda r: calc_ratio(r.get(f"당기순이익_{year}"), r.get(f"자본총계_{year}")), axis=1)
        final[f"부채비율_{year}"] = final.apply(
            lambda r: calc_ratio(r.get(f"부채총계_{year}"), r.get(f"자본총계_{year}")), axis=1)
        final[f"유동비율_{year}"] = final.apply(
            lambda r: calc_ratio(r.get(f"유동자산_{year}"), r.get(f"유동부채_{year}")), axis=1)

    for year in [Y, Y - 1]:
        final[f"매출액성장률_{year}"] = final.apply(
            lambda r: calc_growth(r.get(f"매출액_{year}"), r.get(f"매출액_{year-1}")), axis=1)
        final[f"영업이익성장률_{year}"] = final.apply(
            lambda r: calc_growth(r.get(f"영업이익_{year}"), r.get(f"영업이익_{year-1}")), axis=1)

    output_path = f"historical_financials_{Y}.csv"
    final.to_csv(output_path, index=False, encoding="utf-8-sig")

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n완료! 소요시간: {elapsed/60:.1f}분")
    print(f"저장됨: {output_path}")
    print(f"\n[샘플] {Y}년 기준 ROE 정상 데이터: {final[f'ROE_{Y}'].notna().sum()} / {len(final)}")
    print(final[["종목코드", "종목명", f"ROE_{Y}", f"부채비율_{Y}", f"매출액성장률_{Y}"]].head(10))


if __name__ == "__main__":
    main()