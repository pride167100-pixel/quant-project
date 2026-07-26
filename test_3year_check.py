import os
import requests
from dotenv import load_dotenv

load_dotenv()
DART_API_KEY = os.getenv("DART_API_KEY")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def get_financials(corp_code, bsns_year="2025", reprt_code="11011", fs_div="CFS"):
    url = "https://opendart.fss.or.kr/api/fnlttSinglAcnt.json"
    params = {
        "crtfc_key": DART_API_KEY,
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": reprt_code,
        "fs_div": fs_div
    }
    response = requests.get(url, params=params, headers=HEADERS, timeout=5)
    return response.json()


if __name__ == "__main__":
    data = get_financials("00126380")
    items = data.get("list", [])

    # 손익계산서(IS) 전체 계정과목 이름을 다 출력
    print("=== 손익계산서(IS) 전체 계정과목 ===")
    for item in items:
        if item.get("sj_div") == "IS":
            print(item.get("account_nm"))