import os
import time
import pandas as pd
import requests
from dotenv import load_dotenv
from datetime import datetime

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


def to_number(val):
    """문자열 숫자를 float으로 안전하게 변환. 실패하면 None."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def get_price_info(token, stock_code, max_retries=3):
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST01010100"
    }
    params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code}

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=5)
            data = response.json()

            if data.get("msg_cd") == "EGW00201":
                time.sleep(1.0 + attempt)
                continue

            output = data.get("output", {})
            return {
                "현재가": to_number(output.get("stck_prpr")),
                "PER": to_number(output.get("per")),
                "PBR": to_number(output.get("pbr")),
                "EPS": to_number(output.get("eps")),
                "BPS": to_number(output.get("bps")),
                "등락률": to_number(output.get("prdy_ctrt")),
            }
        except Exception:
            time.sleep(0.5)
            continue

    return {"현재가": None, "PER": None, "PBR": None, "EPS": None, "BPS": None, "등락률": None}


def main():
    start_time = datetime.now()
    print("시작 시각:", start_time.strftime("%H:%M:%S"))

    df = pd.read_csv("universe_full.csv", dtype={"종목코드": str})

    # 값을 넣을 컬럼들을 미리 float 타입(NaN 허용)으로 확실히 맞춰둠
    for col in ["현재가", "PER", "PBR", "EPS", "BPS", "등락률"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    failed_idx = df[df["현재가"].isna()].index
    print(f"재시도 대상: {len(failed_idx)}개")

    token = get_access_token()

    for i, idx in enumerate(failed_idx):
        code = df.at[idx, "종목코드"]
        info = get_price_info(token, code)
        for key, val in info.items():
            df.at[idx, key] = val

        if (i + 1) % 20 == 0 or (i + 1) == len(failed_idx):
            print(f"재시도 진행: {i + 1} / {len(failed_idx)}")

        time.sleep(0.3)

    df.to_csv("universe_full.csv", index=False, encoding="utf-8-sig")

    still_failed = df["현재가"].isna().sum()
    end_time = datetime.now()
    elapsed = (end_time - start_time).total_seconds()

    print(f"\n완료! 총 소요시간: {elapsed:.1f}초 ({elapsed/60:.1f}분)")
    print(f"여전히 실패한 종목 수: {still_failed}")
    if still_failed > 0:
        print(df[df["현재가"].isna()][["종목코드", "종목명"]])


if __name__ == "__main__":
    main()