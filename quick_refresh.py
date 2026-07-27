"""
빠른 새로고침: 현재가 + PER + PBR만 초고속으로 갱신 (멀티종목 일괄조회 API 사용)
예상 소요시간: 약 1~2분
EPS/BPS는 재무 새로고침(full_refresh.py) 때의 값을 그대로 사용해 PER/PBR을 재계산합니다.
"""
import kis_batch_refresh


def main(progress_callback=None):
    return kis_batch_refresh.main(progress_callback=progress_callback)


if __name__ == "__main__":
    main()