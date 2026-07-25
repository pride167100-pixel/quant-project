"""
재무 데이터 새로고침: 전체 시세(EPS/BPS 포함) + 모멘텀 + 업종 + 재무제표(성장률·부채비율·유동비율)
+ 회사개요까지 전부 갱신. 여기서 EPS/BPS도 최신화되므로, 이후 '빠른 새로고침'이 정확한 값을 씁니다.

예상 소요시간: 약 1~1.5시간 (분기 실적 발표 시기나 한 달에 한 번 정도만 실행 권장)
"""
from datetime import datetime
import build_universe
import build_momentum_data
import get_sector_names
import build_growth_data
import build_company_info
import merge_data


def main():
    start = datetime.now()
    print("=" * 50)
    print("재무 데이터 새로고침 시작 (시간이 꽤 걸립니다: 약 1~1.5시간)")
    print("시작 시각:", start.strftime("%H:%M:%S"))
    print("=" * 50)

    print("\n[1/6] 시세 · PBR · PER · EPS · BPS 전체 갱신 중... (약 25~30분)")
    build_universe.main()

    print("\n[2/6] 모멘텀(3/6/12개월 수익률) · 거래대금 갱신 중... (약 25~30분)")
    build_momentum_data.main()

    print("\n[3/6] 업종 정보 갱신 중...")
    get_sector_names.main()

    print("\n[4/6] 재무제표(성장률/부채비율/유동비율) 갱신 중... (약 25~30분)")
    build_growth_data.main()

    print("\n[5/6] 회사개요(대표자/설립일/주소) 갱신 중... (약 25~30분)")
    build_company_info.main()

    print("\n[6/6] 최종 데이터 병합 중...")
    merge_data.main()

    elapsed = (datetime.now() - start).total_seconds()
    print("\n" + "=" * 50)
    print(f"재무 데이터 새로고침 완료! 총 소요시간: {elapsed / 60:.1f}분")
    print("=" * 50)
    return {"elapsed_sec": elapsed}


if __name__ == "__main__":
    main()