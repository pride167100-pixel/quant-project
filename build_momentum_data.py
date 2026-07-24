import os
import time
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()
APP_KEY = os.getenv("KIS_APP_KEY")
APP_SECRET = os.getenv("KIS_APP_SECRET")
URL_BASE = "https://openapi.koreainvestment.com:9443"


def get_access_token():
    url = f"{URL_BASE}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()
    return response.json()["access_token"]


def get_weekly_chart(token, stock_code, date_from, date_to, max_retries=3):
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
        "FID_INPUT_DATE_1": date_from,
        "FID_INPUT_DATE_2": date_to,
        "FID_PERIOD_DIV_CODE": "W",
        "FID_ORG_ADJ_PRC": "0"
    }
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=5)
            data = response.json()
            if data.get("msg_cd") == "EGW00201":  # 속도제한
                time.sleep(1.0 + attempt)
                continue
            return data.get("output2", [])
        except Exception:
            time.sleep(0.5)
            continue
    return []


def calc_momentum(weekly_data):
    if not weekly_data:
        return {"3개월수익률(%)": None, "6개월수익률(%)": None, "12개월수익률(%)": None, "평균거래대금(억원)": None}

    rows = sorted(weekly_data, key=lambda r: r["stck_bsop_date"])
    try:
        closes = [float(r["stck_clpr"]) for r in rows]
        volumes_krw = [float(r["acml_tr_pbmn"]) for r in rows]
    except (ValueError, KeyError):
        return {"3개월수익률(%)": None, "6개월수익률(%)": None, "12개월수익률(%)": None, "평균거래대금(억원)": None}

    n = len(closes)
    if n == 0 or closes[-1] == 0:
        return {"3개월수익률(%)": None, "6개월수익률(%)": None, "12개월수익률(%)": None, "평균거래대금(억원)": None}

    current_price = closes[-1]

    def pct_change(weeks_back):
        idx = n - 1 - weeks_back
        if idx < 0:
            return None
        past_price = closes[idx]
        if past_price == 0:
            return None
        return round((current_price - past_price) / past_price * 100, 2)

    recent_12w = volumes_krw[-12:] if n >= 1 else []
    avg_daily_value_100m = round(sum(recent_12w) / len(recent_12w) / 5 / 1e8, 1) if recent_12w else None

    return {
        "3개월수익률(%)": pct_change(13),
        "6개월수익률(%)": pct_change(26),
        "12개월수익률(%)": pct_change(52),
        "평균거래대금(억원)": avg_daily_value_100m,
    }


def main():
    start_time = datetime.now()
    print("시작 시각:", start_time.strftime("%H:%M:%S"))

    stocks = pd.read_csv("all_stocks.csv", dtype={"종목코드": str})
    total = len(stocks)
    print(f"대상 종목 수: {total}")

    token = get_access_token()

    date_to = datetime.now().strftime("%Y%m%d")
    date_from = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")

    results = []
    for idx, row in stocks.iterrows():
        code = row["종목코드"]
        weekly = get_weekly_chart(token, code, date_from, date_to)
        info = calc_momentum(weekly)
        results.append(info)

        if (idx + 1) % 100 == 0 or (idx + 1) == total:
            print(f"진행: {idx + 1} / {total}")

        if (idx + 1) % 500 == 0:
            temp = pd.concat([stocks.iloc[:idx + 1][["종목코드"]].reset_index(drop=True),
                               pd.DataFrame(results)], axis=1)
            temp.to_csv("momentum_checkpoint.csv", index=False, encoding="utf-8-sig")

        time.sleep(0.2)

    momentum_df = pd.DataFrame(results)
    final = pd.concat([stocks[["종목코드"]].reset_index(drop=True), momentum_df], axis=1)
    final.to_csv("momentum_data.csv", index=False, encoding="utf-8-sig")

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n완료! 소요시간: {elapsed:.1f}초 ({elapsed/60:.1f}분)")
    print("momentum_data.csv 저장됨")
    print(final.head(10))
    print("\n[각 지표별 정상 데이터 개수]")
    for col in ["3개월수익률(%)", "6개월수익률(%)", "12개월수익률(%)", "평균거래대금(억원)"]:
        print(f"  {col}: {final[col].notna().sum()} / {len(final)}")


if __name__ == "__main__":
    main()