# 영어 내신 교안 한글(.hwpx/.hwp) 자동화 프로그램

모의고사 교사용 한글 파일(`.hwp`, `.hwpx` — 예: 아잉카 교사용 파일) 또는 지문 이미지를 업로드하고 **원하는 지문 번호만 선택**하면, 학원 내신 교안 양식(**VOCABULARY 2단 표 + 지문 분석 페이지**)에 맞춘 한글 파일(`.hwpx`)을 자동 생성하는 **데스크톱·웹 겸용 앱**입니다.

## 주요 기능

- **순수 Python HWP/HWPX 텍스트 추출**: Windows, macOS, Linux 웹 서버 모두에서 한컴 오피스 설치 없이 `.hwp`(5.0) 및 `.hwpx` 원본 파일을 읽습니다.
- **지문 번호 선택 필터링**: `21, 22, 29-31`처럼 원하는 지문 번호만 입력하면 해당 지문만 추출합니다.
- **Gemini AI 구조화 추출**: 원문자(❶~❿) 영어 본문, 각주, 우리말 해석, `Subject / Title`, `Vocabulary` 20여 개 단어를 정확히 분리하고, 필요 시 영어 한 줄 요약도 자동 생성합니다.
- **내보내기 전 화면 검수·수정**: 생성 전에 오탈자나 단어 뜻을 웹/앱 화면에서 바로 수정할 수 있습니다.
- **한글 호환 출력**:
  - 모든 환경(웹·Mac·Windows)에서 표준 한글 파일(`.hwpx`) 생성 (선생님들 Windows 한글에서 더블클릭으로 바로 열림).
  - Windows PC(한컴 오피스 설치)에서는 구버전 `.hwp` 변환 버튼도 자동 활성화됩니다.

---

## 1. 로컬 데스크톱 실행 방법

### Windows 선생님 PC
1. Python 3.10 이상을 설치합니다 (설치 시 **Add Python to PATH** 체크).
2. 압축을 푼 폴더에서 **`run_windows.bat`** 을 더블클릭합니다.
3. 자동으로 필요 라이브러리를 설치하고 데스크톱 앱 창이 열립니다.

### macOS (개발자/관리자 PC)
터미널에서 압축을 푼 폴더로 이동한 뒤 아래 명령어를 실행합니다.
```bash
chmod +x run_mac.sh
./run_mac.sh
```

### Windows 단일 배포 파일(`.exe`) 만들기
Windows PC에서 **`build_windows_exe.bat`** 을 실행하면 `dist\영어교안_한글자동화\` 폴더에 실행 파일이 생성됩니다. 이 폴더를 선생님들께 공유하면 Python 설치 없이 바로 실행할 수 있습니다.

---

## 2. 무료 웹 배포 방법 (Streamlit Community Cloud)

선생님들이 프로그램 설치 없이 인터넷 주소로 접속해 쓰게 하려면 아래 순서로 5분 만에 배포할 수 있습니다.

1. 이 폴더의 파일들을 본인의 **GitHub 저장소(Private 또는 Public)**에 업로드합니다.
2. [Streamlit Community Cloud](https://share.streamlit.io)에 GitHub 계정으로 로그인하고 **Create app**을 클릭합니다.
3. 저장소와 브랜치를 선택하고 **Main file path**에 `app.py`를 지정합니다.
4. **Advanced settings → Secrets** 칸에 아래와 같이 Gemini API 키를 등록합니다.
   ```toml
   GEMINI_API_KEY = "여기에_발급받은_API_키_입력"
   ```
5. **Deploy**를 누르면 전용 웹 주소가 생성됩니다. Secrets에 API 키를 넣어 두면 선생님들이 별도로 키를 입력하지 않아도 바로 사용할 수 있습니다.

---

## 파일 구성

- `app.py`: Streamlit 웹·데스크톱 UI 메인 앱
- `core/hwp_reader.py`: `.hwp`(5.0 OLE) / `.hwpx`(XML) 텍스트 추출 및 지문 번호 파서
- `core/gemini_parser.py`: Gemini API(`google-genai`) 기반 지문·어휘 구조화 추출기
- `core/hwpx_builder.py`: VOCABULARY 표 + 지문 분석 페이지 `.hwpx` 생성기
- `core/win_hwp_converter.py`: Windows 전용 `.hwpx → .hwp` 한글 COM 변환 모듈
- `desktop_launcher.py`: 로컬 데스크톱 창 실행기
- `sample_21번_교안.hwpx`: 1번 사진(21번 지문)으로 미리 생성해 둔 테스트 결과물
