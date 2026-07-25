"""벤치마크 ETF의 특정 날짜 종가 / 현재가 조회"""
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from benchmark_config import BENCHMARK_ETFS
import kis_realtime

load_dotenv()
APP_KEY = os.getenv("KIS_APP_KEY")
APP_SECRET = os.getenv("KIS_APP_SECRET")
URL_BASE = "https://openapi.koreainvestment.com:9443"


def get_access_token():
    """토큰 재발급 대신 kis_realtime의 캐시된 토큰을 재사용 (하루 발급 제한 보호)"""
    return kis_realtime.get_token()


def get_current_price(token, stock_code):
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY, "appsecret": APP_SECRET,
        "tr_id": "FHKST01010100"
    }
    params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        price = response.json().get("output", {}).get("stck_prpr")
        return float(price) if price else None
    except Exception:
        return None


def get_price_on_date(token, stock_code, target_date):
    """target_date: datetime 객체. 그 날짜 또는 그 이전 가장 가까운 거래일 종가를 반환"""
    url = f"{URL_BASE}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": APP_KEY, "appsecret": APP_SECRET,
        "tr_id": "FHKST03010100"
    }
    date_to = target_date.strftime("%Y%m%d")
    date_from = (target_date - timedelta(days=14)).strftime("%Y%m%d")
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
        "FID_INPUT_DATE_1": date_from,
        "FID_INPUT_DATE_2": date_to,
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "0"
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        rows = response.json().get("output2", [])
        if not rows:
            return None
        rows_sorted = sorted(rows, key=lambda r: r["stck_bsop_date"])
        return float(rows_sorted[-1]["stck_clpr"])  # target_date에 가장 가까운(이전) 거래일 종가
    except Exception:
        return None


def get_all_current_prices():
    token = get_access_token()
    return {name: get_current_price(token, code) for name, code in BENCHMARK_ETFS.items()}


def get_all_prices_on_date(target_date):
    token = get_access_token()
    return {name: get_price_on_date(token, code, target_date) for name, code in BENCHMARK_ETFS.items()}