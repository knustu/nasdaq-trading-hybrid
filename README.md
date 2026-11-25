# Nasdaq Trading Hybrid

Python 앱과 C++17 계산 엔진을 pybind11로 연결한 스캘핑·스윙 교육용 프로토타입입니다. 공개 소스 버전은 **v2.0.1**이며, 시연은 PAPER 모드의 모의 주문·체결을 기준으로 합니다.

| 위치 | 역할 |
| --- | --- |
| [cpp_engine/](cpp_engine/) | 진입 점수, 청산 조건, 수량, 체결과 손익 계산 |
| [app/cpp_adapter.py](app/cpp_adapter.py) | C++ 모듈 선택과 Python 계산 경로 |
| [app/](app/) | Tkinter UI, 전략, 회원·설정 저장, 모의 브로커 |
| [backtest.py](backtest.py) | 과거 데이터 기반 콘솔 백테스트 |
| [tests/](tests/) | 계산 경계, PAPER 브로커, 회원·GUI·실행 도구 회귀 검사 |

## Windows에서 실행

PowerShell에서 Python 3.11 환경을 만든 뒤 실행합니다. 앱에서는 PAPER 모드를 선택합니다.

~~~powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
~~~

C++ 경로를 사용하려면 Visual Studio Build Tools의 C++ 도구와 Windows SDK를 준비하고 [build_cpp.bat](build_cpp.bat)을 실행합니다. C++ 모듈이 없는 환경에서는 Python 계산 경로를 사용할 수 있습니다.

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q
~~~

[설정 예시](.env.example)의 브로커와 알림 인증란은 비워 두었습니다. 설치, 빌드, 기능별 실행 방법은 [v2.0.1 원본 사용 가이드](docs/v2.0.1-guide.md)를 참고하세요.
