# v1.0.2 -> v2.0.0 Hybrid 변경사항

## C++로 이동한 기능

- 스캘핑 규칙 점수
- 스윙 규칙 점수
- AI 확률과 규칙 점수 결합
- 진입 기준 판정
- 스캘핑/스윙 청산
- 위험 기반 주문수량
- PAPER 체결가·슬리피지·수수료
- 거래 순손익·순수익률

## Python에 유지한 기능

- 회원가입, 로그인, 비밀번호 해시
- SQLite 트랜잭션
- GUI와 CLI
- yfinance 및 pandas
- XGBoost 학습/추론
- 토스증권 REST 요청
- 알림과 실행 스케줄링

## 실행 차이

v1에서는 C++ 엔진 빌드에 실패해도 Python 계산으로 실행될 수 있었습니다. v2 기본값은 다음과 같습니다.

```env
REQUIRE_CPP_ENGINE=true
```

따라서 `install_windows.bat`에서 C++ 빌드가 성공해야 앱이 시작됩니다.

## 기존 데이터

기존 `data/trading_app.db`를 새 프로젝트의 `data` 폴더에 복사하면 회원과 모의 거래 기록을 이어서 사용할 수 있습니다. 복사 전 새 프로그램을 종료하고 원본 DB를 백업하세요.

기존 `.env`는 전체 복사보다 새 `.env.example`을 기준으로 필요한 값만 옮기는 것을 권장합니다.


## v2.0.1 Windows 실행 수정

- 모든 BAT 파일이 `cd /d "%~dp0"`로 자신의 폴더에서 실행됨
- ZIP 내부에서 실행했을 때 압축 해제 안내 표시
- Python 3.11 x64 자동 탐지와 불완전한 `.venv` 복구
- C++ 빌드 실패 시 앱 전체 설치를 중단하지 않고 Python fallback으로 실행
- `START_HERE.bat` 단일 실행 파일 추가
- `diagnose_windows.bat` 환경 진단 파일 추가
- 정확한 최신 버전만 요구하던 패키지 제한을 호환 범위로 완화
- 설치 성공/실패를 `install_result.txt`에 기록
