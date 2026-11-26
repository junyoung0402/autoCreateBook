"""Windows 전용 한글(HWP) COM 자동화 변환 헬퍼.

Windows PC에 한컴 오피스 한글이 설치되어 있을 때,
생성된 .hwpx 파일을 구버전 .hwp(5.0) 파일로 자동 변환할 수 있습니다.
macOS / Linux(웹 서버) 환경에서는 안전하게 비활성화됩니다.
"""

from __future__ import annotations

import platform
from pathlib import Path


def is_windows_hwp_available() -> bool:
    """현재 환경에서 Windows 한글 COM 자동화가 가능한지 확인합니다."""
    if platform.system() != "Windows":
        return False
    try:
        import win32com.client  # noqa: F401
        return True
    except ImportError:
        return False


def convert_hwpx_to_hwp(hwpx_path: str | Path, hwp_output_path: str | Path) -> Path:
    """Windows 한글 COM을 이용해 .hwpx 파일을 .hwp 파일로 변환합니다."""
    if not is_windows_hwp_available():
        raise RuntimeError(
            "Windows 환경 및 pywin32/한컴 오피스가 필요합니다. 웹/맥 환경에서는 .hwpx 파일을 그대로 한글에서 열어 사용하세요."
        )

    import pythoncom
    import win32com.client

    src = Path(hwpx_path).resolve()
    dst = Path(hwp_output_path).resolve()

    pythoncom.CoInitialize()
    hwp = None
    try:
        hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
        hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
        hwp.XHwpWindows.Item(0).Visible = False
        hwp.Open(str(src), "HWPX", "forceopen:true")
        hwp.SaveAs(str(dst), "HWP")
        return dst
    finally:
        if hwp is not None:
            try:
                hwp.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()
