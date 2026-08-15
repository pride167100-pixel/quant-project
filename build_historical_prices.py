"""
백테스터용 과거 주가 이력 수집 (증분 방식).
전 종목 + 벤치마크 3종(코스피200/코스닥150/S&P500)의 주봉(종가+거래대금)을 수집한다.
기존 historical_prices.csv가 있으면 종목별로 '마지막으로 수집된 날짜 이후'분만 받아서
이어붙이고, 파일이 없거나 신규 상장이라 이력이 아예 없는 종목만 최근 3.1년치를
처음부터 받는다. 예전에는 실행할 때마다 전종목을 통째로 다시 받아서 수십 분씩
걸렸는데, 이렇게 하면 한 번 밀린 걸 따라잡고 나면 이후로는 최근 며칠~몇 주치만
받으면 되므로 훨씬 빨라진다.
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

OUTPUT_FILE = "historical_prices.csv"
FULL_HISTORY_YEARS = 3.1
# 이 안에 이미 수집된 데이터가 있으면 "최신"이라고 보고 건너뜀 (주봉이라 이보다 촘촘히 받을 이유가 없음)
MIN_STALE_DAYS_TO_REFETCH = 7


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


def load_existing_prices():
    """기존 historical_prices.csv를 읽어 반환. 없으면 빈 데이터프레임."""
    try:
        return pd.read_csv(OUTPUT_FILE, dtype={"종목코드": str})
    except FileNotFoundError:
        return pd.DataFrame(columns=["종목코드", "날짜", "종가", "거래대금"])


def get_last_dates(existing_df):
    """종목코드별 마지막으로 수집된 날짜를 {종목코드: datetime} 딕셔너리로 반환"""
    if existing_df.empty:
        return {}
    parsed_dates = pd.to_datetime(existing_df["날짜"], format="%Y%m%d")
    return parsed_dates.groupby(existing_df["종목코드"]).max().to_dict()


def main(progress_callback=None):
    start_time = datetime.now()
    print("시작 시각:", start_time.strftime("%H:%M:%S"))

    stocks = pd.read_csv("all_stocks.csv", dtype={"종목코드": str})
    all_codes = list(stocks["종목코드"]) + list(BACKTEST_BENCHMARK_CODES.values())
    total = len(all_codes)

    existing_df = load_existing_prices()
    last_dates = get_last_dates(existing_df)
    print(f"기존 데이터: {len(existing_df)}행, {len(last_dates)}개 종목")
    print(f"대상: 종목 {len(stocks)}개 + 벤치마크 {len(BACKTEST_BENCHMARK_CODES)}개 = 총 {total}개 (신규/갱신분만 수집)")

    token = get_access_token()
    latest_date = datetime.now()
    full_backfill_start = latest_date - timedelta(days=int(365 * FULL_HISTORY_YEARS))

    new_rows = []
    skipped = 0
    for idx, code in enumerate(all_codes):
        last_date = last_dates.get(code)
        if last_date is not None:
            if (latest_date - last_date).days < MIN_STALE_DAYS_TO_REFETCH:
                skipped += 1
                if progress_callback:
                    progress_callback(idx + 1, total)
                continue
            fetch_from = last_date + timedelta(days=1)  # 이미 있는 마지막 날짜 다음날부터만
        else:
            fetch_from = full_backfill_start  # 이력이 아예 없는 종목(신규상장 등) - 처음부터 받음

        weekly = get_full_weekly_history(token, code, fetch_from, latest_date)
        for row in weekly:
            try:
                new_rows.append({
                    "종목코드": code,
                    "날짜": row["stck_bsop_date"],
                    "종가": float(row["stck_clpr"]),
                    "거래대금": float(row.get("acml_tr_pbmn", 0)),
                })
            except (ValueError, KeyError):
                continue

        if (idx + 1) % 100 == 0 or (idx + 1) == total:
            print(f"진행: {idx + 1} / {total} (건너뜀 {skipped}개)")

        if (idx + 1) % 500 == 0 and new_rows:
            # 중간에 끊겨도 그때까지 받은 신규분은 살리기 위한 체크포인트
            checkpoint = pd.concat([existing_df, pd.DataFrame(new_rows)], ignore_index=True)
            checkpoint = checkpoint.drop_duplicates(subset=["종목코드", "날짜"], keep="last")
            checkpoint.to_csv("historical_prices_checkpoint.csv", index=False, encoding="utf-8-sig")

        if progress_callback:
            progress_callback(idx + 1, total)

        time.sleep(0.1)

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        # 혹시 겹치는 날짜가 있으면(재시도 등) 새로 받은 값으로 덮어씀
        combined = combined.drop_duplicates(subset=["종목코드", "날짜"], keep="last")
        combined = combined.sort_values(["종목코드", "날짜"]).reset_index(drop=True)
    else:
        combined = existing_df

    combined.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n완료! 소요시간: {elapsed/60:.1f}분")
    print(f"{OUTPUT_FILE} 저장됨, 총 {len(combined)}행 (이번에 {len(new_rows)}행 추가, {skipped}개 종목은 이미 최신이라 건너뜀)")

    date_check = pd.to_datetime(combined["날짜"], format="%Y%m%d")
    print(f"수집된 전체 날짜 범위: {date_check.min()} ~ {date_check.max()}")

    return {"elapsed_sec": elapsed, "added_rows": len(new_rows), "skipped": skipped, "total_rows": len(combined)}


if __name__ == "__main__":
    main()