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


def get_company_overview(corp_code):
    url = "https://opendart.fss.or.kr/api/company.json"
    params = {"crtfc_key": DART_API_KEY, "corp_code": corp_code}
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=5)
        data = response.json()
        if data.get("status") != "000":
            return {"대표자": None, "설립일": None, "주소": None}
        return {
            "대표자": data.get("ceo_nm"),
            "설립일": data.get("est_dt"),
            "주소": data.get("adres"),
        }
    except Exception:
        return {"대표자": None, "설립일": None, "주소": None}


def main(progress_callback=None):
    start_time = datetime.now()
    print("시작 시각:", start_time.strftime("%H:%M:%S"))

    stocks = pd.read_csv("all_stocks.csv", dtype={"종목코드": str})
    corp_map = pd.read_csv("dart_corp_codes.csv", dtype={"종목코드": str, "고유번호": str})
    merged = stocks.merge(corp_map[["종목코드", "고유번호"]], on="종목코드", how="left")

    results = []
    total = len(merged)

    for idx, row in merged.iterrows():
        corp_code = row["고유번호"]
        if pd.isna(corp_code):
            results.append({"대표자": None, "설립일": None, "주소": None})
        else:
            results.append(get_company_overview(corp_code))
            time.sleep(0.2)

        if (idx + 1) % 100 == 0 or (idx + 1) == total:
            print(f"진행: {idx + 1} / {total}")
        if progress_callback:
            progress_callback(idx + 1, total)

        if (idx + 1) % 500 == 0:
            temp = pd.concat([merged.iloc[:idx + 1][["종목코드"]].reset_index(drop=True),
                               pd.DataFrame(results)], axis=1)
            temp.to_csv("company_info_checkpoint.csv", index=False, encoding="utf-8-sig")

    info_df = pd.DataFrame(results)
    final = pd.concat([merged[["종목코드"]].reset_index(drop=True), info_df], axis=1)
    final.to_csv("company_info.csv", index=False, encoding="utf-8-sig")

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n완료! 소요시간: {elapsed:.1f}초 ({elapsed/60:.1f}분)")
    print("company_info.csv 저장됨")
    print(final.head(10))


if __name__ == "__main__":
    main()