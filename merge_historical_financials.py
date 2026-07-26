"""
historical_financials_2025.csv (2023~2025년) + historical_financials_2023.csv (2021~2023년)를
하나로 합쳐서, 종목별로 2021~2025년 전체 데이터를 담은 historical_financials.csv 생성
"""
import pandas as pd


def main():
    df_2025 = pd.read_csv("historical_financials_2025.csv", dtype={"종목코드": str})
    df_2023 = pd.read_csv("historical_financials_2023.csv", dtype={"종목코드": str})

    # 겹치는 2023년 컬럼들은 df_2025 쪽 값을 우선 사용 (동일해야 정상이지만 혹시 다르면 최신 수집분 우선)
    overlap_year = 2023
    cols_to_drop_from_2023 = [c for c in df_2023.columns if c.endswith(f"_{overlap_year}") and c in df_2025.columns]
    df_2023_slim = df_2023.drop(columns=cols_to_drop_from_2023)

    merged = df_2025.merge(df_2023_slim, on=["종목코드", "종목명"], how="outer", suffixes=("", "_dup"))

    # 혹시 남은 중복 컬럼(_dup) 정리
    dup_cols = [c for c in merged.columns if c.endswith("_dup")]
    merged = merged.drop(columns=dup_cols)

    merged.to_csv("historical_financials.csv", index=False, encoding="utf-8-sig")

    print("병합 완료: historical_financials.csv")
    print("총 종목 수:", len(merged))
    print("전체 컬럼 수:", len(merged.columns))

    for year in [2021, 2022, 2023, 2024, 2025]:
        col = f"ROE_{year}"
        if col in merged.columns:
            print(f"  {year}년 ROE 데이터: {merged[col].notna().sum()} / {len(merged)}")
        else:
            print(f"  {year}년 ROE 데이터: 컬럼 없음")


if __name__ == "__main__":
    main()