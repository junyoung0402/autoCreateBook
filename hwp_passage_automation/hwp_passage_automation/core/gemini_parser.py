"""Gemini API 기반 모의고사 교사용 지문 구조화 추출기 및 유형별 자동 정제기.

실제 아잉카(Our English Cafe) 모의고사 교사용 한글 파일의 모든 문항 유형(18~45번)에 대응합니다:
- 어법 추론 (29번): `④ what (→ that)` → `that` 치환 및 ①~⑤ 제거
- 어휘 추론 (30번, 41~42번): `⑤ uninterested (→ potential)`, `(b) include (→ eliminate)`,
  한글 해석의 `무관심한(→ 잠재적인)`, `포함한다(→ 제거한다)` 모두 정답 어휘만 남기고 오답·기호 제거
- 빈칸 추론 (31~34번): 본문 원문 유지, 하단 선택지 ①~⑤ 제거
- 무관한 문장 (35번): 전체 흐름과 무관한 문장(한글 해석에 괄호 처리된 문장) 제거 후 ①~⑤ 제거 및 ❶~❻ 연속 재번호
- 순서 추론 (36~37번, 43~45번): (A)(B)(C)(D) 및 (a)~(e) 제거 후 원문자 숫자 순서(❶→❷→...) 정렬
- 문장 삽입 (38~39번): 상단 박스 문장을 원문자 숫자 위치로 이동, ( ① )~( ⑤ ) 제거
- 요약문 추론 (40번): 본문(❶~❽)과 요약문(❾) 분리, 요약문은 영어 한 줄 요약으로 활용 가능
- 분리된 2열 Vocabulary 표: 좌측 영단어 목록 + 우측 한국어 뜻 목록 1:1 정확 매칭
"""

from __future__ import annotations

import json
import re
from typing import List, Optional, Sequence

from pydantic import BaseModel, Field

from core.hwp_reader import extract_vocab_by_passage_from_text, prefilter_text_by_numbers

# 원문자(❶~⓴) 숫자 매핑 및 역매핑
_CIRCLED_CHARS: List[str] = [
    "❶", "❷", "❸", "❹", "❺", "❻", "❼", "❽", "❾", "❿",
    "⓫", "⓬", "⓭", "⓮", "⓯", "⓰", "⓱", "⓲", "⓳", "⓴",
]
_CIRCLED_NUM_MAP: dict[str, int] = {ch: idx + 1 for idx, ch in enumerate(_CIRCLED_CHARS)}

# 1) 문장 삽입 기호: ( ① ), (②), ( ③ )
_INSERTION_MARKER_RE = re.compile(r"\(\s*[①②③④⑤]\s*\)\s*")

# 2) 어법/어휘 오답 → 정답 치환 패턴 (영어)
# 예: "④ what (→ that)", "⑤ uninterested (→ potential)", "(b) include (→ eliminate)"
_EN_CORRECTION_RE = re.compile(
    r"(?:[①②③④⑤]\s*|\([a-e]\)\s*)?(?:[A-Za-z0-9'’-]+(?:\s+[A-Za-z0-9'’-]+)?)\s*\(\s*(?:→|->)\s*([^)]+?)\s*\)"
)

# 3) 어휘 오답 → 정답 치환 패턴 (한국어 해석)
# 예: "무관심한(→ 잠재적인)", "포함한다(→ 제거한다)"
_KO_CORRECTION_RE = re.compile(
    r"[가-힣A-Za-z0-9·]+\s*\(\s*(?:→|->)\s*([^)]+?)\s*\)"
)

# 4) 본문 내 잔여 문제 기호 제거: 단독 ①~⑤, (a)~(e), 문두 (A)~(D)
_STANDALONE_CIRCLED_CHOICE_RE = re.compile(r"[①②③④⑤]\s*")
_LETTER_MARKER_RE = re.compile(r"\(\s*[a-eA-D]\s*\)\s*")


class VocabItem(BaseModel):
    """단어 및 뜻 항목."""

    word: str = Field(description="영단어 또는 숙어 (예: break ~ up, perceive ~ as ...)")
    meaning: str = Field(description="한국어 뜻 (예: ~을 해체하다, 분해하다)")


class PassageData(BaseModel):
    """단일 지문 구조화 데이터."""

    number: int = Field(description="대표 지문 번호 (예: 21, 29, 39, 장문 41~42번이면 41)")
    display_number: str = Field(
        default="",
        description="표시용 번호 (단일 문항이면 '29', 장문이면 '41~42' 또는 '43~45')",
    )
    question_type: str = Field(
        default="유형 미상",
        description="기존유형 (예: 함축 의미 추론, 어법 추론, 어휘 추론, 문장 삽입, 순서 추론, 무관한 문장 찾기)",
    )
    title_ko: str = Field(
        default="",
        description="한국어 주제/제목 (원본의 Subject / Title 항목)",
    )
    summary_en: str = Field(
        default="",
        description="지문 분석 우측 칸에 들어갈 간결한 영어 한 줄 요약 (1문장 또는 명사구)",
    )
    english_sentences: List[str] = Field(
        default_factory=list,
        description="원문자 숫자 순서(❶, ❷, ❸, ...)대로 정렬되고 오답/문제 기호가 모두 정제된 순수 영어 원문 문장 리스트",
    )
    footnotes: str = Field(
        default="",
        description="본문 하단 각주 단어 (예: *retrieve 상기하다 **primacy 우위성). 없으면 빈 문자열",
    )
    korean_sentences: List[str] = Field(
        default_factory=list,
        description="원문자 숫자 순서(❶, ❷, ❸, ...)대로 정렬되고 오답/기호가 정제된 우리말 해석 문장 리스트",
    )
    vocabulary: List[VocabItem] = Field(
        default_factory=list,
        description="원본 Vocabulary 표의 영단어-한국어 뜻 1:1 매칭 목록 (원래 순서 유지)",
    )

    @property
    def label(self) -> str:
        """표시용 번호 문자열을 반환합니다 (예: '29', '41~42')."""
        return (self.display_number or str(self.number)).strip()


class ExtractionResult(BaseModel):
    """전체 추출 결과."""

    passages: List[PassageData] = Field(default_factory=list)


SYSTEM_PROMPT = """당신은 대한민국 고등영어 내신 교안 제작 전문가입니다.
주어진 모의고사 교사용 한글 파일(아잉카 등) 텍스트 또는 이미지에서 사용자가 요청한 지문 번호의 내용만 추출하고,
**학생이 공부할 깨끗한 '원 문장' 상태**로 정제하여 JSON으로 반환하세요.

[유형별 필수 정제 규칙 — 반드시 모두 준수]
1. **지문 번호 필터링**:
   - 사용자가 지정한 지문 번호만 추출하세요.
   - 장문 독해(`41~42`, `43~45`)는 해당 범위 번호 중 하나만 요청되어도 1개의 지문으로 추출하고, `number`는 시작 번호(41 또는 43), `display_number`는 `"41~42"` 또는 `"43~45"`로 적으세요.
2. **어법 추론 (29번 등) & 어휘 추론 (30번, 41~42번 등)**:
   - 본문 속 `①`, `②`, `③`, `④`, `⑤` 및 `(a)`, `(b)`, `(c)`, `(d)`, `(e)` 기호를 모두 제거하세요.
   - 틀린 어법/어휘가 `④ what (→ that)`, `⑤ uninterested (→ potential)`, `(b) include (→ eliminate)`처럼 표기되어 있으면 **원래 틀린 단어와 화살표 괄호를 지우고 올바른 원 문장 어휘(`that`, `potential`, `eliminate`)만 남기세요.**
   - 우리말 해석에서도 `무관심한(→ 잠재적인)`, `포함한다(→ 제거한다)`처럼 되어 있으면 **틀린 표현을 지우고 올바른 해석(`잠재적인`, `제거한다`)만 남기세요.**
3. **무관한 문장 찾기 (35번 등)**:
   - 본문 속 `①~⑤` 기호를 제거하세요.
   - **전체 흐름과 관계 없는 문장 1개**(교사용 한글 해석에서 보통 `(...)` 괄호로 묶여 있거나 정답 번호에 해당하는 문장)를 영어 본문과 우리말 해석 **양쪽 모두에서 완전히 삭제**하세요.
   - 삭제 후 남은 문장들은 `❶, ❷, ❸, ❹, ...`로 빈 번호 없이 연속해서 번호를 다시 매기세요.
4. **문장 삽입 (38~39번) & 순서 추론 (36~37번, 43~45번)**:
   - 상단 박스에 떨어져 있는 문장(예: ❹, ❻)을 본문 속 제자리로 옮겨 **반드시 원문자 숫자 순서(`❶ → ❷ → ❸ → ...`)대로 정렬**하세요.
   - `( ① )`, `( ② )`, `( ③ )`, `( ④ )`, `( ⑤ )`, `(A)`, `(B)`, `(C)`, `(D)`, `(a)~(e)` 기호는 영어 본문과 우리말 해석에서 모두 제거하세요.
5. **요약문 추론 (40번)**:
   - 본문 아래 `↓` 이후의 요약문(예: `❾ (A) Logical thinking ... (B) innovative solutions.`)은 본문(`english_sentences`, `korean_sentences`)에서 제외하세요.
   - 대신 요약문에서 `(A)`, `(B)`를 지운 깔끔한 영어 문장을 `summary_en`으로 활용하면 좋습니다.
6. **빈칸 추론 (31~34번) 및 일반 유형 (18~28번)**:
   - 문제 발문과 하단 5지선다 선택지(`①~⑤`)는 제외하고 순수 원문 문장만 남기세요.
7. **분리된 2열 Vocabulary 표 100% 원문 그대로 전수 추출 (절대 누락·의역 금지)**:
   - 원본 한글 파일의 `■ Vocabulary` 영역은 왼쪽 칸에 영단어가 한꺼번에, 오른쪽 칸에 한국어 뜻이 한꺼번에 나오는 2열 표 구조입니다.
   - `■ Vocabulary`에 있는 **모든 단어(보통 12~30개)를 단 1개도 빠뜨리지 말고 100% 전부** 추출하세요. 절대로 일부 핵심 단어만 요약하거나 본문 각주(`*`, `**`)를 임의로 섞어 넣지 마세요.
   - 한국어 뜻도 임의로 바꾸지 말고 원문 `■ Vocabulary`에 적힌 표현을 그대로 유지하세요(예: `영향을 주다`를 `영향을 미치다`로 바꾸지 말 것).
   - 줄바꿈으로 잘린 표현(예: `one way or -` / `another`, `income -` / `distribution`)만 하나의 온전한 표현으로 합쳐 1:1로 매칭하세요.
8. **공통**:
   - `title_ko`에는 `Subject / Title` 칸의 한국어 주제를, `footnotes`에는 본문 아래 별표 각주(`* ...`)를 넣으세요.
   - 각 문장은 원문자(`❶`, `❷`, ...)로 시작하게 하세요.
"""


def _extract_leading_num(sentence: str) -> Optional[int]:
    s = sentence.strip()
    if s and s[0] in _CIRCLED_NUM_MAP:
        return _CIRCLED_NUM_MAP[s[0]]
    return None


def _strip_leading_circled(sentence: str) -> str:
    s = sentence.strip()
    if s and s[0] in _CIRCLED_NUM_MAP:
        return s[1:].strip()
    return s


def clean_english_sentence(sentence: str) -> str:
    """영어 문장에서 어법/어휘 오답 표기(`wrong (→ right)`)와 문제 기호를 정제합니다."""
    s = sentence.strip()
    if not s:
        return ""
    # 1. wrong (→ right) -> right
    s = _EN_CORRECTION_RE.sub(r"\1", s)
    # 2. ( ① )~( ⑤ ) 제거
    s = _INSERTION_MARKER_RE.sub("", s)
    # 3. (a)~(e), (A)~(D) 제거
    s = _LETTER_MARKER_RE.sub("", s)
    # 4. 본문 내 단독 ①~⑤ 제거
    s = _STANDALONE_CIRCLED_CHOICE_RE.sub("", s)
    # 5. 다중 공백 정리
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def clean_korean_sentence(sentence: str) -> str:
    """우리말 해석에서 오답 표기(`틀린뜻(→ 맞는뜻)`)와 순서 기호 `(A)~(D)`를 정제합니다."""
    s = sentence.strip()
    if not s:
        return ""
    s = _KO_CORRECTION_RE.sub(r"\1", s)
    s = _LETTER_MARKER_RE.sub("", s)
    s = re.sub(r"^→\s*", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def normalize_and_sort_sentences(
    sentences: Sequence[str],
    is_english: bool = True,
    renumber_consecutively: bool = False,
) -> List[str]:
    """문장을 정제한 뒤 원문자 숫자(❶→❷→...) 순서로 강제 정렬합니다."""
    cleaner = clean_english_sentence if is_english else clean_korean_sentence
    cleaned = [cleaner(raw) for raw in sentences]
    cleaned = [s for s in cleaned if s]

    indexed = []
    has_circled = False
    for idx, s in enumerate(cleaned):
        num = _extract_leading_num(s)
        if num is not None:
            has_circled = True
            indexed.append((num, idx, s))
        else:
            indexed.append((9999, idx, s))

    if has_circled:
        indexed.sort(key=lambda item: (item[0], item[1]))
        result = [item[2] for item in indexed]
    else:
        result = cleaned

    # 무관한 문장 삭제 등으로 번호에 구멍이 생긴 경우 ❶, ❷, ❸... 연속 재번호
    if renumber_consecutively and result and has_circled:
        renumbered: List[str] = []
        for idx, s in enumerate(result):
            body = _strip_leading_circled(s)
            prefix = _CIRCLED_CHARS[idx] if idx < len(_CIRCLED_CHARS) else f"({idx + 1})"
            renumbered.append(f"{prefix} {body}")
        return renumbered

    return result


def postprocess_passage(passage: PassageData) -> PassageData:
    """추출된 단일 지문에 유형별 정제·숫자 순 정렬·연속 재번호를 적용합니다."""
    if not passage.display_number:
        passage.display_number = str(passage.number)

    # 무관한 문장 제거 후 번호 구멍이 있는지 확인
    en_nums = [_extract_leading_num(s) for s in passage.english_sentences if s.strip()]
    valid_en_nums = [n for n in en_nums if n is not None]
    has_gap = bool(valid_en_nums) and (sorted(valid_en_nums) != list(range(1, len(valid_en_nums) + 1)))
    is_irrelevant_type = "무관" in (passage.question_type or "")
    need_renumber = has_gap or is_irrelevant_type

    passage.english_sentences = normalize_and_sort_sentences(
        passage.english_sentences,
        is_english=True,
        renumber_consecutively=need_renumber,
    )
    passage.korean_sentences = normalize_and_sort_sentences(
        passage.korean_sentences,
        is_english=False,
        renumber_consecutively=need_renumber,
    )
    if passage.summary_en:
        passage.summary_en = clean_english_sentence(passage.summary_en)
    return passage


def _build_user_prompt(
    target_numbers: Sequence[int],
    auto_summary_en: bool = True,
) -> str:
    if target_numbers:
        num_str = ", ".join(str(n) for n in target_numbers)
        target_instruction = f"반드시 다음 지문 번호만 추출하세요: [{num_str}번]"
    else:
        target_instruction = "문서에 포함된 모든 지문을 번호 순서대로 추출하세요."

    summary_instruction = (
        "summary_en 필드는 각 지문의 핵심 내용을 간결한 영어 1줄로 작성해 주세요(40번 요약문 유형이면 정제된 요약문을 사용)."
        if auto_summary_en
        else "원문에 영어 요약이 없으면 summary_en은 빈 문자열(\"\")로 비워 두세요."
    )

    return f"{target_instruction}\n{summary_instruction}\n요청한 JSON 스키마에 맞춰 정확히 출력하세요."


def _matches_target(passage: PassageData, wanted: set[int]) -> bool:
    """단일 번호(29) 및 장문 복합 번호(41~42, 43~45) 매칭 여부를 확인합니다."""
    if passage.number in wanted:
        return True
    m = re.match(r"^\s*(\d+)\s*[~-]\s*(\d+)\s*$", passage.label)
    if m:
        s, e = int(m.group(1)), int(m.group(2))
        return any(n in wanted for n in range(s, e + 1))
    return False



# 특수 목적 모델(이미지 생성/TTS/임베딩/라이브 등) 제외 키워드
_EXCLUDED_MODEL_KEYWORDS = (
    "embedding", "imagen", "veo", "tts", "audio", "image",
    "live", "robotics", "computer-use", "aqa", "bisociative",
)

# API 목록 조회 실패 시 사용할 최신 경량 무료 모델 우선순위 폴백
_FALLBACK_LIGHT_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-2.5-flash",
]


def _extract_version_tuple(model_id: str) -> tuple[int, int]:
    """모델명에서 버전 번호(예: 3.5 -> (3, 5))를 추출합니다."""
    m = re.search(r"gemini-(\d+)(?:\.(\d+))?", model_id.lower())
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2) or 0))


def rank_lightest_free_models(model_ids: Sequence[str]) -> List[str]:
    """사용 가능한 모델 ID 목록을 '무료 최저 사용량(Flash-Lite 우선 -> 최신 안정판 우선)' 순으로 정렬합니다."""
    candidates: List[str] = []
    for raw_name in model_ids:
        name = raw_name.replace("models/", "").strip()
        lower = name.lower()
        if not lower.startswith("gemini-"):
            continue
        if any(bad in lower for bad in _EXCLUDED_MODEL_KEYWORDS):
            continue
        if "pro" in lower or "ultra" in lower or "argon" in lower or "carbon" in lower:
            continue
        if "flash" not in lower:
            continue
        candidates.append(name)

    def sort_key(name: str) -> tuple:
        lower = name.lower()
        is_lite = 1 if "lite" in lower else 0
        is_latest_alias = 1 if lower == "gemini-flash-lite-latest" else 0
        is_stable = 0 if ("preview" in lower or "exp" in lower) else 1
        major, minor = _extract_version_tuple(lower)
        # Flash-Lite 최우선 > 최신 버전 우선 > 안정판 우선 > latest 별칭
        return (is_lite, major, minor, is_stable, is_latest_alias)

    unique = list(dict.fromkeys(candidates))
    unique.sort(key=sort_key, reverse=True)
    return unique



# API 키 입력 전 또는 조회 실패 시 표시할 최신 추천 모델 기본 목록
DEFAULT_MODEL_CHOICES = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.1-pro-preview",
    "gemini-2.5-flash",
]


def rank_all_gemini_models(model_ids: Sequence[str]) -> List[str]:
    """계정에서 사용 가능한 모든 최신 Gemini 텍스트/멀티모달 모델을 최신 세대·성능 순으로 정렬합니다."""
    candidates: List[str] = []
    for raw_name in model_ids:
        name = raw_name.replace("models/", "").strip()
        lower = name.lower()
        if not lower.startswith("gemini-"):
            continue
        if any(bad in lower for bad in _EXCLUDED_MODEL_KEYWORDS):
            continue
        candidates.append(name)

    def sort_key(name: str) -> tuple:
        lower = name.lower()
        major, minor = _extract_version_tuple(lower)
        # 티어 가중치: lite(1) < flash(2) < pro/argon/carbon(3) (같은 세대 내에서 성능 확인 용이)
        if "lite" in lower:
            tier = 1
        elif "flash" in lower:
            tier = 2
        else:
            tier = 3
        is_stable = 0 if ("preview" in lower or "exp" in lower) else 1
        return (major, minor, is_stable, tier)

    unique = list(dict.fromkeys(candidates))
    unique.sort(key=sort_key, reverse=True)
    return unique


def list_available_gemini_models(api_key: str) -> List[str]:
    """Gemini API에서 현재 사용 가능한 최신 모델 목록을 실시간 조회합니다."""
    if not api_key or not api_key.strip():
        return list(DEFAULT_MODEL_CHOICES)
    try:
        from google import genai
    except ImportError:
        return list(DEFAULT_MODEL_CHOICES)

    discovered: List[str] = []
    try:
        client = genai.Client(api_key=api_key.strip())
        for m in client.models.list():
            m_name = getattr(m, "name", "") or ""
            methods = (
                getattr(m, "supported_actions", None)
                or getattr(m, "supported_generation_methods", None)
                or []
            )
            if methods and not any("generateContent" in str(a) for a in methods):
                continue
            discovered.append(m_name)
    except Exception:
        return list(DEFAULT_MODEL_CHOICES)

    ranked = rank_all_gemini_models(discovered)
    return ranked if ranked else list(DEFAULT_MODEL_CHOICES)


def resolve_lightest_free_models(client) -> List[str]:
    """현재 API 키로 호출 가능한 무료 최저 사용량(Flash-Lite) 모델 후보 목록을 동적으로 조회합니다."""
    discovered: List[str] = []
    try:
        for m in client.models.list():
            m_name = getattr(m, "name", "") or ""
            methods = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or []
            if methods and not any("generateContent" in str(a) for a in methods):
                continue
            discovered.append(m_name)
    except Exception:
        discovered = []

    ranked = rank_lightest_free_models(discovered)
    for fb in _FALLBACK_LIGHT_MODELS:
        if fb not in ranked:
            ranked.append(fb)
    return ranked


def extract_passages_with_gemini(
    api_key: str,
    raw_text: Optional[str] = None,
    image_bytes_list: Optional[List[tuple[bytes, str]]] = None,
    target_numbers: Sequence[int] = (),
    auto_summary_en: bool = True,
    model_name: Optional[str] = None,
) -> tuple[List[PassageData], str]:
    """Gemini API를 호출해 지문 목록을 구조화 JSON으로 추출합니다.

    model_name을 비워 두면(기본값) 현재 계정에서 사용 가능한 무료 최저 사용량(Flash-Lite) 모델을
    자동 탐색하여 호출하며, 할당량/미지원 오류 시 다음 경량 모델로 자동 전환합니다.

    Returns:
        (추출된 PassageData 리스트, 실제 사용된 모델명)
    """
    if not api_key or not api_key.strip():
        raise ValueError("Gemini API 키를 입력해 주세요.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise ImportError(
            "google-genai 패키지가 설치되어 있지 않습니다. `pip install google-genai`를 실행해 주세요."
        ) from exc

    client = genai.Client(api_key=api_key.strip())
    contents: list = []

    user_prompt = _build_user_prompt(target_numbers, auto_summary_en=auto_summary_en)
    contents.append(user_prompt)

    if raw_text:
        filtered = prefilter_text_by_numbers(raw_text, target_numbers)
        contents.append(
            f"\n\n--- [원본 한글 파일 추출 텍스트 시작] ---\n{filtered}\n--- [원본 텍스트 끝] ---"
        )

    if image_bytes_list:
        for img_bytes, mime_type in image_bytes_list:
            contents.append(types.Part.from_bytes(data=img_bytes, mime_type=mime_type))

    if model_name and model_name.strip():
        candidate_models = [model_name.strip()]
    else:
        candidate_models = resolve_lightest_free_models(client)

    last_err: Optional[Exception] = None
    used_model = candidate_models[0]
    response = None

    for cand in candidate_models[:5]:
        try:
            response = client.models.generate_content(
                model=cand,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=ExtractionResult,
                    temperature=0.1,
                ),
            )
            used_model = cand
            break
        except Exception as err:
            last_err = err
            err_msg = str(err).lower()
            # 인증 오류(API 키 잘못됨)는 즉시 중단
            if "api key" in err_msg or "invalid_argument" in err_msg or "unauthenticated" in err_msg:
                raise
            continue

    if response is None:
        raise RuntimeError(
            f"사용 가능한 무료 경량 모델 호출에 모두 실패했습니다. 마지막 오류: {last_err}"
        )

    parsed = ExtractionResult.model_validate_json(response.text)
    passages = [postprocess_passage(p) for p in parsed.passages]

    if target_numbers:
        wanted = set(target_numbers)
        passages = [p for p in passages if _matches_target(p, wanted)]
        passages.sort(key=lambda p: p.number)
    else:
        passages.sort(key=lambda p: p.number)


    # [핵심 보정] 원본 HWP 텍스트의 `■ Vocabulary` 블록을 Python으로 직접 파싱해
    # 단어가 1개라도 누락되거나 뜻이 임의로 바뀌지 않도록 100% 원문 그대로 보정합니다.
    if raw_text:
        vocab_map = extract_vocab_by_passage_from_text(raw_text)
        for p in passages:
            entry = vocab_map.get(p.number)
            if not entry:
                continue
            en_list, ko_list = entry
            if not en_list:
                continue
            # Case 1: 영단어 개수 == 한국어 뜻 개수 -> 100% 결정론적 원문 1:1 매칭 (LLM 누락/의역 원천 차단)
            if len(en_list) == len(ko_list):
                p.vocabulary = [
                    VocabItem(word=w, meaning=m) for w, m in zip(en_list, ko_list)
                ]
            # Case 2: 줄바꿈 등으로 개수가 살짝 다른데 Gemini가 단어를 누락했다면,
            # 해당 Vocabulary 블록만 단독으로 다시 정렬 요청해 전수 복구
            elif len(p.vocabulary) < len(en_list):
                try:
                    align_prompt = (
                        "아래는 원본 한글 파일의 `■ Vocabulary` 2열 표에서 추출한 영단어 목록과 한국어 뜻 목록입니다.\n"
                        f"영단어 목록({len(en_list)}개)의 모든 단어를 단 1개도 빠뜨리지 말고 순서대로 유지하면서, "
                        "한국어 뜻 목록의 원문 표현을 그대로 사용해 1:1로 정확히 매칭한 JSON을 반환하세요.\n"
                        "임의로 단어를 추가/삭제하거나 뜻을 의역하지 마세요.\n\n"
                        "[영단어 목록]\n" + "\n".join(f"{i+1}. {w}" for i, w in enumerate(en_list)) + "\n\n"
                        "[한국어 뜻 목록]\n" + "\n".join(f"{i+1}. {m}" for i, m in enumerate(ko_list))
                    )

                    class _VocabOnly(BaseModel):
                        vocabulary: List[VocabItem]

                    align_resp = client.models.generate_content(
                        model=used_model,
                        contents=[align_prompt],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=_VocabOnly,
                            temperature=0.0,
                        ),
                    )
                    aligned = _VocabOnly.model_validate_json(align_resp.text)
                    if len(aligned.vocabulary) >= len(p.vocabulary):
                        p.vocabulary = aligned.vocabulary
                except Exception:
                    # 최후 안전장치: 앞쪽 N개라도 원문 영단어 누락 없이 보전
                    if len(ko_list) >= len(en_list):
                        p.vocabulary = [
                            VocabItem(word=w, meaning=m) for w, m in zip(en_list, ko_list[: len(en_list)])
                        ]

    return passages, used_model


def passages_to_json(passages: Sequence[PassageData]) -> str:
    """디버깅/미리보기용 JSON 직렬화."""
    return json.dumps(
        [p.model_dump() for p in passages],
        ensure_ascii=False,
        indent=2,
    )
