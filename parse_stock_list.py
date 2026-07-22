import pandas as pd
import os

def parse_kospi_master(file_path="kospi_code.mst"):
    tmp_fil1 = "kospi_code_part1.tmp"
    tmp_fil2 = "kospi_code_part2.tmp"

    wf1 = open(tmp_fil1, mode="w", encoding="utf-8")
    wf2 = open(tmp_fil2, mode="w", encoding="utf-8")

    with open(file_path, mode="r", encoding="cp949") as f:
        for row in f:
            rf1 = row[0:len(row) - 228]
            rf1_1 = rf1[0:9].rstrip()
            rf1_2 = rf1[9:21].rstrip()
            rf1_3 = rf1[21:].strip()
            wf1.write(rf1_1 + ',' + rf1_2 + ',' + rf1_3 + '\n')
            rf2 = row[-228:]
            wf2.write(rf2)

    wf1.close()
    wf2.close()

    part1_columns = ['종목코드', '표준코드', '종목명']
    df1 = pd.read_csv(tmp_fil1, header=None, names=part1_columns, encoding='utf-8')

    field_specs = [2, 1, 4, 4, 4,
                   1, 1, 1, 1, 1,
                   1, 1, 1, 1, 1,
                   1, 1, 1, 1, 1,
                   1, 1, 1, 1, 1,
                   1, 1, 1, 1, 1,
                   1, 9, 5, 5, 1,
                   1, 1, 2, 1, 1,
                   1, 2, 2, 2, 3,
                   1, 3, 12, 12, 8,
                   15, 21, 2, 7, 1,
                   1, 1, 1, 1, 9,
                   9, 9, 5, 9, 8,
                   9, 3, 1, 1, 1]

    part2_columns = ['그룹코드', '시가총액규모', '지수업종대분류', '지수업종중분류', '지수업종소분류',
                     '제조업', '저유동성', '지배구조지수종목', 'KOSPI200섹터업종', 'KOSPI100',
                     'KOSPI50', 'KRX', 'ETP', 'ELW발행', 'KRX100',
                     'KRX자동차', 'KRX반도체', 'KRX바이오', 'KRX은행', 'SPAC',
                     'KRX에너지화학', 'KRX철강', '단기과열', 'KRX미디어통신', 'KRX건설',
                     'Non1', 'KRX증권', 'KRX선박', 'KRX섹터_보험', 'KRX섹터_운송',
                     'SRI', '기준가', '매매수량단위', '시간외수량단위', '거래정지',
                     '정리매매', '관리종목', '시장경고', '경고예고', '불성실공시',
                     '우회상장', '락구분', '액면변경', '증자구분', '증거금비율',
                     '신용가능', '신용기간', '전일거래량', '액면가', '상장일자',
                     '상장주수', '자본금', '결산월', '공모가', '우선주',
                     '공매도과열', '이상급등', 'KRX300', 'KOSPI', '매출액',
                     '영업이익', '경상이익', '당기순이익', 'ROE', '기준년월',
                     '시가총액', '그룹사코드', '회사신용한도초과', '담보대출가능', '대주가능']

    df2 = pd.read_fwf(tmp_fil2, widths=field_specs, names=part2_columns)
    df = pd.merge(df1, df2, how='outer', left_index=True, right_index=True)
    df["시장구분"] = "KOSPI"

    os.remove(tmp_fil1)
    os.remove(tmp_fil2)
    return df


def parse_kosdaq_master(file_path="kosdaq_code.mst"):
    tmp_fil1 = "kosdaq_code_part1.tmp"
    tmp_fil2 = "kosdaq_code_part2.tmp"

    wf1 = open(tmp_fil1, mode="w", encoding="utf-8")
    wf2 = open(tmp_fil2, mode="w", encoding="utf-8")

    with open(file_path, mode="r", encoding="cp949") as f:
        for row in f:
            rf1 = row[0:len(row) - 222]
            rf1_1 = rf1[0:9].rstrip()
            rf1_2 = rf1[9:21].rstrip()
            rf1_3 = rf1[21:].strip()
            wf1.write(rf1_1 + ',' + rf1_2 + ',' + rf1_3 + '\n')
            rf2 = row[-222:]
            wf2.write(rf2)

    wf1.close()
    wf2.close()

    part1_columns = ['종목코드', '표준코드', '종목명']
    df1 = pd.read_csv(tmp_fil1, header=None, names=part1_columns, encoding='utf-8')

    field_specs = [2, 1,
                   4, 4, 4, 1, 1,
                   1, 1, 1, 1, 1,
                   1, 1, 1, 1, 1,
                   1, 1, 1, 1, 1,
                   1, 1, 1, 1, 9,
                   5, 5, 1, 1, 1,
                   2, 1, 1, 1, 2,
                   2, 2, 3, 1, 3,
                   12, 12, 8, 15, 21,
                   2, 7, 1, 1, 1,
                   1, 9, 9, 9, 5,
                   9, 8, 9, 3, 1,
                   1, 1]

    part2_columns = ['증권그룹구분', '시가총액규모', '지수업종대분류', '지수업종중분류', '지수업종소분류',
                     '벤처기업', '저유동성', 'KRX', 'ETP', 'KRX100',
                     'KRX자동차', 'KRX반도체', 'KRX바이오', 'KRX은행', 'SPAC',
                     'KRX에너지화학', 'KRX철강', '단기과열', 'KRX미디어통신', 'KRX건설',
                     '투자주의환기', 'KRX증권', 'KRX선박', 'KRX섹터_보험', 'KRX섹터_운송',
                     'KOSDAQ150', '기준가', '매매수량단위', '시간외수량단위', '거래정지',
                     '정리매매', '관리종목', '시장경고', '경고예고', '불성실공시',
                     '우회상장', '락구분', '액면변경', '증자구분', '증거금비율',
                     '신용가능', '신용기간', '전일거래량', '액면가', '상장일자',
                     '상장주수', '자본금', '결산월', '공모가', '우선주',
                     '공매도과열', '이상급등', 'KRX300', '매출액', '영업이익',
                     '경상이익', '당기순이익', 'ROE', '기준년월', '시가총액',
                     '그룹사코드', '회사신용한도초과', '담보대출가능', '대주가능']

    df2 = pd.read_fwf(tmp_fil2, widths=field_specs, names=part2_columns)
    df = pd.merge(df1, df2, how='outer', left_index=True, right_index=True)
    df["시장구분"] = "KOSDAQ"

    os.remove(tmp_fil1)
    os.remove(tmp_fil2)
    return df


if __name__ == "__main__":
    kospi_df = parse_kospi_master()
    kosdaq_df = parse_kosdaq_master()

    # 일반 보통주만 필터링 (ETF/ETN/리츠 등 제외)
    kospi_stocks = kospi_df[kospi_df["그룹코드"] == "ST"].copy()
    kosdaq_stocks = kosdaq_df[kosdaq_df["증권그룹구분"] == "ST"].copy()

    print("코스피 일반주식 수:", len(kospi_stocks))
    print("코스닥 일반주식 수:", len(kosdaq_stocks))

    all_stocks = pd.concat([kospi_stocks, kosdaq_stocks], ignore_index=True)

    # 스크리너에서 바로 쓸 핵심 컬럼만 정리
    final_columns = ["종목코드", "종목명", "시장구분", "매출액", "영업이익",
                      "경상이익" if "경상이익" in all_stocks.columns else "당기순이익",
                      "ROE", "시가총액", "상장주수", "결산월"]
    # 코스피/코스닥 컬럼명이 약간 달라 안전하게 존재하는 컬럼만 선택
    final_columns = [c for c in final_columns if c in all_stocks.columns]

    result = all_stocks[final_columns]
    result.to_csv("all_stocks.csv", index=False, encoding="utf-8-sig")

    print("\n최종 all_stocks.csv 저장 완료, 총 종목 수:", len(result))
    print(result.head(10))