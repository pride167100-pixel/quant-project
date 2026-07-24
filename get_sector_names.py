import requests
import zipfile
import pandas as pd

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def download_sector_master():
    url = "https://new.real.download.dws.co.kr/common/master/idxcode.mst.zip"
    zip_path = "idxcode.zip"

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        print("다운로드 상태 코드:", response.status_code)
    except Exception as e:
        print("다운로드 중 에러 발생:", e)
        raise

    with open(zip_path, "wb") as f:
        f.write(response.content)

    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(".")
        print("압축 해제 완료 -> idxcode.mst 생성됨")
    except zipfile.BadZipFile as e:
        print("압축 해제 실패:", e)
        print("응답 내용 앞부분:", response.content[:200])
        raise


def parse_sector_master(file_path="idxcode.mst"):
    codes = []
    names = []
    with open(file_path, mode="r", encoding="cp949") as f:
        for row in f:
            code = row[1:5].strip()
            name = row[3:43].strip()
            codes.append(code)
            names.append(name)

    df = pd.DataFrame({"업종코드": codes, "업종명": names})
    df = df.drop_duplicates(subset="업종코드").reset_index(drop=True)
    return df


def extract_stock_sector_codes(file_path, part_len):
    """종목코드 + 지수업종대분류(offset 3~6) + 지수업종중분류(offset 7~10) 추출"""
    data = []
    with open(file_path, mode="r", encoding="cp949") as f:
        for row in f:
            stock_code = row[0:9].strip()
            part2 = row[-part_len:]
            major_code = part2[3:7].strip()
            mid_code = part2[7:11].strip()
            data.append({"종목코드": stock_code, "대분류코드": major_code, "중분류코드": mid_code})
    return pd.DataFrame(data)


def main():
    print("=== 1단계: 업종코드 매핑표 다운로드 ===")
    download_sector_master()
    sector_master = parse_sector_master()
    print(f"업종코드 매핑 개수: {len(sector_master)}\n")

    print("=== 2단계: 종목별 업종코드 추출 ===")
    kospi_sectors = extract_stock_sector_codes("kospi_code.mst", part_len=228)
    kosdaq_sectors = extract_stock_sector_codes("kosdaq_code.mst", part_len=222)
    all_sectors = pd.concat([kospi_sectors, kosdaq_sectors], ignore_index=True)
    print(f"전체 종목 수(펀드/ETF 포함): {len(all_sectors)}\n")

    print("=== 3단계: 업종명 매칭 ===")
    merged = all_sectors.merge(
        sector_master.rename(columns={"업종코드": "중분류코드", "업종명": "중분류명"}),
        on="중분류코드", how="left"
    )
    merged = merged.merge(
        sector_master.rename(columns={"업종코드": "대분류코드", "업종명": "대분류명"}),
        on="대분류코드", how="left"
    )
    merged["업종명"] = merged["중분류명"].fillna(merged["대분류명"])

    final = merged[["종목코드", "업종명"]]
    final.to_csv("sector_info.csv", index=False, encoding="utf-8-sig")

    print(f"최종 저장 완료: sector_info.csv")
    print(f"업종명 매칭 성공: {final['업종명'].notna().sum()} / {len(final)}")
    print("\n[샘플]")
    print(final.head(15))


if __name__ == "__main__":
    main()