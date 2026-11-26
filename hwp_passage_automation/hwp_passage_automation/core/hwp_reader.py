"""순수 Python 기반 HWP 5.0(OLE) 및 HWPX(ZIP/XML) 텍스트 추출기.

Windows, macOS, Linux(웹 서버) 환경 모두에서 한컴 오피스 설치 없이
.hwp / .hwpx 파일의 전체 본문 텍스트를 추출합니다.
UTF-16LE 서로게이트 페어를 안전하게 처리하여 장문·특수기호 포함 파일에서도 오류가 나지 않습니다.
"""

from __future__ import annotations

import io
import re
import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path
from typing import Iterable, List, Set, Union

import olefile


def parse_passage_numbers(spec: str) -> List[int]:
    """사용자 입력 지문 번호 문자열을 정렬된 정수 리스트로 변환합니다.

    예:
        "21, 22, 29-31" -> [21, 22, 29, 30, 31]
        "" 또는 "전체" -> [] (전체 추출을 의미)
    """
    cleaned = (spec or "").strip()
    if not cleaned or cleaned in ("전체", "all", "ALL", "*"):
        return []

    numbers: Set[int] = set()
    tokens = re.split(r"[,;\s]+", cleaned)
    for token in tokens:
        if not token:
            continue
        token = token.replace("번", "")
        if "-" in token or "~" in token:
            parts = re.split(r"[-~]", token)
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                start, end = int(parts[0]), int(parts[1])
                if start <= end:
                    numbers.update(range(start, end + 1))
                else:
                    numbers.update(range(end, start + 1))
        elif token.isdigit():
            numbers.add(int(token))
        else:
            raise ValueError(f"지문 번호 형식이 올바르지 않습니다: '{token}' (예: 21, 22, 29-31)")

    return sorted(numbers)


def _decode_hwp5_para_text(rec: bytes) -> str:
    """HWP 5.0 HWPTAG_PARA_TEXT(tag_id=67) 레코드에서 UTF-16LE 텍스트를 안전하게 디코딩합니다."""
    raw_utf16 = bytearray()
    j = 0
    length = len(rec)

    # HWP 5.0 제어 문자 규격:
    # 확장 제어 문자(8 wchar = 16 bytes): 1,2,3,11,12,14,15,16,17,18,21,22,23
    # 인라인 제어 문자(8 wchar = 16 bytes): 4,5,6,7,8,9,19,20
    ext_controls = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}
    inline_controls = {4, 5, 6, 7, 8, 9, 19, 20}

    while j + 1 < length:
        ch = struct.unpack_from("<H", rec, j)[0]
        if ch in ext_controls:
            j += 16
        elif ch in inline_controls:
            if ch == 9:
                raw_utf16.extend(b"\t\x00")
            j += 16
        elif ch in (10, 13):
            raw_utf16.extend(b"\n\x00")
            j += 2
        elif ch in (0, 24):
            j += 2
        elif ch in (30, 31):
            raw_utf16.extend(b" \x00")
            j += 2
        else:
            raw_utf16.extend(rec[j : j + 2])
            j += 2

    # UTF-16LE 전체 바이트열을 한 번에 디코딩하여 서로게이트 페어를 정상 처리
    text = raw_utf16.decode("utf-16-le", errors="replace")
    # UTF-8 인코딩을 깨뜨리는 단독 서로게이트나 제어 문자 제거
    text = text.replace("\ufffd", "")
    return text.strip()


def extract_text_from_hwp5(source: Union[str, Path, bytes, io.BytesIO]) -> str:
    """HWP 5.0 바이너리(OLE) 파일에서 모든 섹션의 텍스트를 추출합니다."""
    if isinstance(source, bytes):
        ole = olefile.OleFileIO(io.BytesIO(source))
    else:
        ole = olefile.OleFileIO(source)

    try:
        if not ole.exists("FileHeader"):
            raise ValueError("유효한 HWP 5.0 파일이 아닙니다 (FileHeader 누락).")

        header = ole.openstream("FileHeader").read()
        flags = struct.unpack_from("<I", header, 36)[0]
        is_compressed = bool(flags & 1)
        is_encrypted = bool(flags & 2)

        if is_encrypted:
            raise ValueError(
                "암호로 보호된 HWP 파일입니다. 한글에서 암호를 해제하거나 .hwpx로 다시 저장해 주세요."
            )

        section_entries = []
        for entry in ole.listdir():
            if len(entry) == 2 and entry[0] == "BodyText" and entry[1].startswith("Section"):
                m = re.search(r"Section(\d+)$", entry[1])
                idx = int(m.group(1)) if m else 9999
                section_entries.append((idx, entry))
        section_entries.sort(key=lambda x: x[0])

        paragraphs: List[str] = []
        for _, entry in section_entries:
            raw = ole.openstream(entry).read()
            if is_compressed:
                raw = zlib.decompress(raw, -15)

            i = 0
            n = len(raw)
            while i + 4 <= n:
                rec_hdr = struct.unpack_from("<I", raw, i)[0]
                i += 4
                tag_id = rec_hdr & 0x3FF
                size = (rec_hdr >> 20) & 0xFFF
                if size == 0xFFF:
                    if i + 4 > n:
                        break
                    size = struct.unpack_from("<I", raw, i)[0]
                    i += 4
                rec_data = raw[i : i + size]
                i += size

                if tag_id == 67:  # HWPTAG_PARA_TEXT
                    text = _decode_hwp5_para_text(rec_data)
                    if text:
                        paragraphs.append(text)

        return "\n".join(paragraphs)
    finally:
        ole.close()


def extract_text_from_hwpx(source: Union[str, Path, bytes, io.BytesIO]) -> str:
    """HWPX(ZIP/OWPML XML) 파일에서 모든 섹션의 텍스트를 추출합니다."""
    if isinstance(source, bytes):
        zf_ctx = zipfile.ZipFile(io.BytesIO(source), "r")
    else:
        zf_ctx = zipfile.ZipFile(source, "r")

    with zf_ctx as zf:
        section_files = sorted(
            [
                name
                for name in zf.namelist()
                if name.startswith("Contents/section") and name.endswith(".xml")
            ],
            key=lambda s: int(re.search(r"section(\d+)\.xml$", s).group(1))
            if re.search(r"section(\d+)\.xml$", s)
            else 9999,
        )

        paragraphs: List[str] = []
        for sec_name in section_files:
            xml_bytes = zf.read(sec_name)
            root = ET.fromstring(xml_bytes)
            for elem in root.iter():
                if elem.tag.endswith("}p") or elem.tag == "p":
                    parts: List[str] = []
                    for sub in elem.iter():
                        if (sub.tag.endswith("}t") or sub.tag == "t") and sub.text:
                            parts.append(sub.text)
                    line = "".join(parts).strip()
                    if line:
                        paragraphs.append(line)

        return "\n".join(paragraphs)


def extract_text_from_file(
    source: Union[str, Path, bytes, io.BytesIO],
    filename: str = "",
) -> str:
    """확장자 또는 파일 시그니처를 자동 판별하여 HWP/HWPX 텍스트를 추출합니다."""
    if isinstance(source, (str, Path)):
        path = Path(source)
        filename = filename or path.name
        data = path.read_bytes()
    elif isinstance(source, io.BytesIO):
        data = source.getvalue()
    else:
        data = source

    ext = Path(filename).suffix.lower() if filename else ""
    if ext == ".hwpx" or data[:4] == b"PK\x03\x04":
        return extract_text_from_hwpx(data)
    if ext == ".hwp" or data[:4] == b"\xd0\xcf\x11\xe0":
        return extract_text_from_hwp5(data)

    raise ValueError(
        f"지원하지 않는 파일 형식입니다: '{filename}'. .hwp 또는 .hwpx 파일을 업로드해 주세요."
    )


def prefilter_text_by_numbers(
    full_text: str,
    target_numbers: Iterable[int],
    window_chars: int = 9000,
) -> str:
    """전체 모의고사 텍스트가 길 때 원하는 지문 번호 주변 구간만 1차 추려냅니다.

    단일 번호(예: 29.)뿐 아니라 장문 복합 번호(예: 41~42., 43~45.)도 함께 매칭합니다.
    """
    nums = sorted(set(target_numbers))
    if not nums or len(full_text) <= 55000:
        return full_text

    seen_ranges: List[tuple[int, int]] = []
    for num in nums:
        # "29.", "29번", "41~42.", "43-45." 패턴 탐색
        pattern = re.compile(
            rf"(?:^|\n)\s*(?:{num}\s*(?:[~-]\s*\d+)?\s*(?:\.|번)|\d+\s*[~-]\s*{num}\s*\.)"
        )
        for match in pattern.finditer(full_text):
            start = max(0, match.start() - 600)
            end = min(len(full_text), match.end() + window_chars)
            seen_ranges.append((start, end))

    if not seen_ranges:
        return full_text

    seen_ranges.sort()
    merged: List[tuple[int, int]] = [seen_ranges[0]]
    for s, e in seen_ranges[1:]:
        prev_s, prev_e = merged[-1]
        if s <= prev_e:
            merged[-1] = (prev_s, max(prev_e, e))
        else:
            merged.append((s, e))

    return "\n\n=== [구간 구분] ===\n\n".join(full_text[s:e] for s, e in merged)


def _is_korean_line(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text))


def _merge_vocab_en_lines(raw_en: List[str]) -> List[str]:
    """2열 표 폭 때문에 줄바꿈된 영단어/숙어 줄을 하나의 표현으로 합칩니다."""
    merged: List[str] = []
    continuation_tokens = {
        "...", "do", "sth", "sb", "oneself", "to", "of", "for", "with", "in", "on", "at", "up", "out", "off",
    }
    for line in raw_en:
        s = line.strip()
        if not s:
            continue
        if merged:
            prev = merged[-1]
            if prev.endswith("-") and not prev.endswith("--"):
                merged[-1] = (prev[:-1].rstrip() + " " + s).strip()
                continue
            if s in continuation_tokens or prev.endswith("~"):
                merged[-1] = (prev + " " + s).strip()
                continue
        merged.append(s)
    return merged


def _merge_vocab_ko_lines(raw_ko: List[str]) -> List[str]:
    """2열 표 폭 때문에 줄바꿈된 한국어 뜻을 하나의 뜻으로 합칩니다."""
    cleaned = [s.strip() for s in raw_ko if s.strip()]
    out: List[str] = []
    pending_prefix: str = ""
    verb_continuations = {
        "하다", "되다", "있다", "없다", "지다", "받다", "주다",
        "부여하다", "지시하다", "가능성이 있다", "새어 나오다",
    }
    for s in cleaned:
        # '(웃음 등이)' 처럼 괄호 수식어만 단독 줄로 끊긴 경우 다음 줄 앞에 붙임
        if re.match(r"^\([^)]+\)$", s):
            pending_prefix = (pending_prefix + " " + s).strip()
            continue
        if pending_prefix:
            s = f"{pending_prefix} {s}"
            pending_prefix = ""
        if out and (
            out[-1].endswith(",")
            or out[-1].endswith(";")
            or out[-1].endswith("~하도록")
            or out[-1].endswith("...하도록")
            or out[-1].endswith("안되게")
            or s in verb_continuations
        ):
            out[-1] = f"{out[-1]} {s}"
        else:
            out.append(s)
    if pending_prefix:
        if out:
            out[-1] = f"{out[-1]} {pending_prefix}"
        else:
            out.append(pending_prefix)
    return out


def extract_vocab_by_passage_from_text(full_text: str) -> dict[int, tuple[List[str], List[str]]]:
    """아잉카 원본 HWP 텍스트에서 각 지문 번호별 `■ Vocabulary`의 (영단어 리스트, 한국어 뜻 리스트)를 직접 추출합니다.

    LLM이 단어를 누락하거나 뜻을 임의로 바꾸는 문제를 원천 차단하기 위해
    원본 파일의 Vocabulary 블록을 100% 원문 그대로 파싱합니다.
    """
    lines = full_text.splitlines()
    result: dict[int, tuple[List[str], List[str]]] = {}
    current_nums: List[int] = []

    for idx, raw_line in enumerate(lines):
        s = raw_line.strip()
        # 복합 문항 번호 예: "41~42. 다음 글을 읽고..."
        m_range = re.match(r"^(\d{1,2})\s*[~-]\s*(\d{1,2})\.\s+", s)
        if m_range:
            a, b = int(m_range.group(1)), int(m_range.group(2))
            if 1 <= a <= b <= 50:
                current_nums = list(range(a, b + 1))
                continue

        # 단일 문항 번호 예: "20. 다음 글에서..."
        m_single = re.match(r"^(\d{1,2})\.\s+", s)
        if m_single:
            n = int(m_single.group(1))
            if 1 <= n <= 50:
                # 41~42, 43~45 내부 소문항이면 기존 범위 유지
                if not (current_nums and n in current_nums):
                    current_nums = [n]
                continue

        if re.match(r"^[■▪□▶•\s]*Vocabulary\b", s, re.IGNORECASE) and current_nums:
            en_raw: List[str] = []
            ko_raw: List[str] = []
            seen_ko = False
            j = idx + 1
            while j < len(lines):
                l = lines[j].strip()
                if not l:
                    j += 1
                    continue
                if l.startswith(("❶", "▶", "★", "■", "Our English Cafe", "(A) ❶", "(B) ❶", "(C) ❶", "•", "※")):
                    break
                if re.match(r"^\d{1,2}(?:\s*[~-]\s*\d{1,2})?\.\s+", l):
                    break
                if _is_korean_line(l):
                    seen_ko = True
                    # 실용문 안내문 해석 본문(긴 문장)이 이어지는 경우 중단
                    if len(ko_raw) >= len(en_raw) and (l.endswith(("다.", "요!", "요.", "니다")) and len(l) > 22):
                        break
                    ko_raw.append(l)
                else:
                    if seen_ko:
                        break
                    en_raw.append(l)
                j += 1

            en_merged = _merge_vocab_en_lines(en_raw)
            ko_merged = _merge_vocab_ko_lines(ko_raw)
            # 실용문 등에서 해석 제목이 뒤에 붙어 ko_merged가 en_merged보다 긴 경우 앞쪽 en_merged개까지만 점검
            if len(en_merged) > 0:
                for num in current_nums:
                    result[num] = (en_merged, ko_merged)

    return result
