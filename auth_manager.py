"""
첫 실행 시 API키 입력 + 비밀번호 설정, 이후 실행 시 비밀번호 로그인을 처리하는 모듈.
※ 이 잠금은 "혼자 쓰는 로컬 컴퓨터"를 전제로 한 가벼운 보호 장치입니다.
   .env 파일 자체를 직접 열어보면 우회 가능한 수준이며, 그 이상의 강한 보안은 목적하지 않습니다.
"""
import os
import hashlib
import secrets
from pathlib import Path

ENV_PATH = ".env"
REQUIRED_KEYS = ["KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO", "DART_API_KEY"]


def _read_env_dict():
    """지금 .env 파일 내용을 딕셔너리로 읽음 (없으면 빈 딕셔너리)"""
    env_vars = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


def _write_env_dict(env_vars):
    """딕셔너리를 .env 파일로 통째로 다시 씀"""
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        for key, value in env_vars.items():
            f.write(f"{key}={value}\n")


def is_configured():
    """필수 API키가 전부 .env에 설정되어 있는지 확인"""
    env_vars = _read_env_dict()
    return all(env_vars.get(key) for key in REQUIRED_KEYS)


def has_password():
    env_vars = _read_env_dict()
    return bool(env_vars.get("APP_PASSWORD_HASH"))


def _hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000).hex()


def save_credentials(kis_app_key, kis_app_secret, kis_account_no, dart_api_key, password):
    """API키 4종 + 비밀번호(해시로 저장)를 .env에 저장"""
    env_vars = _read_env_dict()
    env_vars["KIS_APP_KEY"] = kis_app_key.strip()
    env_vars["KIS_APP_SECRET"] = kis_app_secret.strip()
    env_vars["KIS_ACCOUNT_NO"] = kis_account_no.strip()
    env_vars["DART_API_KEY"] = dart_api_key.strip()

    salt = secrets.token_hex(16)
    env_vars["APP_PASSWORD_SALT"] = salt
    env_vars["APP_PASSWORD_HASH"] = _hash_password(password, salt)

    _write_env_dict(env_vars)


def update_api_keys_only(kis_app_key, kis_app_secret, kis_account_no, dart_api_key):
    """비밀번호는 그대로 두고 API키만 갱신 (API 재설정 버튼용)"""
    env_vars = _read_env_dict()
    env_vars["KIS_APP_KEY"] = kis_app_key.strip()
    env_vars["KIS_APP_SECRET"] = kis_app_secret.strip()
    env_vars["KIS_ACCOUNT_NO"] = kis_account_no.strip()
    env_vars["DART_API_KEY"] = dart_api_key.strip()
    _write_env_dict(env_vars)


def verify_password(password):
    env_vars = _read_env_dict()
    salt = env_vars.get("APP_PASSWORD_SALT", "")
    stored_hash = env_vars.get("APP_PASSWORD_HASH", "")
    if not salt or not stored_hash:
        return False
    return _hash_password(password, salt) == stored_hash


def verify_kis_credentials(app_key, app_secret):
    """한투 API키가 실제로 유효한지 토큰 발급을 시도해서 확인"""
    import requests
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret}
    try:
        response = requests.post(url, headers=headers, json=body, timeout=10)
        data = response.json()
        if "access_token" in data:
            return True, "한투 API 인증 성공"
        return False, f"한투 API 인증 실패: {data.get('error_description', data.get('msg1', '알 수 없는 오류'))}"
    except Exception as e:
        return False, f"한투 API 연결 오류: {e}"


def verify_dart_credentials(dart_api_key):
    """DART 인증키가 실제로 유효한지 삼성전자 회사개요 조회를 시도해서 확인"""
    import requests
    url = "https://opendart.fss.or.kr/api/company.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    params = {"crtfc_key": dart_api_key, "corp_code": "00126380"}  # 삼성전자로 테스트
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        data = response.json()
        if data.get("status") == "000":
            return True, "DART API 인증 성공"
        return False, f"DART API 인증 실패: {data.get('message', '알 수 없는 오류')}"
    except Exception as e:
        return False, f"DART API 연결 오류: {e}"


def verify_all_credentials(kis_app_key, kis_app_secret, dart_api_key):
    """한투 + DART 둘 다 검증. 하나라도 실패하면 실패로 처리"""
    kis_ok, kis_msg = verify_kis_credentials(kis_app_key, kis_app_secret)
    if not kis_ok:
        return False, kis_msg
    dart_ok, dart_msg = verify_dart_credentials(dart_api_key)
    if not dart_ok:
        return False, dart_msg
    return True, "한투 · DART API 모두 인증에 성공했습니다."


def get_current_keys():
    """현재 저장된 API키 값들을 반환 (재설정 화면에서 기존 값 보여줄 때 사용)"""
    env_vars = _read_env_dict()
    return {
        "kis_app_key": env_vars.get("KIS_APP_KEY", ""),
        "kis_app_secret": env_vars.get("KIS_APP_SECRET", ""),
        "kis_account_no": env_vars.get("KIS_ACCOUNT_NO", ""),
        "dart_api_key": env_vars.get("DART_API_KEY", ""),
    }