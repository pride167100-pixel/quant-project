import pandas as pd

all_stocks = pd.read_csv("all_stocks.csv", dtype={"종목코드": str})
sector_info = pd.read_csv("sector_info.csv", dtype={"종목코드": str, "업종코드": str})

merged = all_stocks.merge(sector_info, on="종목코드", how="left")
print("전체 대상(순수주식):", len(merged))
print("업종명 매칭 성공:", merged["업종명"].notna().sum())
print("\n[샘플 - 매칭된 것]")
print(merged[merged["업종명"].notna()][["종목코드", "종목명", "업종명"]].head(15))
print("\n[매칭 안 된 것 샘플]")
print(merged[merged["업종명"].isna()][["종목코드", "종목명", "업종코드"]].head(10))