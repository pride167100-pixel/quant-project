import pandas as pd

def main():
    universe = pd.read_csv("universe_full.csv", dtype={"종목코드": str})
    growth = pd.read_csv("growth_data.csv", dtype={"종목코드": str})

    # growth_data.csv에서 필요한 컬럼만 추림 (중복 방지)
    growth_cols = ["종목코드", "매출액성장률(%)", "영업이익성장률(%)"]
    growth_slim = growth[growth_cols]

    final = universe.merge(growth_slim, on="종목코드", how="left")

    # 보기 좋게 컬럼 순서 정리
    preferred_order = [
        "종목코드", "종목명", "시장구분",
        "현재가", "등락률",
        "PBR", "PER", "ROE",
        "매출액성장률(%)", "영업이익성장률(%)",
        "시가총액", "매출액", "영업이익",
        "EPS", "BPS", "상장주수", "결산월"
    ]
    cols = [c for c in preferred_order if c in final.columns]
    remaining = [c for c in final.columns if c not in cols]
    final = final[cols + remaining]

    final.to_csv("screener_data.csv", index=False, encoding="utf-8-sig")

    print("최종 통합 파일: screener_data.csv")
    print("총 종목 수:", len(final))
    print("\n[컬럼 목록]")
    print(list(final.columns))
    print("\n[샘플 데이터]")
    print(final[["종목코드", "종목명", "PBR", "PER", "ROE",
                 "매출액성장률(%)", "영업이익성장률(%)", "시가총액"]].head(10))

    print("\n[각 핵심 지표별 정상 데이터 개수]")
    for col in ["PBR", "PER", "ROE", "매출액성장률(%)", "영업이익성장률(%)", "시가총액"]:
        print(f"  {col}: {final[col].notna().sum()} / {len(final)}")


if __name__ == "__main__":
    main()