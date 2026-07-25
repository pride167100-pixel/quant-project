import os
import time
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
APP_KEY = os.getenv("KIS_APP_KEY")
APP_SECRET = os.getenv("KIS_APP_SECRET")
URL_BASE = "https://openapi.koreainvestment.com:9443"


@st.cache_resource(ttl=60 * 60 * 20)  # 20시간 캐시 (토큰 유효기간 24시간보다 짧게)
def get_token():
    """접속 토큰 발급. 20시간 이내 재호출 시 캐시된 토큰 재사용 (하루 발급 제한 보호)"""
    url = f"{URL_BASE}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}
    response = requests.post(url, headers=headers, json=body, timeout=5)
    response.raise_for_status()
    return response.json()["access_token"]


def get_realtime_price(stock_code, max_retries=2):
    """종목 하나의 실시간 현재가를 조회. 실패 시 None 반환"""
    token = get_token()
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
            if data.get("msg_cd") == "EGW00201":  # 속도제한
                time.sleep(0.5 + attempt)
                continue
            price = data.get("output", {}).get("stck_prpr")
            return float(price) if price else None
        except Exception:
            time.sleep(0.3)
            continue
    return None


def get_multi_prices(stock_codes, max_retries=3):
    """최대 30종목씩 묶어서 한 번에 조회. {종목코드: 가격} 딕셔너리 반환"""
    token = get_token()
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
    for i, code in enumerate(stock_codes, start=1):
        params[f"FID_COND_MRKT_DIV_CODE_{i}"] = "J"
        params[f"FID_INPUT_ISCD_{i}"] = code

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=5)
            data = response.json()
            if data.get("msg_cd") == "EGW00201":
                time.sleep(0.5 + attempt)
                continue
            result = {}
            for item in data.get("output", []):
                code = item.get("inter_shrn_iscd")
                if not code:
                    continue
                try:
                    result[code] = float(item.get("inter2_prpr", 0))
                except (ValueError, TypeError):
                    result[code] = None
            return result
        except Exception:
            time.sleep(0.3)
            continue
    return {}


def get_realtime_prices(stock_codes):
    """여러 종목의 실시간 현재가를 딕셔너리로 반환 {종목코드: 가격} (30개씩 묶어서 일괄조회)"""
    result = {}
    stock_codes = list(dict.fromkeys(stock_codes))  # 중복 제거, 순서 유지
    for i in range(0, len(stock_codes), 30):
        chunk = stock_codes[i:i + 30]
        result.update(get_multi_prices(chunk))
        time.sleep(0.1)
    # 혹시 응답에서 누락된 종목코드는 None으로 채워서 호출부에서 안전하게 처리되도록 함
    for code in stock_codes:
        result.setdefault(code, None)
    return result