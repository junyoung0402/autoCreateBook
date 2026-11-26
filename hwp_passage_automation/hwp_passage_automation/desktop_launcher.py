"""Windows/macOS 데스크톱 앱 실행 런처.

Streamlit 서버를 로컬 백그라운드에서 실행하고,
pywebview가 설치되어 있으면 네이티브 데스크톱 창으로,
그렇지 않으면 기본 웹 브라우저로 자동 실행합니다.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


def _find_free_port(start: int = 8501) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return 8501


def _wait_for_server(port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.3)
    return False


def main() -> None:
    app_path = Path(__file__).resolve().parent / "app.py"
    port = _find_free_port(8501)
    url = f"http://127.0.0.1:{port}"

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        f"--server.port={port}",
        "--server.address=127.0.0.1",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    proc = subprocess.Popen(cmd)

    try:
        if not _wait_for_server(port):
            print("서버 시작 시간이 초과되었습니다.")
            return

        try:
            import webview  # pywebview가 있으면 네이티브 앱 창으로 실행

            webview.create_window("영어 내신 교안 한글 자동화", url, width=1280, height=860)
            webview.start()
        except ImportError:
            webbrowser.open(url)
            print(f"브라우저에서 실행되었습니다: {url}")
            print("종료하려면 이 창을 닫거나 Ctrl+C를 누르세요.")
            proc.wait()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
