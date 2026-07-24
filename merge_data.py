import pandas as pd

def main():
    universe = pd.read_csv("universe_full.csv", dtype={"종목코드": str})
    growth = pd.read_csv("growth_data.csv", dtype={"종목코드": str})
    company = pd.read_csv("company_info.csv", dtype={"종목코드": str})
    sector = pd.read_csv("sector_info.csv", dtype={"종목코드": str})
    momentum = pd.read_csv("momentum_data.csv", dtype={"종목코드": str})

    growth_slim = growth[["종목코드", "매출액성장률(%)", "영업이익성장률(%)", "부채비율(%)", "유동비율(%)"]]

    final = universe.merge(growth_slim, on="종목코드", how="left")
    final = final.merge(company, on="종목코드", how="left")
    final = final.merge(sector, on="종목코드", how="left")
    final = final.merge(momentum, on="종목코드", how="left")

    preferred_order = [
        "종목코드", "종목명", "업종명", "시장구분", "대표자",
        "현재가", "등락률",
        "PBR", "PER", "ROE",
        "매출액성장률(%)", "영업이익성장률(%)", "부채비율(%)", "유동비율(%)",
        "3개월수익률(%)", "6개월수익률(%)", "12개월수익률(%)", "평균거래대금(억원)",
        "시가총액", "매출액", "영업이익",
        "EPS", "BPS", "상장주수", "결산월", "설립일", "주소"
    ]
    cols = [c for c in preferred_order if c in final.columns]
    remaining = [c for c in final.columns if c not in cols]
    final = final[cols + remaining]

    final.to_csv("screener_data.csv", index=False, encoding="utf-8-sig")

    print("최종 통합 파일: screener_data.csv")
    print("총 종목 수:", len(final))
    print("업종명 있는 종목 수:", final["업종명"].notna().sum())
    print("\n[샘플 데이터]")
    print(final[["종목코드", "종목명", "업종명", "PBR", "PER", "ROE"]].head(10))


if __name__ == "__main__":
    main()