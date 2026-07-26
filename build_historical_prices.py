"""
백테스터용 과거 주가 이력 수집.
전 종목 + 벤치마크 3종(코스피200/코스닥150/S&P500)의 최근 3.1년치 주봉(종가+거래대금)을 수집.
"""
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

BACKTEST_BENCHMARK_CODES = {
    "코스피": "069500",
    "코스닥": "229200",
    "S&P500": "360200",
}


def get_access_token():
    url = f"{URL_BASE}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    response = requests.post(url, headers=headers, json=body, timeout=5)
    response.raise_for_status()
    return response.json()["access_token"]


def get_weekly_chart(token, stock_code, date_from, date_to, max_retries=3):
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY, "appsecret": APP_SECRET,
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
            if data.get("msg_cd") == "EGW00201":
                time.sleep(0.5 + attempt)
                continue
            return data.get("output2", [])
        except Exception:
            time.sleep(0.3)
            continue
    return []


def get_full_weekly_history(token, stock_code, earliest_target_date, latest_date):
    """API 1회 호출당 최대 100행 제한을 우회하기 위해, 여러 구간으로 나눠 요청해서 합침"""
    all_rows = []
    seen_dates = set()
    current_end = latest_date

    for _ in range(6):  # 안전장치: 최대 6번 반복 (95주씩 6번 = 약 11년, 3.1년엔 충분)
        if current_end <= earliest_target_date:
            break
        current_start = max(earliest_target_date, current_end - timedelta(weeks=95))
        rows = get_weekly_chart(
            token, stock_code,
            current_start.strftime("%Y%m%d"), current_end.strftime("%Y%m%d")
        )
        if not rows:
            break

        new_rows = [r for r in rows if r["stck_bsop_date"] not in seen_dates]
        for r in new_rows:
            seen_dates.add(r["stck_bsop_date"])
        all_rows.extend(new_rows)

        earliest_received = min(datetime.strptime(r["stck_bsop_date"], "%Y%m%d") for r in rows)
        if earliest_received >= current_end:
            break  # 진전이 없으면 무한루프 방지를 위해 종료
        current_end = earliest_received - timedelta(days=1)

        if len(rows) < 90:
            break  # 받은 행이 적으면 더 오래된 데이터가 없다고 보고 종료

        time.sleep(0.1)  # 같은 종목에 대한 추가 호출 사이 딜레이

    return all_rows


def main():
    start_time = datetime.now()
    print("시작 시각:", start_time.strftime("%H:%M:%S"))

    stocks = pd.read_csv("all_stocks.csv", dtype={"종목코드": str})
    all_codes = list(stocks["종목코드"]) + list(BACKTEST_BENCHMARK_CODES.values())
    total = len(all_codes)
    print(f"대상: 종목 {len(stocks)}개 + 벤치마크 {len(BACKTEST_BENCHMARK_CODES)}개 = 총 {total}개")

    token = get_access_token()
    latest_date = datetime.now()
    earliest_target_date = datetime.now() - timedelta(days=int(365 * 3.1))

    all_rows = []
    for idx, code in enumerate(all_codes):
        weekly = get_full_weekly_history(token, code, earliest_target_date, latest_date)
        for row in weekly:
            try:
                all_rows.append({
                    "종목코드": code,
                    "날짜": row["stck_bsop_date"],
                    "종가": float(row["stck_clpr"]),
                    "거래대금": float(row.get("acml_tr_pbmn", 0)),
                })
            except (ValueError, KeyError):
                continue

        if (idx + 1) % 100 == 0 or (idx + 1) == total:
            print(f"진행: {idx + 1} / {total}")

        if (idx + 1) % 500 == 0:
            pd.DataFrame(all_rows).to_csv("historical_prices_checkpoint.csv", index=False, encoding="utf-8-sig")

        time.sleep(0.1)

    result_df = pd.DataFrame(all_rows)
    result_df.to_csv("historical_prices.csv", index=False, encoding="utf-8-sig")

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n완료! 소요시간: {elapsed/60:.1f}분")
    print(f"historical_prices.csv 저장됨, 총 {len(result_df)}행")
    print(f"종목별 평균 데이터 포인트 수: {len(result_df) / total:.1f}개")

    date_check = pd.to_datetime(result_df["날짜"], format="%Y%m%d")
    print(f"수집된 전체 날짜 범위: {date_check.min()} ~ {date_check.max()}")


if __name__ == "__main__":
    main()