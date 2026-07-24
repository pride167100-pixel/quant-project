import os
import requests
from dotenv import load_dotenv

load_dotenv()
APP_KEY = os.getenv("KIS_APP_KEY")
APP_SECRET = os.getenv("KIS_APP_SECRET")
URL_BASE = "https://openapi.koreainvestment.com:9443"


def get_access_token():
    url = f"{URL_BASE}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    response = requests.post(url, headers=headers, json=body)
    return response.json()["access_token"]


def get_weekly_chart(token, stock_code):
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST03010100"
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
        "FID_INPUT_DATE_1": "20250101",
        "FID_INPUT_DATE_2": "20260724",
        "FID_PERIOD_DIV_CODE": "W",  # 주봉
        "FID_ORG_ADJ_PRC": "0"
    }
    response = requests.get(url, headers=headers, params=params)
    return response.json()


if __name__ == "__main__":
    token = get_access_token()
    data = get_weekly_chart(token, "005930")  # 삼성전자

    print("응답 최상위 키:", list(data.keys()))
    output1 = data.get("output1", {})
    output2 = data.get("output2", [])

    print("\noutput1 (요약 정보):", output1)
    print(f"\noutput2 (주봉 데이터 개수): {len(output2)}")
    if output2:
        print("\n가장 최근 데이터 1개:", output2[0])
        print("\n가장 오래된 데이터 1개:", output2[-1])