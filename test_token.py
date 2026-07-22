import os
import requests
from dotenv import load_dotenv

# .env 파일에서 키 불러오기
load_dotenv()

APP_KEY = os.getenv("KIS_APP_KEY")
APP_SECRET = os.getenv("KIS_APP_SECRET")

# 한투 실전투자 API 서버 주소
URL_BASE = "https://openapi.koreainvestment.com:9443"

def get_access_token():
    url = f"{URL_BASE}/oauth2/tokenP"
    headers = {"content-type": "application/json"}
    body = {
        "grant_type": "client_credentials",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET
    }
    response = requests.post(url, headers=headers, json=body)
    
    print("상태 코드:", response.status_code)
    print("응답 내용:", response.json())

if __name__ == "__main__":
    get_access_token()