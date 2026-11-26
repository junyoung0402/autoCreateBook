#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "[1/3] 가상환경(.venv) 생성 중..."
    python3 -m venv .venv
fi

source .venv/bin/activate
echo "[2/3] 필요한 패키지 설치 확인 중..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "[3/3] 영어 내신 교안 한글 자동화 앱을 실행합니다..."
python3 desktop_launcher.py
