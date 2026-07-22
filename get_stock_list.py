import requests
import zipfile
import os

def download_master_file(market="kospi"):
    """코스피 또는 코스닥 종목마스터 파일을 다운로드"""
    url = f"https://new.real.download.dws.co.kr/common/master/{market}_code.mst.zip"
    zip_path = f"{market}_code.mst.zip"
    
    response = requests.get(url)
    print(f"{market} 다운로드 상태 코드:", response.status_code)
    
    if response.status_code == 200:
        with open(zip_path, "wb") as f:
            f.write(response.content)
        
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(".")
        
        print(f"{market} 마스터 파일 다운로드 및 압축 해제 완료")
        return True
    else:
        print(f"{market} 다운로드 실패")
        return False

if __name__ == "__main__":
    download_master_file("kospi")
    download_master_file("kosdaq")