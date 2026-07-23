import os
import requests
import zipfile
import xml.etree.ElementTree as ET
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
DART_API_KEY = os.getenv("DART_API_KEY")

def download_corp_codes():
    print("키 길이:", len(DART_API_KEY) if DART_API_KEY else "None")
    print("키 앞 4자리:", DART_API_KEY[:4] if DART_API_KEY else "None")
    print("키 마지막 4자리:", repr(DART_API_KEY[-4:]) if DART_API_KEY else "None")

    url = "https://opendart.fss.or.kr/api/corpCode.xml"
    params = {"crtfc_key": DART_API_KEY}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    response = requests.get(url, params=params, headers=headers)
    print("실제 요청 URL:", response.url)
    print("상태 코드:", response.status_code)
    zip_path = "corpCode.zip"
    with open(zip_path, "wb") as f:
        f.write(response.content)

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(".")
        print("압축 해제 성공 -> CORPCODE.xml 생성됨")
        return True
    except zipfile.BadZipFile:
        print("\n압축 파일이 아닙니다.")
        response.encoding = "utf-8"
        text = response.text
        import re
        alert_msgs = re.findall(r'class="alert"[^>]*>(.*?)<', text, re.DOTALL)
        info_msgs = re.findall(r'class="info[^"]*"[^>]*>(.*?)<', text, re.DOTALL)
        print("alert 메시지:", [m.strip() for m in alert_msgs])
        print("info 메시지:", [m.strip() for m in info_msgs])
        return False

def parse_corp_codes():
    tree = ET.parse("CORPCODE.xml")
    root = tree.getroot()

    data = []
    for item in root.findall("list"):
        corp_code = item.findtext("corp_code")
        corp_name = item.findtext("corp_name")
        stock_code = item.findtext("stock_code")
        data.append({"고유번호": corp_code, "회사명": corp_name, "종목코드": stock_code})

    df = pd.DataFrame(data)
    # 종목코드가 있는 것 = 실제 상장회사만
    listed_df = df[df["종목코드"].str.strip() != ""].copy()

    listed_df.to_csv("dart_corp_codes.csv", index=False, encoding="utf-8-sig")
    print(f"\n전체 항목 수: {len(df)}")
    print(f"상장회사 수(종목코드 있음): {len(listed_df)}")
    print(listed_df.head())


if __name__ == "__main__":
    if download_corp_codes():
        parse_corp_codes()