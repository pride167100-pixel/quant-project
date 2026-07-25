import os
import requests
from dotenv import load_dotenv
from benchmark_config import BENCHMARK_ETFS

load_dotenv()
APP_KEY = os.getenv("KIS_APP_KEY")
APP_SECRET = os.getenv("KIS_APP_SECRET")
URL_BASE = "https://openapi.koreainvestment.com:9443"


def get_access_token():
    url = f"{URL_BASE}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    response = requests.post(url, headers=headers, json=body, timeout=5)
    response.raise_for_status()
    return response.json()["access_token"]


def get_price_info(token, stock_code):
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST01010100"
    }
    params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code}
    response = requests.get(url, headers=headers, params=params, timeout=5)
    return response.json()


if __name__ == "__main__":
    token = get_access_token()
    for name, code in BENCHMARK_ETFS.items():
        data = get_price_info(token, code)
        output = data.get("output", {})
        stock_name = output.get("hts_kor_isnm", "(이름 조회 실패)")
        price = output.get("stck_prpr", "(가격 조회 실패)")
        print(f"{name} ({code}) -> 종목명: {stock_name}, 현재가: {price}")