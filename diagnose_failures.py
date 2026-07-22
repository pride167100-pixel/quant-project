import os
import time
import pandas as pd
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
    response.raise_for_status()
    return response.json()["access_token"]


def check_stock(token, stock_code):
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
    data = response.json()
    return {
        "종목코드": stock_code,
        "http상태": response.status_code,
        "rt_cd": data.get("rt_cd"),
        "msg_cd": data.get("msg_cd"),
        "메시지": data.get("msg1"),
    }


def main():
    df = pd.read_csv("universe_full.csv", dtype={"종목코드": str})
    failed = df[df["현재가"].isna()]
    print(f"실패 종목 수: {len(failed)}")

    token = get_access_token()
    results = []

    # 실패 종목 중 앞 20개만 우선 원인 확인 (전수조사는 시간 걸려서 샘플만)
    sample = failed.head(20)
    for _, row in sample.iterrows():
        info = check_stock(token, row["종목코드"])
        info["종목명"] = row["종목명"]
        results.append(info)
        print(info)
        time.sleep(0.15)

    result_df = pd.DataFrame(results)
    result_df.to_csv("failure_diagnosis_sample.csv", index=False, encoding="utf-8-sig")
    print("\n샘플 진단 결과가 failure_diagnosis_sample.csv에 저장되었습니다.")
    print("\n[메시지별 개수]")
    print(result_df["메시지"].value_counts())


if __name__ == "__main__":
    main()