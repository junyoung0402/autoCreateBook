"""표준 OWPML(.hwpx) 학원 내신 교안 생성기 — 효원고 원본 HWP 스타일 100% 반영.

첨부된 `효원고1_26년 10월 모의고사_어휘 및 본문.hwp`에서 직접 추출한
용지 여백, 머리말/꼬리말, 글꼴, 크기, 색상, 표 구성을 동일하게 적용합니다:
- 용지: A4 (59528 x 84188), 좌우 10mm(2835), 상하 5mm(1417), 머리말/꼬리말 10mm(2835)
- 머리말(Header) & 꼬리말(Footer, 자동 쪽 번호 포함) OWPML 컨트롤 적용
- 폰트: 맑은 고딕, LG Smart UI SemiBold, 210 맨발의청춘 R, 12롯데마트드림Medium, 함초롬돋움
- 색상/크기:
  * 대제목(고등영어,아작 ...): LG Smart UI SemiBold 19pt Bold #85BF4C
  * 지문번호(21번): LG Smart UI SemiBold 14pt Bold #7F7F7F
  * ※ 기존유형: LG Smart UI SemiBold 12pt #85BF4C
  * 섹션 라벨(내용/지문 분석/우리말 해석/단어 및 숙어/변형 적합유형/NOTE): 210 맨발의청춘 R 13pt Bold #817CC3
  * 내용·영어 본문: 맑은 고딕 11.5pt #000000
  * 우리말 해석·단어 및 숙어: 맑은 고딕 8.0pt #000000
  * 변형 적합유형 체크박스: 12롯데마트드림Medium 9.0pt #000000
  * VOCABULARY 제목: 210 맨발의청춘 R 15pt Bold #999999
"""

from __future__ import annotations

import io
import math
import zipfile
from dataclasses import dataclass
from typing import List, Sequence
from xml.sax.saxutils import escape

from core.gemini_parser import PassageData, postprocess_passage

# 효원고 원본 HWP Section1 PageDef 실측값 (HWPUNIT)
PAGE_WIDTH = 59528
PAGE_HEIGHT = 84188
MARGIN_LR = 2835       # 좌우 10mm
MARGIN_TB = 1417       # 상하 5mm
MARGIN_HEADER = 2835   # 머리말 10mm
MARGIN_FOOTER = 2835   # 꼬리말 10mm
CONTENT_WIDTH = PAGE_WIDTH - (MARGIN_LR * 2)  # 53858

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS_HS = "http://www.hancom.co.kr/hwpml/2011/section"
NS_HH = "http://www.hancom.co.kr/hwpml/2011/head"
NS_HC = "http://www.hancom.co.kr/hwpml/2011/core"

VARIANT_TYPES_LEFT = [
    "□ 주제/요지/주장/제목",
    "□ 요약문 추론",
    "□ 무관한 문장 찾기",
    "□ 내용 (불)일치",
    "□ 지칭 추론",
    "□ 심경/분위기/추론",
]

VARIANT_TYPES_RIGHT = [
    "□ 함축 의미 추론",
    "□ 어휘 추론",
    "□ 빈칸 추론",
    "□ 문장 삽입",
    "□ 순서 추론",
    "□ 연결어 추론",
]


@dataclass
class WorkbookConfig:
    """교안 상단 제목, 머리말·꼬리말 및 출력 옵션."""

    header_title: str = "고등영어,아작 – 2026년 10월 모의고사 – 2학기 2차 내신대비"
    page_header_text: str = ""  # 문서 상단 머리말 영역(비워 두면 효원고 원본처럼 빈 머리말)
    page_footer_text: str = ""  # 문서 하단 꼬리말 텍스트 (쪽 번호와 함께 표시 가능)
    show_page_number_in_footer: bool = True
    include_vocabulary_table: bool = True
    include_vocab_test_table: bool = False
    vocab_rows_per_page: int = 30  # 여백 축소로 페이지당 좌/우 각 30행 = 60단어


def _x(text: str) -> str:
    """XML 안전 이스케이프."""
    return escape(text or "", {'"': "&quot;", "'": "&apos;"})


def _make_p(
    text: str,
    char_pr: int = 0,
    para_pr: int = 0,
    page_break: bool = False,
    pid: int = 0,
) -> str:
    pb = "1" if page_break else "0"
    return (
        f'<hp:p id="{pid}" paraPrIDRef="{para_pr}" styleIDRef="0" '
        f'pageBreak="{pb}" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="{char_pr}"><hp:t>{_x(text)}</hp:t></hp:run>'
        f"</hp:p>"
    )


def _make_multi_run_p(
    runs: Sequence[tuple[str, int]],
    para_pr: int = 0,
    page_break: bool = False,
    pid: int = 0,
) -> str:
    pb = "1" if page_break else "0"
    runs_xml = "".join(
        f'<hp:run charPrIDRef="{cpr}"><hp:t>{_x(txt)}</hp:t></hp:run>' for txt, cpr in runs
    )
    return (
        f'<hp:p id="{pid}" paraPrIDRef="{para_pr}" styleIDRef="0" '
        f'pageBreak="{pb}" columnBreak="0" merged="0">{runs_xml}</hp:p>'
    )


def _make_multiline_ps(
    lines: Sequence[str],
    char_pr: int = 0,
    para_pr: int = 0,
) -> str:
    if not lines:
        return _make_p("", char_pr=char_pr, para_pr=para_pr)
    return "".join(_make_p(line, char_pr=char_pr, para_pr=para_pr) for line in lines)


def _make_cell(
    col_idx: int,
    row_idx: int,
    width: int,
    height: int,
    inner_paragraphs_xml: str,
    border_fill_id: int = 1,
    col_span: int = 1,
    row_span: int = 1,
    vert_align: str = "CENTER",
    margin_lr: int = 200,
    margin_tb: int = 100,
) -> str:
    return (
        f'<hp:tc name="" header="0" hasMargin="1" protect="0" editable="0" dirty="0" '
        f'borderFillIDRef="{border_fill_id}">'
        f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="{vert_align}" '
        f'linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" '
        f'hasTextRef="0" hasNumRef="0">'
        f"{inner_paragraphs_xml}"
        f"</hp:subList>"
        f'<hp:cellAddr colAddr="{col_idx}" rowAddr="{row_idx}"/>'
        f'<hp:cellSpan colSpan="{col_span}" rowSpan="{row_span}"/>'
        f'<hp:cellSz width="{width}" height="{height}"/>'
        f'<hp:cellMargin left="{margin_lr}" right="{margin_lr}" top="{margin_tb}" bottom="{margin_tb}"/>'
        f"</hp:tc>"
    )


def _make_table(
    tbl_id: int,
    rows_xml: Sequence[str],
    row_cnt: int,
    col_cnt: int,
    total_width: int = CONTENT_WIDTH,
    total_height: int = 2000,
    border_fill_id: int = 2,
    page_break: str = "CELL",
) -> str:
    rows_joined = "".join(f"<hp:tr>{r}</hp:tr>" for r in rows_xml)
    return (
        f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="0">'
        f'<hp:tbl id="{tbl_id}" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" '
        f'textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="{page_break}" '
        f'repeatHeader="0" rowCnt="{row_cnt}" colCnt="{col_cnt}" cellSpacing="0" '
        f'borderFillIDRef="{border_fill_id}" noAdjust="0">'
        f'<hp:sz width="{total_width}" widthRelTo="ABSOLUTE" height="{total_height}" heightRelTo="ABSOLUTE" protect="0"/>'
        f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" '
        f'holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="COLUMN" vertAlign="TOP" '
        f'horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
        f'<hp:outMargin left="0" right="0" top="80" bottom="80"/>'
        f'<hp:inMargin left="200" right="200" top="100" bottom="100"/>'
        f"{rows_joined}"
        f"</hp:tbl>"
        f"</hp:run>"
        f"</hp:p>"
    )


def _build_vocabulary_pages(
    passages: Sequence[PassageData],
    config: WorkbookConfig,
    is_test: bool = False,
    tbl_id_start: int = 100,
) -> tuple[List[str], int]:
    """효원고 원본 스타일의 VOCABULARY 2단 어휘 표 페이지들을 생성합니다."""
    flat_items: List[tuple[str, str, str]] = []
    for p in passages:
        for idx, v in enumerate(p.vocabulary, start=1):
            word_label = f"{v.word} ({p.label})" if idx == 1 else v.word
            meaning_label = "" if is_test else v.meaning
            flat_items.append((str(idx), word_label, meaning_label))

    if not flat_items:
        return [], tbl_id_start

    rows_per_page = max(10, config.vocab_rows_per_page)
    items_per_page = rows_per_page * 2
    total_pages = math.ceil(len(flat_items) / items_per_page)

    # 6열 너비 합계 = CONTENT_WIDTH (53858)
    col_w = [3000, 10200, 13729, 3000, 10200, 13729]
    row_h = 1800

    blocks: List[str] = []
    tbl_id = tbl_id_start
    title_prefix = "VOCABULARY TEST" if is_test else "VOCABULARY"

    for page_idx in range(total_pages):
        chunk = flat_items[page_idx * items_per_page : (page_idx + 1) * items_per_page]
        half = math.ceil(len(chunk) / 2)
        left_items = chunk[:half]
        right_items = chunk[half:]
        row_count = max(len(left_items), len(right_items))

        need_break = (page_idx > 0) or is_test
        # 효원고 원본: VOCABULARY - 1 (210 맨발의청춘 R 15pt Bold #999999) + 부제
        blocks.append(
            _make_p(
                f"{title_prefix} - {page_idx + 1}",
                char_pr=1,
                para_pr=0,
                page_break=need_break,
            )
        )
        blocks.append(_make_p(config.header_title, char_pr=3, para_pr=0))

        headers = ["No", "Word", "Meaning", "No", "Word", "Meaning"]
        header_cells = "".join(
            _make_cell(
                col_idx=c,
                row_idx=0,
                width=col_w[c],
                height=1900,
                inner_paragraphs_xml=_make_p(headers[c], char_pr=2, para_pr=1),
                border_fill_id=3,
            )
            for c in range(6)
        )
        rows_xml = [header_cells]

        for r in range(row_count):
            l_no, l_word, l_mean = left_items[r] if r < len(left_items) else ("", "", "")
            r_no, r_word, r_mean = right_items[r] if r < len(right_items) else ("", "", "")
            vals = [l_no, l_word, l_mean, r_no, r_word, r_mean]
            aligns = [1, 0, 0, 1, 0, 0]
            char_prs = [12, 6, 12, 12, 6, 12]
            row_cells = "".join(
                _make_cell(
                    col_idx=c,
                    row_idx=r + 1,
                    width=col_w[c],
                    height=row_h,
                    inner_paragraphs_xml=_make_p(vals[c], char_pr=char_prs[c], para_pr=aligns[c]),
                    border_fill_id=2,
                    margin_lr=180,
                    margin_tb=90,
                )
                for c in range(6)
            )
            rows_xml.append(row_cells)

        blocks.append(
            _make_table(
                tbl_id=tbl_id,
                rows_xml=rows_xml,
                row_cnt=row_count + 1,
                col_cnt=6,
                total_width=CONTENT_WIDTH,
                total_height=1900 + row_count * row_h,
                border_fill_id=2,
            )
        )
        tbl_id += 1

    return blocks, tbl_id


def _build_passage_page(
    passage: PassageData,
    config: WorkbookConfig,
    need_page_break: bool,
    tbl_id_start: int,
) -> tuple[List[str], int]:
    """효원고 원본 HWP의 정확한 색상·폰트·크기·9행 투명 표 구성을 그대로 생성합니다."""
    passage = postprocess_passage(passage)

    blocks: List[str] = []
    tbl_id = tbl_id_start

    # 1. 상단 대제목: LG Smart UI SemiBold 19pt Bold #85BF4C
    blocks.append(
        _make_p(
            config.header_title,
            char_pr=7,
            para_pr=0,
            page_break=need_page_break,
        )
    )
    # 2. 지문 번호(14pt Bold #7F7F7F) + ※ 기존유형(12pt #85BF4C)
    blocks.append(
        _make_multi_run_p(
            [
                (f"{passage.label}번", 8),
                ("      ", 8),
                (f"※ 기존유형 : {passage.question_type}", 10),
            ],
            para_pr=0,
        )
    )

    # 3. 3열 x 9행 통합 투명 표 (합계 = CONTENT_WIDTH 53858)
    c0, c1 = 11800, 10800
    c2 = CONTENT_WIDTH - c0 - c1  # 31258
    c12 = c1 + c2                 # 42058

    en_paragraphs: List[str] = []
    for sent in passage.english_sentences:
        if sent.strip():
            en_paragraphs.append(_make_p(sent.strip(), char_pr=0, para_pr=2))
    if passage.footnotes.strip():
        en_paragraphs.append(_make_p(passage.footnotes.strip(), char_pr=3, para_pr=4))

    ko_joined = " ".join(s.strip() for s in passage.korean_sentences if s.strip())
    vocab_line = "  ".join(f"• {v.word} {v.meaning}" for v in passage.vocabulary)

    rows_xml = [
        # Row 0: 내용 (보라 13pt Bold 가운데) | 한국어 주제 (맑은 고딕 11.5pt)
        (
            _make_cell(
                col_idx=0, row_idx=0, width=c0, height=2300,
                inner_paragraphs_xml=_make_p("내용", char_pr=9, para_pr=1),
                border_fill_id=1, vert_align="CENTER",
            )
            + _make_cell(
                col_idx=1, row_idx=0, width=c12, height=2300,
                inner_paragraphs_xml=_make_p(passage.title_ko, char_pr=0, para_pr=0),
                border_fill_id=1, col_span=2, vert_align="CENTER",
            )
        ),
        # Row 1: 지문 분석 (보라 13pt Bold 가운데) | 영어 한 줄 요약
        (
            _make_cell(
                col_idx=0, row_idx=1, width=c0, height=2300,
                inner_paragraphs_xml=_make_p("지문 분석", char_pr=9, para_pr=1),
                border_fill_id=1, vert_align="CENTER",
            )
            + _make_cell(
                col_idx=1, row_idx=1, width=c12, height=2300,
                inner_paragraphs_xml=_make_p(passage.summary_en.strip(), char_pr=4, para_pr=0),
                border_fill_id=1, col_span=2, vert_align="CENTER",
            )
        ),
        # Row 2: 영어 본문 (맑은 고딕 11.5pt, 넉넉한 필기 행간)
        (
            _make_cell(
                col_idx=0, row_idx=2, width=CONTENT_WIDTH, height=31000,
                inner_paragraphs_xml="".join(en_paragraphs) or _make_p("", char_pr=0, para_pr=2),
                border_fill_id=1, col_span=3, vert_align="TOP",
                margin_lr=200, margin_tb=140,
            )
        ),
        # Row 3: 우리말 해석 라벨
        (
            _make_cell(
                col_idx=0, row_idx=3, width=c0, height=2100,
                inner_paragraphs_xml=_make_p("우리말 해석", char_pr=9, para_pr=1),
                border_fill_id=1, vert_align="CENTER",
            )
            + _make_cell(
                col_idx=1, row_idx=3, width=c12, height=2100,
                inner_paragraphs_xml=_make_p("", char_pr=5, para_pr=0),
                border_fill_id=1, col_span=2, vert_align="CENTER",
            )
        ),
        # Row 4: 우리말 해석 본문 (맑은 고딕 8.0pt — 효원고 원본 동일)
        (
            _make_cell(
                col_idx=0, row_idx=4, width=CONTENT_WIDTH, height=7400,
                inner_paragraphs_xml=_make_p(ko_joined, char_pr=5, para_pr=3),
                border_fill_id=1, col_span=3, vert_align="TOP",
                margin_lr=200, margin_tb=100,
            )
        ),
        # Row 5: 단어 및 숙어 라벨
        (
            _make_cell(
                col_idx=0, row_idx=5, width=c0, height=2100,
                inner_paragraphs_xml=_make_p("단어 및 숙어", char_pr=9, para_pr=1),
                border_fill_id=1, vert_align="CENTER",
            )
            + _make_cell(
                col_idx=1, row_idx=5, width=c12, height=2100,
                inner_paragraphs_xml=_make_p("", char_pr=5, para_pr=0),
                border_fill_id=1, col_span=2, vert_align="CENTER",
            )
        ),
        # Row 6: 단어 및 숙어 본문 (맑은 고딕 8.0pt — 효원고 원본 동일)
        (
            _make_cell(
                col_idx=0, row_idx=6, width=CONTENT_WIDTH, height=5800,
                inner_paragraphs_xml=_make_p(vocab_line, char_pr=5, para_pr=0),
                border_fill_id=1, col_span=3, vert_align="TOP",
                margin_lr=200, margin_tb=100,
            )
        ),
        # Row 7: 변형 적합유형 | (빈칸) | NOTE
        (
            _make_cell(
                col_idx=0, row_idx=7, width=c0, height=2100,
                inner_paragraphs_xml=_make_p("변형 적합유형", char_pr=9, para_pr=1),
                border_fill_id=1, vert_align="CENTER",
            )
            + _make_cell(
                col_idx=1, row_idx=7, width=c1, height=2100,
                inner_paragraphs_xml=_make_p("", char_pr=5, para_pr=0),
                border_fill_id=1, vert_align="CENTER",
            )
            + _make_cell(
                col_idx=2, row_idx=7, width=c2, height=2100,
                inner_paragraphs_xml=_make_p("NOTE", char_pr=9, para_pr=0),
                border_fill_id=1, vert_align="CENTER",
            )
        ),
        # Row 8: 체크박스 12개 (12롯데마트드림Medium 9.0pt) | NOTE 필기 여백
        (
            _make_cell(
                col_idx=0, row_idx=8, width=c0, height=7600,
                inner_paragraphs_xml=_make_multiline_ps(VARIANT_TYPES_LEFT, char_pr=11, para_pr=0),
                border_fill_id=1, vert_align="TOP",
                margin_lr=160, margin_tb=80,
            )
            + _make_cell(
                col_idx=1, row_idx=8, width=c1, height=7600,
                inner_paragraphs_xml=_make_multiline_ps(VARIANT_TYPES_RIGHT, char_pr=11, para_pr=0),
                border_fill_id=1, vert_align="TOP",
                margin_lr=160, margin_tb=80,
            )
            + _make_cell(
                col_idx=2, row_idx=8, width=c2, height=7600,
                inner_paragraphs_xml=_make_p("", char_pr=11, para_pr=0),
                border_fill_id=1, vert_align="TOP",
            )
        ),
    ]

    blocks.append(
        _make_table(
            tbl_id=tbl_id,
            rows_xml=rows_xml,
            row_cnt=9,
            col_cnt=3,
            total_width=CONTENT_WIDTH,
            total_height=62700,
            border_fill_id=1,
        )
    )
    tbl_id += 1

    return blocks, tbl_id


def _build_version_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
        '<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" '
        'tagetApplication="WORDPROCESSOR" major="5" minor="1" micro="1" buildNumber="0" '
        'os="1" xmlVersion="1.5" application="Hancom Office Hangul" appVersion="12, 0, 0, 0"/>'
    )


def _build_container_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
        '<ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container" '
        'xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf">'
        "<ocf:rootfiles>"
        '<ocf:rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/>'
        "</ocf:rootfiles>"
        "</ocf:container>"
    )


def _build_manifest_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
        '<odf:manifest xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"/>'
    )


def _build_content_hpf() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
        '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" version="" unique-identifier="" id="">'
        "<opf:metadata>"
        "<opf:title>내신 영어 지문 분석 교안</opf:title>"
        "<opf:language>ko</opf:language>"
        "</opf:metadata>"
        "<opf:manifest>"
        '<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>'
        '<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>'
        "</opf:manifest>"
        "<opf:spine>"
        '<opf:itemref idref="header" linear="yes"/>'
        '<opf:itemref idref="section0" linear="yes"/>'
        "</opf:spine>"
        "</opf:package>"
    )


def _build_header_xml() -> str:
    # 효원고 원본 HWP의 실제 5개 폰트 등록 (0~4)
    # 0: 맑은 고딕, 1: LG Smart UI SemiBold, 2: 210 맨발의청춘 R, 3: 12롯데마트드림Medium, 4: 함초롬돋움
    font_names = [
        "맑은 고딕",
        "LG Smart UI SemiBold",
        "210 맨발의청춘 R",
        "12롯데마트드림Medium",
        "함초롬돋움",
    ]
    font_langs = ["HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER"]
    fontfaces_xml = []
    for lang in font_langs:
        items = "".join(
            f'<hh:font id="{fid}" face="{fname}" type="TTF" isEmbedded="0"/>'
            for fid, fname in enumerate(font_names)
        )
        fontfaces_xml.append(f'<hh:fontface lang="{lang}" fontCnt="{len(font_names)}">{items}</hh:fontface>')

    def char_pr(
        cid: int,
        height: int,
        color: str,
        font_id: int = 0,
        bold: bool = False,
        underline: bool = False,
        underline_color: str = "#817CC3",
    ) -> str:
        b_tag = "<hh:bold/>" if bold else ""
        u_tag = (
            f'<hh:underline type="BOTTOM" shape="SOLID" color="{underline_color}"/>'
            if underline
            else '<hh:underline type="NONE" shape="SOLID" color="#000000"/>'
        )
        return (
            f'<hh:charPr id="{cid}" height="{height}" textColor="{color}" '
            f'shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="1">'
            f'<hh:fontRef hangul="{font_id}" latin="{font_id}" hanja="{font_id}" japanese="{font_id}" other="{font_id}" symbol="{font_id}" user="{font_id}"/>'
            f'<hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
            f'<hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
            f'<hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
            f'<hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
            f"{b_tag}{u_tag}"
            f"</hh:charPr>"
        )

    def para_pr(pid: int, align: str, line_spacing: int) -> str:
        return (
            f'<hh:paraPr id="{pid}" tabPrIDRef="0" condense="0" fontLineHeight="0" '
            f'snapToGrid="1" suppressLineNumbers="0" checked="0">'
            f'<hh:align horizontal="{align}" vertical="BASELINE"/>'
            f'<hh:heading type="NONE" idRef="0" level="0"/>'
            f'<hh:breakSetting breakLatinWord="KEEP_WORD" breakNonLatinWord="KEEP_WORD" '
            f'widowOrphan="0" keepWithNext="0" keepLines="0" pageBreakBefore="0" lineWrap="BREAK"/>'
            f'<hh:autoSpacing eAsianEng="0" eAsianNum="0"/>'
            f"<hh:margin>"
            f'<hc:intent value="0" unit="HWPUNIT"/>'
            f'<hc:left value="0" unit="HWPUNIT"/>'
            f'<hc:right value="0" unit="HWPUNIT"/>'
            f'<hc:prev value="0" unit="HWPUNIT"/>'
            f'<hc:next value="0" unit="HWPUNIT"/>'
            f"</hh:margin>"
            f'<hh:lineSpacing type="PERCENT" value="{line_spacing}" unit="HWPUNIT"/>'
            f'<hh:border borderFillIDRef="1" offsetLeft="0" offsetRight="0" offsetTop="0" offsetBottom="0" connect="0" ignoreMargin="0"/>'
            f"</hh:paraPr>"
        )

    char_prs = "".join(
        [
            char_pr(0, 1150, "#000000", font_id=0, bold=False),                         # 0: 내용·영어 본문 (맑은 고딕 11.5pt)
            char_pr(1, 1500, "#999999", font_id=2, bold=True),                          # 1: VOCABULARY - 1 (210 맨발의청춘 R 15pt Bold #999999)
            char_pr(2, 950, "#000000", font_id=0, bold=True),                           # 2: VOCABULARY 표 헤더 (맑은 고딕 9.5pt Bold)
            char_pr(3, 850, "#595959", font_id=0, bold=False),                          # 3: 부제/각주 (맑은 고딕 8.5pt)
            char_pr(4, 1050, "#000080", font_id=0, bold=True),                          # 4: 영어 한 줄 요약 (맑은 고딕 10.5pt Bold #000080)
            char_pr(5, 800, "#000000", font_id=0, bold=False),                          # 5: 우리말 해석·단어 및 숙어 (맑은 고딕 8.0pt)
            char_pr(6, 900, "#000000", font_id=0, bold=True),                           # 6: VOCABULARY 영단어 (맑은 고딕 9.0pt Bold)
            char_pr(7, 1900, "#85BF4C", font_id=1, bold=True),                          # 7: 상단 대제목 (LG Smart UI SemiBold 19pt Bold #85BF4C)
            char_pr(8, 1400, "#7F7F7F", font_id=1, bold=True),                          # 8: 지문번호 (LG Smart UI SemiBold 14pt Bold #7F7F7F)
            char_pr(9, 1300, "#817CC3", font_id=2, bold=True, underline=True, underline_color="#817CC3"),  # 9: 섹션 라벨 (210 맨발의청춘 R 13pt Bold #817CC3 밑줄)
            char_pr(10, 1200, "#85BF4C", font_id=1, bold=False),                        # 10: ※ 기존유형 (LG Smart UI SemiBold 12pt #85BF4C)
            char_pr(11, 900, "#000000", font_id=3, bold=False),                         # 11: 변형 적합유형 체크박스 (12롯데마트드림Medium 9.0pt)
            char_pr(12, 900, "#000000", font_id=0, bold=False),                         # 12: VOCABULARY 번호/뜻 (맑은 고딕 9.0pt)
            char_pr(13, 900, "#595959", font_id=4, bold=False),                         # 13: 머리말·꼬리말 (함초롬돋움 9.0pt)
        ]
    )

    para_prs = "".join(
        [
            para_pr(0, "LEFT", 140),
            para_pr(1, "CENTER", 135),
            para_pr(2, "LEFT", 185),      # 영어 본문 (필기 여백)
            para_pr(3, "JUSTIFY", 145),   # 우리말 해석
            para_pr(4, "RIGHT", 135),     # 각주 우측 정렬
        ]
    )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
        f'<hh:head xmlns:hh="{NS_HH}" xmlns:hc="{NS_HC}" version="1.4" secCnt="1">'
        '<hh:beginNum page="1" footnote="1" endnote="1" pic="1" tbl="1" equation="1"/>'
        "<hh:refList>"
        f'<hh:fontfaces itemCnt="{len(font_langs)}">{"".join(fontfaces_xml)}</hh:fontfaces>'
        '<hh:borderFills itemCnt="3">'
        '<hh:borderFill id="1" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
        '<hh:slash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:leftBorder type="NONE" width="0.1 mm" color="#000000"/>'
        '<hh:rightBorder type="NONE" width="0.1 mm" color="#000000"/>'
        '<hh:topBorder type="NONE" width="0.1 mm" color="#000000"/>'
        '<hh:bottomBorder type="NONE" width="0.1 mm" color="#000000"/>'
        '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>'
        "</hh:borderFill>"
        '<hh:borderFill id="2" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
        '<hh:slash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:leftBorder type="SOLID" width="0.12 mm" color="#A6B1C2"/>'
        '<hh:rightBorder type="SOLID" width="0.12 mm" color="#A6B1C2"/>'
        '<hh:topBorder type="SOLID" width="0.12 mm" color="#A6B1C2"/>'
        '<hh:bottomBorder type="SOLID" width="0.12 mm" color="#A6B1C2"/>'
        '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>'
        "</hh:borderFill>"
        '<hh:borderFill id="3" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
        '<hh:slash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:leftBorder type="SOLID" width="0.12 mm" color="#8FA3BF"/>'
        '<hh:rightBorder type="SOLID" width="0.12 mm" color="#8FA3BF"/>'
        '<hh:topBorder type="SOLID" width="0.12 mm" color="#8FA3BF"/>'
        '<hh:bottomBorder type="SOLID" width="0.12 mm" color="#8FA3BF"/>'
        '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>'
        "<hc:fillBrush>"
        '<hc:winBrush faceColor="#EEF3F8" hatchColor="#999999" alpha="0"/>'
        "</hc:fillBrush>"
        "</hh:borderFill>"
        "</hh:borderFills>"
        f'<hh:charProperties itemCnt="14">{char_prs}</hh:charProperties>'
        '<hh:tabProperties itemCnt="1">'
        '<hh:tabPr id="0" autoTabLeft="0" autoTabRight="0"/>'
        "</hh:tabProperties>"
        f'<hh:paraProperties itemCnt="5">{para_prs}</hh:paraProperties>'
        '<hh:styles itemCnt="1">'
        '<hh:style id="0" type="PARA" name="바탕글" engName="Normal" paraPrIDRef="0" charPrIDRef="0" nextStyleIDRef="0" langID="1042" lockForm="0"/>'
        "</hh:styles>"
        "</hh:refList>"
        "</hh:head>"
    )


def _build_header_footer_ctrls(config: WorkbookConfig) -> str:
    """OWPML 표준 머리말(header) 및 꼬리말(footer + 자동 쪽 번호) 컨트롤을 생성합니다."""
    header_ctrl = (
        '<hp:ctrl>'
        '<hp:header id="1" applyPageType="BOTH">'
        '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="TOP" '
        'linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
        f'{_make_p(config.page_header_text, char_pr=13, para_pr=0)}'
        '</hp:subList>'
        '</hp:header>'
        '</hp:ctrl>'
    )

    if config.show_page_number_in_footer:
        prefix = f"{_x(config.page_footer_text)}   - " if config.page_footer_text.strip() else "- "
        footer_inner = (
            '<hp:p id="0" paraPrIDRef="1" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="13"><hp:t>{prefix}</hp:t></hp:run>'
            '<hp:run charPrIDRef="13"><hp:ctrl>'
            '<hp:autoNum num="1" numType="PAGE">'
            '<hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar="" supscript="0"/>'
            '</hp:autoNum>'
            '</hp:ctrl></hp:run>'
            '<hp:run charPrIDRef="13"><hp:t> -</hp:t></hp:run>'
            '</hp:p>'
        )
    else:
        footer_inner = _make_p(config.page_footer_text, char_pr=13, para_pr=1)

    footer_ctrl = (
        '<hp:ctrl>'
        '<hp:footer id="2" applyPageType="BOTH">'
        '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="BOTTOM" '
        'linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
        f'{footer_inner}'
        '</hp:subList>'
        '</hp:footer>'
        '</hp:ctrl>'
    )
    return header_ctrl + footer_ctrl


def _build_section0_xml(passages: Sequence[PassageData], config: WorkbookConfig) -> str:
    hf_ctrls = _build_header_footer_ctrls(config)
    sec_pr = (
        '<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        '<hp:run charPrIDRef="0">'
        '<hp:secPr id="" textDirection="HORIZONTAL" spaceColumns="1134" tabStop="8000" '
        'outlineShapeIDRef="1" memoShapeIDRef="0" textVerticalWidthHead="0" masterPageCnt="0">'
        '<hp:grid lineGrid="0" charGrid="0" wonggojiFormat="0"/>'
        '<hp:startNum pageStartsOn="BOTH" page="1" pic="1" tbl="1" equation="1"/>'
        '<hp:visibility hideFirstHeader="0" hideFirstFooter="0" hideFirstMasterPage="0" '
        'border="SHOW_ALL" fill="SHOW_ALL" hideFirstPageNum="0" hideFirstEmptyLine="0" showLineNumber="0"/>'
        f'<hp:pagePr landscape="WIDELY" width="{PAGE_WIDTH}" height="{PAGE_HEIGHT}" gutterType="LEFT_ONLY">'
        f'<hp:margin header="{MARGIN_HEADER}" footer="{MARGIN_FOOTER}" gutter="0" '
        f'left="{MARGIN_LR}" right="{MARGIN_LR}" top="{MARGIN_TB}" bottom="{MARGIN_TB}"/>'
        "</hp:pagePr>"
        '<hp:footNotePr><hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar=")" supscript="0"/></hp:footNotePr>'
        '<hp:endNotePr><hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar=")" supscript="0"/></hp:endNotePr>'
        "</hp:secPr>"
        '<hp:ctrl><hp:colPr id="" type="NEWSPAPER" layout="LEFT" colCount="1" sameSz="1" sameGap="0"/></hp:ctrl>'
        f"{hf_ctrls}"
        "</hp:run>"
        "</hp:p>"
    )

    body_blocks: List[str] = [sec_pr]
    tbl_id = 100
    has_preceding_content = False

    if config.include_vocabulary_table:
        vocab_blocks, tbl_id = _build_vocabulary_pages(
            passages, config, is_test=False, tbl_id_start=tbl_id
        )
        if vocab_blocks:
            body_blocks.extend(vocab_blocks)
            has_preceding_content = True

    if config.include_vocab_test_table:
        test_blocks, tbl_id = _build_vocabulary_pages(
            passages, config, is_test=True, tbl_id_start=tbl_id
        )
        if test_blocks:
            body_blocks.extend(test_blocks)
            has_preceding_content = True

    for idx, passage in enumerate(passages):
        need_break = has_preceding_content or (idx > 0)
        p_blocks, tbl_id = _build_passage_page(
            passage, config, need_page_break=need_break, tbl_id_start=tbl_id
        )
        body_blocks.extend(p_blocks)

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
        f'<hs:sec xmlns:hs="{NS_HS}" xmlns:hp="{NS_HP}" xmlns:hc="{NS_HC}">'
        f'{"".join(body_blocks)}'
        "</hs:sec>"
    )


def build_hwpx_bytes(
    passages: Sequence[PassageData],
    config: WorkbookConfig | None = None,
) -> bytes:
    """구조화된 지문 리스트를 효원고 원본 스타일의 표준 .hwpx 바이너리(bytes)로 생성합니다."""
    if not passages:
        raise ValueError("생성할 지문 데이터가 없습니다.")

    cfg = config or WorkbookConfig()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("version.xml", _build_version_xml())
        zf.writestr("META-INF/container.xml", _build_container_xml())
        zf.writestr("META-INF/manifest.xml", _build_manifest_xml())
        zf.writestr("Contents/content.hpf", _build_content_hpf())
        zf.writestr("Contents/header.xml", _build_header_xml())
        zf.writestr("Contents/section0.xml", _build_section0_xml(passages, cfg))

    return buf.getvalue()
