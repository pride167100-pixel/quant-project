# 퀀트 프로젝트 진행상황

## 완료된 것 (2026-07-22 ~ 23)
- Python 3.12, VS Code, venv 가상환경 설정 완료
- 한국투자증권 Open API 앱키/시크릿 발급 완료 (.env에 저장, 실전투자계좌 기준)
- 토큰 발급 테스트 성공 (test_token.py)
- 종목 시세 조회 테스트 성공 (test_price.py)
- 코스피/코스닥 마스터 파일 파싱 완료 (parse_stock_list.py)
  → 일반 보통주만 필터링 (그룹코드 'ST') → 총 2,719개 종목 (all_stocks.csv)
- 전 종목 시세/PBR/PER 등 수집 완료 (build_universe.py + retry_failures.py)
  → universe_full.csv 에 최종 통합 데이터 저장됨 (재무데이터 + 시세 + PBR/PER)

## 다음에 할 일 (내일)
1. 성장(Growth) 지표 데이터 추가
   - DART Open API 연동 (재무제표 시계열 - 전년대비 영업이익/매출 성장률)
   - growth_data.csv로 별도 저장 예정
2. 스크리너 UI 만들기
   - 5개 카테고리(가치/퀄리티/성장/모멘텀/규모) 탭 구조
   - 슬라이더 + 숫자 직접 입력 병행
   - 프리셋 저장/추가 기능

## 확정된 설계 방향 (참고)
- 국내주식(코스피/코스닥), 한투 API, 완전 자동매매 목표
- 모의투자는 KIS 공식 모의서버 아닌, 내부 가상 매매 로직으로 구현
- 리밸런싱 주기에만 프로그램 실행 (상시 서버 불필요)
- 배포는 각자 컴퓨터에서 실행 + 각자 API 키 사용
- 알림은 텔레그램 봇 예정 (아직 미착수)
- 성장률 지표는 마스터 파일에 없어 DART API 별도 필요(확인됨)
## 정리 대상 (프로젝트 마무리 단계에서 삭제 예정)
- test_token.py — 최초 API 연동 테스트용, 역할 다함
- test_price.py — 최초 시세 조회 테스트용, 역할 다함
- test_ui.py — Streamlit 감 잡기용, 역할 다함
- kospi_code.mst.zip, kosdaq_code.mst.zip — 압축 원본, 파싱 후 불필요
- corpCode.zip — 압축 원본, 파싱 후 불필요
- growth_checkpoint.csv, universe_checkpoint.csv — 중간 저장용, 최종 파일 완성 후 불필요
- failure_diagnosis_sample.csv — 일회성 진단용

## 완료된 것 (추가, 2026-07-24 오후)
- Streamlit 기반 스크리너 화면 완성 (screener_app.py)
  → 4개 카테고리(가치/퀄리티/성장/규모) 탭, 슬라이더+숫자입력 동기화, 체크박스 on/off
  → 지표별 설명 툴팁(물음표 아이콘) 추가
  → 업종명 컬럼 추가 (get_sector_names.py, sector_info.csv, 2,472/2,719 매칭)
- 데이터 파일 최종 구조: universe_full.csv + growth_data.csv + company_info.csv + sector_info.csv
  → merge_data.py 로 전부 통합 → screener_data.csv 최종본

## 다음에 할 일
1. 모의매매(가상 거래) 기능 추가
   - 체크박스로 종목 선택 → "거래하기" → 매수/매도
   - 균등배분 / 시가총액가중 옵션 선택 가능하게
   - SQLite로 프리셋별 보유 종목(바스켓) 저장
2. 모멘텀(Momentum) 카테고리 추가 (5번째 탭)
   - 과거 가격 이력 수집 필요 (한투 API, 3/6/12개월 수익률 계산)
   - 밸류 트랩 방지 목적 (가치 지표만으로는 급락주가 저평가로 오인될 수 있음)
3. 지표 실시간 새로고침 버튼 (universe_full.csv 등 재수집 트리거)

## 정리 대상 (프로젝트 마무리 단계에서 삭제 예정, 추가)
- check_sector_match.py — 업종 매칭 검증용 1회성 스크립트
- inspect_raw_field.py — 필드 위치 디버깅용 1회성 스크립트
- idxcode.zip, idxcode.mst — 파싱 후 원본, 불필요
- company_info_checkpoint.csv, growth_checkpoint.csv — 중간 저장용