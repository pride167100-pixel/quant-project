import os
import time
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

APP_KEY = os.getenv("KIS_APP_KEY")
APP_SECRET = os.getenv("KIS_APP_SECRET")
URL_BASE = "https://openapi.koreainvestment.com:9443"

# ── 1. 토큰 발급 (한 번만) ──────────────────────────────
def get_access_token():
    url = f"{URL_BASE}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()
    return response.json()["access_token"]


# ── 2. 종목 1개 시세/지표 조회 ──────────────────────────
def get_price_info(token, stock_code):
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST01010100"
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        data = response.json()
        output = data.get("output", {})
        return {
            "현재가": output.get("stck_prpr"),
            "PER": output.get("per"),
            "PBR": output.get("pbr"),
            "EPS": output.get("eps"),
            "BPS": output.get("bps"),
            "등락률": output.get("prdy_ctrt"),
        }
    except Exception as e:
        return {"현재가": None, "PER": None, "PBR": None, "EPS": None, "BPS": None, "등락률": None}


# ── 3. 전체 종목 순회 ────────────────────────────────────
def main(progress_callback=None):
    universe = pd.read_csv("all_stocks.csv", dtype={"종목코드": str})
    print(f"대상 종목 수: {len(universe)}")

    token = get_access_token()
    print("토큰 발급 완료. 시세 조회 시작...\n")

    results = []
    total = len(universe)

    for idx, row in universe.iterrows():
        code = row["종목코드"]
        info = get_price_info(token, code)
        results.append(info)

        # 진행상황 표시 (100개마다)
        if (idx + 1) % 100 == 0 or (idx + 1) == total:
            print(f"진행: {idx + 1} / {total}")
        if progress_callback:
            progress_callback(idx + 1, total)

        # 중간 저장 (500개마다 체크포인트 — 중간에 끊겨도 복구 가능)
        if (idx + 1) % 500 == 0:
            temp_df = pd.concat([universe.iloc[:idx + 1].reset_index(drop=True),
                                  pd.DataFrame(results)], axis=1)
            temp_df.to_csv("universe_checkpoint.csv", index=False, encoding="utf-8-sig")

        time.sleep(0.15)  # 호출 제한 방지용 딜레이

    # ── 4. 최종 병합 및 저장 ────────────────────────────
    price_df = pd.DataFrame(results)
    final_df = pd.concat([universe.reset_index(drop=True), price_df], axis=1)
    final_df.to_csv("universe_full.csv", index=False, encoding="utf-8-sig")

    print("\n완료! universe_full.csv 저장됨")
    print(final_df.head(10))


if __name__ == "__main__":
    main()