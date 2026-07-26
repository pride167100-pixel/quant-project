import pandas as pd
from datetime import datetime
import backtest_engine as be

# 1. 실시간 화면(screener_data.csv)에서 삼성전자 값 확인
live_df = pd.read_csv("screener_data.csv", dtype={"종목코드": str})
live_samsung = live_df[live_df["종목코드"] == "005930"]
print("=== 실시간 화면(screener_data.csv) 기준 삼성전자 ===")
print(live_samsung[["종목코드", "종목명", "현재가", "PBR", "PER", "ROE",
                     "매출액성장률(%)", "영업이익성장률(%)", "시가총액",
                     "3개월수익률(%)", "6개월수익률(%)", "12개월수익률(%)"]].to_string())

# 2. 백테스터가 '오늘' 시점에 계산하는 삼성전자 값 확인
static_info, financials, prices = be.load_backtest_data()
price_lookup = be.build_price_lookup(prices)
today = datetime.now()

snapshot = be.build_historical_snapshot(today, static_info, financials, price_lookup)
bt_samsung = snapshot[snapshot["종목코드"] == "005930"]
print("\n=== 백테스터가 계산한 '오늘' 기준 삼성전자 ===")
print(bt_samsung[["종목코드", "종목명", "현재가", "PBR", "PER", "ROE",
                  "매출액성장률(%)", "영업이익성장률(%)", "시가총액",
                  "3개월수익률(%)", "6개월수익률(%)", "12개월수익률(%)"]].to_string())

Y = be.get_fiscal_year_asof(today)
print(f"\n백테스터가 사용한 회계연도: {Y}")