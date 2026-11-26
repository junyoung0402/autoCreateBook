"""모의고사 교사용 한글(.hwp/.hwpx) -> 내신 분석 교안(.hwpx/.hwp) 자동화 앱.

- 웹 배포: Streamlit Community Cloud / Render 등에 그대로 배포 가능
- 데스크톱 실행: Windows(run_windows.bat / .exe) 및 macOS(run_mac.sh)에서 실행 가능
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import List

import streamlit as st

from core.gemini_parser import (
    PassageData,
    VocabItem,
    extract_passages_with_gemini,
    list_available_gemini_models,
)
from core.hwp_reader import extract_text_from_file, parse_passage_numbers
from core.hwpx_builder import WorkbookConfig, build_hwpx_bytes
from core.win_hwp_converter import convert_hwpx_to_hwp, is_windows_hwp_available

st.set_page_config(
    page_title="영어 내신 교안 한글 자동화",
    page_icon="📘",
    layout="wide",
)


def _get_default_api_key() -> str:
    """환경변수 또는 Streamlit Secrets에서 Gemini API 키를 자동으로 읽어옵니다."""
    env_key = os.getenv("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key
    try:
        secret_key = st.secrets.get("GEMINI_API_KEY", "")
        return str(secret_key).strip()
    except Exception:
        return ""



AUTO_MODEL_LABEL = "자동 선택 (무료 최저 사용량 Flash-Lite 우선)"


@st.cache_data(ttl=600, show_spinner=False)
def _cached_fetch_models(api_key: str) -> List[str]:
    return list_available_gemini_models(api_key)


def main() -> None:
    st.title("📘 영어 내신 교안 한글 자동화 프로그램")
    st.caption(
        "모의고사 교사용 한글 파일(.hwp / .hwpx) 또는 지문 이미지를 업로드하고 원하는 지문 번호만 입력하면 "
        "VOCABULARY 표와 지문 분석 페이지를 한글 파일(.hwpx)로 자동 생성합니다."
    )

    with st.sidebar:
        st.header("⚙️ 설정")
        default_key = _get_default_api_key()
        api_key = st.text_input(
            "Gemini API 키",
            value=default_key,
            type="password",
            help="Google AI Studio(aistudio.google.com)에서 발급받은 API 키를 입력하세요. 웹 배포 시 Secrets에 등록해 두면 자동 입력됩니다.",
        )

        available_models = _cached_fetch_models(api_key)
        model_options = [AUTO_MODEL_LABEL] + available_models
        selected_model_label = st.selectbox(
            "Gemini 모델 선택 (실시간 최신화)",
            options=model_options,
            index=0,
            help=(
                "API 키를 입력하면 현재 사용 가능한 최신 모델 목록이 자동으로 최신화됩니다. "
                "단어 파싱 정확도를 높이려면 Flash 또는 Pro 상위 모델을 선택하세요."
            ),
        )
        if st.button("🔄 최신 모델 목록 새로고침", use_container_width=True):
            _cached_fetch_models.clear()
            st.rerun()
        chosen_model = None if selected_model_label == AUTO_MODEL_LABEL else selected_model_label

        st.divider()
        st.subheader("교안 출력 옵션")
        header_title = st.text_input(
            "지문 상단 대제목 (연두색 19pt)",
            value="고등영어,아작 – 2026년 10월 모의고사 – 2학기 2차 내신대비",
        )
        page_header_text = st.text_input(
            "문서 머리말 (선택)",
            value="",
            placeholder="비워 두면 원본과 동일하게 빈 머리말",
        )
        page_footer_text = st.text_input(
            "문서 꼬리말 텍스트 (선택)",
            value="",
            placeholder="예: 효원고1 내신대비 (비워 두면 쪽 번호만 표시)",
        )
        show_page_num = st.checkbox("꼬리말에 자동 쪽 번호 표시 (- 1 -)", value=True)
        include_vocab = st.checkbox("VOCABULARY 표 포함 (앞쪽 어휘 정리)", value=True)
        include_vocab_test = st.checkbox("VOCABULARY TEST 표 포함 (뜻 빈칸)", value=False)
        auto_summary_en = st.checkbox("영어 한 줄 요약 자동 생성 (지문 분석 상단)", value=True)

        st.divider()
        if is_windows_hwp_available():
            st.success("Windows 한글(COM) 연동 가능 (.hwp 직접 변환 지원)")
        else:
            st.info(
                "현재 환경에서는 표준 한글 파일(.hwpx)로 출력됩니다. "
                "Windows/Mac 한글 프로그램에서 바로 열립니다."
            )

    # 1. 입력 영역
    col_upload, col_nums = st.columns([2, 1])
    with col_upload:
        uploaded_files = st.file_uploader(
            "원본 교사용 파일 업로드 (.hwp, .hwpx 또는 지문 이미지 .jpg/.png)",
            type=["hwp", "hwpx", "jpg", "jpeg", "png"],
            accept_multiple_files=True,
        )

    with col_nums:
        passage_spec = st.text_input(
            "추출할 지문 번호",
            placeholder="예: 21, 22, 29-31 (비우면 전체)",
            help="쉼표(,)로 여러 번호를 구분하거나 하이픈(-)으로 범위를 지정할 수 있습니다.",
        )
        output_filename = st.text_input(
            "저장할 파일명 (확장자 제외)",
            value="내신교안_변환결과",
        )

    # 2. 추출 실행 버튼
    if st.button("🚀 선택한 지문 추출하기", type="primary", use_container_width=True):
        if not uploaded_files:
            st.error("먼저 원본 한글 파일(.hwp/.hwpx) 또는 지문 이미지를 업로드해 주세요.")
            return
        if not api_key:
            st.error("왼쪽 사이드바에 Gemini API 키를 입력해 주세요.")
            return

        try:
            target_numbers = parse_passage_numbers(passage_spec)
        except ValueError as err:
            st.error(str(err))
            return

        raw_texts: List[str] = []
        image_payloads: List[tuple[bytes, str]] = []

        with st.spinner("원본 파일에서 텍스트/이미지를 읽는 중..."):
            try:
                for uf in uploaded_files:
                    file_bytes = uf.getvalue()
                    ext = Path(uf.name).suffix.lower()
                    if ext in (".hwp", ".hwpx"):
                        text = extract_text_from_file(file_bytes, filename=uf.name)
                        raw_texts.append(text)
                    elif ext in (".jpg", ".jpeg", ".png"):
                        mime = "image/png" if ext == ".png" else "image/jpeg"
                        image_payloads.append((file_bytes, mime))
            except Exception as err:
                st.error(f"파일 읽기 오류: {err}")
                return

        combined_text = "\n\n".join(raw_texts) if raw_texts else None

        with st.spinner("Gemini AI가 선택한 지문과 Vocabulary를 구조화하는 중..."):
            try:
                passages, used_model = extract_passages_with_gemini(
                    api_key=api_key,
                    raw_text=combined_text,
                    image_bytes_list=image_payloads or None,
                    target_numbers=target_numbers,
                    auto_summary_en=auto_summary_en,
                    model_name=chosen_model,
                )
            except Exception as err:
                st.error(f"Gemini 추출 중 오류가 발생했습니다: {err}")
                return

        if not passages:
            st.warning("요청하신 지문 번호를 원본 파일에서 찾지 못했습니다. 번호를 다시 확인해 주세요.")
            return

        st.session_state["extracted_passages"] = passages
        st.session_state["used_model"] = used_model
        st.success(
            f"총 {len(passages)}개 지문 ({', '.join(f'{p.label}번' for p in passages)}) 추출 완료! "
            f"(사용 모델: `{used_model}`)"
        )

    # 3. 미리보기, 수정 및 한글 파일 생성
    passages: List[PassageData] | None = st.session_state.get("extracted_passages")
    if passages:
        st.divider()
        st.subheader("📝 추출 결과 검수 및 수정")
        st.caption("한글 파일로 내보내기 전에 제목·본문·해석·단어를 바로 수정할 수 있습니다.")

        edited_passages: List[PassageData] = []
        tabs = st.tabs([f"{p.label}번 ({p.question_type})" for p in passages])

        for idx, (tab, p) in enumerate(zip(tabs, passages)):
            with tab:
                c1, c2 = st.columns([1, 2])
                q_type = c1.text_input("기존유형", value=p.question_type, key=f"qtype_{idx}")
                title_ko = c2.text_input("내용 (한국어 주제)", value=p.title_ko, key=f"title_{idx}")
                summary_en = st.text_input("영어 한 줄 요약", value=p.summary_en, key=f"sum_{idx}")

                en_text = st.text_area(
                    "영어 본문 (줄바꿈으로 문장 구분)",
                    value="\n".join(p.english_sentences),
                    height=180,
                    key=f"en_{idx}",
                )
                footnotes = st.text_input("각주 (*단어 뜻)", value=p.footnotes, key=f"fn_{idx}")
                ko_text = st.text_area(
                    "우리말 해석",
                    value="\n".join(p.korean_sentences),
                    height=140,
                    key=f"ko_{idx}",
                )
                vocab_raw = st.text_area(
                    "Vocabulary (한 줄에 `영단어 | 한국어 뜻` 형식)",
                    value="\n".join(f"{v.word} | {v.meaning}" for v in p.vocabulary),
                    height=180,
                    key=f"voc_{idx}",
                )

                parsed_vocab: List[VocabItem] = []
                for line in vocab_raw.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if "|" in line:
                        w, m = line.split("|", 1)
                        parsed_vocab.append(VocabItem(word=w.strip(), meaning=m.strip()))
                    else:
                        parsed_vocab.append(VocabItem(word=line, meaning=""))

                edited_passages.append(
                    PassageData(
                        number=p.number,
                        display_number=p.display_number,
                        question_type=q_type.strip(),
                        title_ko=title_ko.strip(),
                        summary_en=summary_en.strip(),
                        english_sentences=[s.strip() for s in en_text.splitlines() if s.strip()],
                        footnotes=footnotes.strip(),
                        korean_sentences=[s.strip() for s in ko_text.splitlines() if s.strip()],
                        vocabulary=parsed_vocab,
                    )
                )

        st.divider()
        cfg = WorkbookConfig(
            header_title=header_title,
            page_header_text=page_header_text,
            page_footer_text=page_footer_text,
            show_page_number_in_footer=show_page_num,
            include_vocabulary_table=include_vocab,
            include_vocab_test_table=include_vocab_test,
        )
        hwpx_bytes = build_hwpx_bytes(edited_passages, config=cfg)
        safe_stem = (output_filename.strip() or "내신교안_변환결과").replace("/", "_")

        dl_col1, dl_col2 = st.columns(2)
        with dl_col1:
            st.download_button(
                label="📥 한글 파일 다운로드 (.hwpx — Windows/Mac 공통)",
                data=hwpx_bytes,
                file_name=f"{safe_stem}.hwpx",
                mime="application/hwp+zip",
                type="primary",
                use_container_width=True,
            )

        with dl_col2:
            if is_windows_hwp_available():
                if st.button("🔄 구버전 .hwp 파일로 변환 생성 (Windows 한글)", use_container_width=True):
                    with st.spinner("한글(COM)로 .hwp 변환 중..."):
                        with tempfile.TemporaryDirectory() as tmpdir:
                            tmp_hwpx = Path(tmpdir) / f"{safe_stem}.hwpx"
                            tmp_hwp = Path(tmpdir) / f"{safe_stem}.hwp"
                            tmp_hwpx.write_bytes(hwpx_bytes)
                            convert_hwpx_to_hwp(tmp_hwpx, tmp_hwp)
                            hwp_bytes = tmp_hwp.read_bytes()
                    st.download_button(
                        label="📥 구버전 한글 파일 다운로드 (.hwp)",
                        data=hwp_bytes,
                        file_name=f"{safe_stem}.hwp",
                        mime="application/x-hwp",
                        use_container_width=True,
                    )


if __name__ == "__main__":
    main()
