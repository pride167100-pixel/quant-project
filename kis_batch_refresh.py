"""
빠른 새로고침: 관심종목(멀티종목) 시세조회 API로 현재가를 일괄 조회하고,
저장된 EPS/BPS(재무 새로고침 시점 값)를 이용해 PER/PBR을 재계산한다.
EPS/BPS 자체는 갱신하지 않음 (그건 재무 새로고침의 역할).
"""
import os
import time
import requests
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime
import merge_data

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


def get_multi_price(token, code_chunk, max_retries=3):
    """최대 30종목을 한 번에 조회. code_chunk: 종목코드 문자열 리스트"""
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/intstock-multprice"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
        "tr_id": "FHKST11300006",
        "custtype": "P",
    }
    params = {}
    for i, code in enumerate(code_chunk, start=1):
        params[f"FID_COND_MRKT_DIV_CODE_{i}"] = "J"
        params[f"FID_INPUT_ISCD_{i}"] = code

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=5)
            data = response.json()
            if data.get("msg_cd") == "EGW00201":
                time.sleep(0.5 + attempt)
                continue
            output = data.get("output", [])
            result = {}
            for item in output:
                code = item.get("inter_shrn_iscd")
                if not code:
                    continue
                try:
                    price = float(item.get("inter2_prpr", 0))
                except (ValueError, TypeError):
                    price = None
                try:
                    change = float(item.get("prdy_ctrt", 0))
                except (ValueError, TypeError):
                    change = None
                result[code] = {"현재가": price, "등락률": change}
            return result
        except Exception:
            time.sleep(0.3)
            continue
    return {}


def chunked(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def main(progress_callback=None):
    start_time = datetime.now()
    print("시작 시각:", start_time.strftime("%H:%M:%S"))

    universe = pd.read_csv("universe_full.csv", dtype={"종목코드": str})
    print(f"대상 종목 수: {len(universe)}")

    token = get_access_token()
    codes = universe["종목코드"].tolist()
    chunks = list(chunked(codes, 30))
    print(f"총 {len(chunks)}번의 배치 호출로 진행합니다 (30종목씩)")

    all_prices = {}
    for i, chunk in enumerate(chunks):
        result = get_multi_price(token, chunk)
        all_prices.update(result)
        if (i + 1) % 20 == 0 or (i + 1) == len(chunks):
            print(f"진행: {i + 1} / {len(chunks)} 배치")
        if progress_callback:
            progress_callback(i + 1, len(chunks))
        time.sleep(0.07)  # 초당 20건 제한 대비 여유

    # 새 가격 반영 + EPS/BPS는 기존 값 그대로 사용해 PER/PBR 재계산
    def update_row(row):
        info = all_prices.get(row["종목코드"])
        if not info or info["현재가"] is None:
            return row  # 조회 실패 시 기존 값 유지
        new_price = info["현재가"]
        row["현재가"] = new_price
        row["등락률"] = info["등락률"] if info["등락률"] is not None else row.get("등락률")

        eps = row.get("EPS")
        bps = row.get("BPS")
        row["PER"] = round(new_price / eps, 2) if eps and eps != 0 else row.get("PER")
        row["PBR"] = round(new_price / bps, 2) if bps and bps != 0 else row.get("PBR")
        return row

    universe = universe.apply(update_row, axis=1)
    universe.to_csv("universe_full.csv", index=False, encoding="utf-8-sig")

    success_count = sum(1 for v in all_prices.values() if v["현재가"] is not None)
    print(f"\n가격 갱신 성공: {success_count} / {len(universe)}")

    print("\n최종 데이터 병합 중...")
    merge_data.main()

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n빠른 새로고침 완료! 총 소요시간: {elapsed:.1f}초 ({elapsed / 60:.1f}분)")
    return {"elapsed_sec": elapsed, "success_count": success_count, "total": len(universe)}


if __name__ == "__main__":
    main()