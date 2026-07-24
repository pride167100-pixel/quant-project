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
        "FID_PERIOD_DIV_CODE": "W",
        "FID_ORG_ADJ_PRC": "0"
    }
    response = requests.get(url, headers=headers, params=params)
    return response.json().get("output2", [])


def calc_momentum(weekly_data):
    # 날짜 오름차순 정렬 (오래된 것 -> 최근 것)
    rows = sorted(weekly_data, key=lambda r: r["stck_bsop_date"])
    closes = [float(r["stck_clpr"]) for r in rows]
    volumes_krw = [float(r["acml_tr_pbmn"]) for r in rows]

    n = len(closes)
    current_price = closes[-1]

    def pct_change(weeks_back):
        idx = n - 1 - weeks_back
        if idx < 0:
            return None
        past_price = closes[idx]
        if past_price == 0:
            return None
        return round((current_price - past_price) / past_price * 100, 2)

    momentum_3m = pct_change(13)
    momentum_6m = pct_change(26)
    momentum_12m = pct_change(52)

    recent_12w = volumes_krw[-12:] if n >= 12 else volumes_krw
    avg_daily_value_100m = round(sum(recent_12w) / len(recent_12w) / 5 / 1e8, 1) if recent_12w else None

    return {
        "현재가": current_price,
        "3개월수익률(%)": momentum_3m,
        "6개월수익률(%)": momentum_6m,
        "12개월수익률(%)": momentum_12m,
        "평균거래대금(억원)": avg_daily_value_100m,
        "데이터개수": n,
    }


if __name__ == "__main__":
    token = get_access_token()
    weekly = get_weekly_chart(token, "005930")
    result = calc_momentum(weekly)
    print("=== 삼성전자(005930) 모멘텀 계산 결과 ===")
    for k, v in result.items():
        print(f"{k}: {v}")