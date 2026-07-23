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


def to_number(val):
    if val is None or val == "":
        return None
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None


def get_financials(corp_code, bsns_year="2025", reprt_code="11011"):
    """연결재무제표(CFS) 우선 조회, 없으면 개별재무제표(OFS)로 재시도"""
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"

    for fs_div in ["CFS", "OFS"]:
        params = {
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": fs_div
        }
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=5)
            data = response.json()

            if data.get("status") != "000":
                continue  # 데이터 없음 -> 다음 fs_div 시도

            items = data.get("list", [])
            revenue_this, revenue_prev = None, None
            profit_this, profit_prev = None, None

            for item in items:
                if item.get("sj_div") != "IS":
                    continue
                name = item.get("account_nm", "")
                if name == "매출액":
                    revenue_this = to_number(item.get("thstrm_amount"))
                    revenue_prev = to_number(item.get("frmtrm_amount"))
                elif name == "영업이익":
                    profit_this = to_number(item.get("thstrm_amount"))
                    profit_prev = to_number(item.get("frmtrm_amount"))

            if revenue_this is not None or profit_this is not None:
                return {
                    "재무제표종류": fs_div,
                    "매출액_당기": revenue_this,
                    "매출액_전기": revenue_prev,
                    "영업이익_당기": profit_this,
                    "영업이익_전기": profit_prev,
                }
        except Exception:
            continue

    return {
        "재무제표종류": None,
        "매출액_당기": None, "매출액_전기": None,
        "영업이익_당기": None, "영업이익_전기": None,
    }


def calc_growth(this, prev):
    if this is None or prev is None or prev == 0:
        return None
    return round((this - prev) / abs(prev) * 100, 2)


def main():
    start_time = datetime.now()
    print("시작 시각:", start_time.strftime("%H:%M:%S"))

    stocks = pd.read_csv("all_stocks.csv", dtype={"종목코드": str})
    corp_map = pd.read_csv("dart_corp_codes.csv", dtype={"종목코드": str, "고유번호": str})

    merged = stocks.merge(corp_map[["종목코드", "고유번호"]], on="종목코드", how="left")
    no_match = merged["고유번호"].isna().sum()
    print(f"대상 종목 수: {len(merged)} / DART 매핑 안된 종목: {no_match}")

    results = []
    total = len(merged)

    for idx, row in merged.iterrows():
        corp_code = row["고유번호"]
        if pd.isna(corp_code):
            results.append({
                "재무제표종류": None, "매출액_당기": None, "매출액_전기": None,
                "영업이익_당기": None, "영업이익_전기": None,
            })
        else:
            info = get_financials(corp_code)
            results.append(info)
            time.sleep(0.2)

        if (idx + 1) % 100 == 0 or (idx + 1) == total:
            print(f"진행: {idx + 1} / {total}")

        if (idx + 1) % 500 == 0:
            temp = pd.concat([merged.iloc[:idx + 1].reset_index(drop=True),
                               pd.DataFrame(results)], axis=1)
            temp.to_csv("growth_checkpoint.csv", index=False, encoding="utf-8-sig")

    growth_df = pd.DataFrame(results)
    final = pd.concat([merged.reset_index(drop=True), growth_df], axis=1)

    final["매출액성장률(%)"] = final.apply(lambda r: calc_growth(r["매출액_당기"], r["매출액_전기"]), axis=1)
    final["영업이익성장률(%)"] = final.apply(lambda r: calc_growth(r["영업이익_당기"], r["영업이익_전기"]), axis=1)

    final.to_csv("growth_data.csv", index=False, encoding="utf-8-sig")

    elapsed = (datetime.now() - start_time).total_seconds()
    success = final["매출액_당기"].notna().sum() + final["영업이익_당기"].notna().sum()
    print(f"\n완료! 소요시간: {elapsed:.1f}초 ({elapsed/60:.1f}분)")
    print(f"growth_data.csv 저장됨, 총 {len(final)}개 종목")
    print(final[["종목코드", "종목명", "매출액성장률(%)", "영업이익성장률(%)"]].head(10))


if __name__ == "__main__":
    main()