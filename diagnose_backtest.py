import pandas as pd
from datetime import datetime, timedelta

prices = pd.read_csv("historical_prices.csv", dtype={"종목코드": str})
print("전체 행 수:", len(prices))
print("고유 종목코드 수:", prices["종목코드"].nunique())
print("\n날짜 컬럼 원본 샘플(문자열):", prices["날짜"].iloc[0], type(prices["날짜"].iloc[0]))

prices["날짜_파싱"] = pd.to_datetime(prices["날짜"], format="%Y%m%d")
print("\n파싱 후 전체 날짜 범위:", prices["날짜_파싱"].min(), "~", prices["날짜_파싱"].max())

# 코스피 ETF(069500) 데이터 확인
kospi = prices[prices["종목코드"] == "069500"]
print(f"\n코스피(069500) 데이터 행 수: {len(kospi)}")
if len(kospi) > 0:
    print("코스피 날짜 범위:", kospi["날짜_파싱"].min(), "~", kospi["날짜_파싱"].max())
else:
    print("코스피 코드가 파일에 아예 없습니다!")
    print("파일에 있는 종목코드 샘플 10개:", prices["종목코드"].unique()[:10])

# 삼성전자로도 확인 (혹시 전 종목 자체가 문제인지)
samsung = prices[prices["종목코드"] == "005930"]
print(f"\n삼성전자(005930) 데이터 행 수: {len(samsung)}")
if len(samsung) > 0:
    print("삼성전자 날짜 범위:", samsung["날짜_파싱"].min(), "~", samsung["날짜_파싱"].max())

# 오늘 기준 36개월 전 날짜와 비교
now = datetime.now()
target_36m_ago = now - timedelta(days=36*30)
print(f"\n오늘: {now.strftime('%Y-%m-%d')}")
print(f"36개월 전(근사): {target_36m_ago.strftime('%Y-%m-%d')}")
print(f"수집된 데이터의 가장 오래된 날짜가 이보다 이전인가? {prices['날짜_파싱'].min() <= target_36m_ago}")