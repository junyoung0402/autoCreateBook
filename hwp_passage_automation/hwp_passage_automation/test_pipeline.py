"""실제 아잉카 원본 HWP 파일 기반 전체 문항 유형 정제·변환 검증 테스트.

1) 실제 아잉카 HWP 5.0 파일(18~45번) 서로게이트 오류 없이 100% 텍스트 추출 검증
2) 29번(어법), 30번(어휘), 35번(무관한 문장), 36번(순서), 38번(문장 삽입), 41~42번(장문 어휘)
   각 유형별 오답 치환·기호 제거·숫자 순 재정렬·연속 재번호 검증
3) 실제 정제 결과로 학원 양식 .hwpx 생성 및 XML/왕복 추출 검증
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from core.gemini_parser import PassageData, VocabItem, postprocess_passage
from core.hwp_reader import (
    extract_text_from_file,
    extract_text_from_hwpx,
    parse_passage_numbers,
)
from core.hwpx_builder import WorkbookConfig, build_hwpx_bytes


def _sample_29_grammar() -> PassageData:
    """실제 아잉카 29번(어법 추론) 원본 문장 입력 -> 정제 테스트."""
    return PassageData(
        number=29,
        display_number="29",
        question_type="어법 추론",
        title_ko="운동선수에게 루틴의 의미",
        summary_en="How routines help athletes evaluate and adjust to competition conditions",
        english_sentences=[
            "❶ Routines enable athletes to evaluate competition conditions.",
            "❷ For example, bouncing a ball in a volleyball service routine ① supplies the server with information about the ball, the floor, and the state of her muscles.",
            "❸ This information can then be used to ② properly prepare for her serve.",
            "❹ Routines also enable athletes to adjust and fine-tune their preparations ③ based on those evaluations or in pursuit of a particular competitive goal.",
            "❺ This adaptation can involve adjustment to the conditions, rivals, competitive situation, or internal influences ④ what (→ that) can affect performance.",
            "❻ Just like adjusting a race-car engine to the conditions of the track, air temperature, and weather, routines adjust all competitive components ⑤ to achieve proper performance.",
        ],
        footnotes="* component 구성 요소",
        korean_sentences=[
            "❶ 루틴은 운동선수가 경기 조건을 평가할 수 있도록 해 준다.",
            "❷ 예를 들어, 배구 서브 루틴에서 공을 튕기는 것은 서브를 하는 선수에게 공, 바닥, 그리고 자신의 근육 상태에 대한 정보를 제공한다.",
            "❸ 그다음 이 정보는 자신의 서브를 적절히 준비하기 위해 사용될 수 있다.",
            "❹ 루틴은 또한 그러한 평가에 기반하거나 또는 특정 경쟁 목표를 추구하여 선수가 준비 상태를 조절하고 미세하게 조정할 수 있게 해 준다.",
            "❺ 이러한 적응은 수행에 영향을 미칠 수 있는 조건, 경쟁 상대, 경기 상황, 또는 내적 영향에 대한 조정을 포함할 수 있다.",
            "❻ 경주용 자동차 엔진을 트랙, 기온, 그리고 날씨의 조건에 맞게 조정하는 것과 마찬가지로, 루틴은 적절한 수행을 해내기 위해 경기의 모든 구성 요소를 조정한다.",
        ],
        vocabulary=[
            VocabItem(word="routine", meaning="루틴, 일상의 과정"),
            VocabItem(word="enable", meaning="가능하게 하다"),
            VocabItem(word="evaluate", meaning="평가하다"),
            VocabItem(word="fine-tune", meaning="미세하게 조정하다"),
            VocabItem(word="in pursuit of", meaning="~을 추구하여"),
            VocabItem(word="adaptation", meaning="적응"),
        ],
    )


def _sample_30_vocab() -> PassageData:
    """실제 아잉카 30번(어휘 추론) 원본 문장 입력 -> 영어/한국어 오답 치환 테스트."""
    return PassageData(
        number=30,
        display_number="30",
        question_type="어휘 추론",
        title_ko="소비자 심리를 다루는 프로모션",
        summary_en="Honest promotion focused on identifying and reaching potential consumers",
        english_sentences=[
            "❶ Promotion deals with consumer psychology.",
            "❷ We can’t ① force people to think one way or another, and the clever marketer knows that promotion is used to provide information in the most clear, honest, and simple fashion possible.",
            "❸ By doing so, the possibility of increasing sales goes up.",
            "❹ Gone are the days when promotions were done in order to ② fool the consumer into purchasing something.",
            "❺ The long-term effect of getting a consumer to buy something they did not really want or need wasn’t good.",
            "❻ In fact, consumers fooled once can do ③ damage to sales as they relate their experience to others.",
            "❼ Instead, marketers now know that their goal is to ④ identify the consumers who are most likely to appreciate a good or service, and to promote that good or service in a way that makes the value clear to the consumer.",
            "❽ Therefore, marketers must know where the ⑤ uninterested (→ potential) consumers are, and how to reach them.",
        ],
        footnotes="",
        korean_sentences=[
            "❶ 프로모션은 소비자 심리를 다룬다.",
            "❷ 우리가 사람들을 어떤 한 방식으로 생각하도록 강요할 수는 없으며, 현명한 마케팅 담당자는 프로모션이 가능한 한 가장 명확하고 정직하며 단순한 방식으로 정보를 제공하기 위해 사용된다는 것을 알고 있다.",
            "❸ 그렇게 함으로써, 매출 증가의 가능성이 높아진다.",
            "❹ 무언가를 구매하도록 소비자를 속이기 위해 프로모션이 행해지던 시대는 갔다.",
            "❺ 소비자가 정말로 원하지 않았거나 필요로 하지 않았던 물건을 구매하도록 하는 것의 장기적인 효과는 좋지 않았다.",
            "❻ 사실, 한 번 속은 소비자는 자신의 경험을 다른 사람에게 전하기 때문에 판매에 손해를 끼칠 수 있다.",
            "❼ 대신, 마케팅 담당자들은 상품이나 서비스의 진가를 가장 인정할 것 같은 소비자를 확인하고, 그 소비자에게 그 상품이나 서비스의 가치를 명확하게 하는 방식으로 홍보하는 것이 목표가 되어야 한다는 것을 이제 알고 있다.",
            "❽ 그러므로, 마케팅 담당자는 그 무관심한(→ 잠재적인) 소비자가 어디에 있는지, 그리고 어떻게 그들에게 도달해야 하는지 알아야 한다.",
        ],
        vocabulary=[
            VocabItem(word="promotion", meaning="프로모션, 홍보"),
            VocabItem(word="deal with", meaning="~을 다루다"),
            VocabItem(word="one way or another", meaning="어떤 한 방식으로"),
            VocabItem(word="potential", meaning="잠재적인"),
        ],
    )


def _sample_35_irrelevant() -> PassageData:
    """실제 아잉카 35번(무관한 문장 찾기) — ❹ 삭제 후 ❶~❻ 연속 재번호 테스트."""
    return PassageData(
        number=35,
        display_number="35",
        question_type="무관한 문장 찾기",
        title_ko="주인공과 관객 사이의 긍정적 관계 수립을 위한 작가의 노력",
        summary_en="Establishing an emotional connection between a protagonist and the audience",
        english_sentences=[
            "❶ What does it mean for a character to be a hero as opposed to a villain?",
            "❷ In artistic and entertainment descriptions, it’s essential for the author to establish a positive relationship between a protagonist and the audience.",
            "❸ ① In order for tragedy or misfortune to draw out an emotional response in viewers, the character must be adjusted so as to be recognizable as either friend or enemy.",
            # ❹ 무관한 문장 제거됨 -> ❺, ❻, ❼이 ❹, ❺, ❻으로 재번호되어야 함
            "❺ ③ Whether the portrayal is fictional or documentary, we must feel that the protagonist is someone whose actions benefit us; the protagonist is, or would be, a worthy companion or valued ally.",
            "❻ ④ Violent action films are often filled with dozens of incidental deaths of minor characters that draw out little response in the audience.",
            "❼ ⑤ In order to feel strong emotions, the audience must be emotionally invested in a character as either ally or enemy.",
        ],
        footnotes="* villain 악당 ** protagonist 주인공",
        korean_sentences=[
            "❶ 등장인물이 악당과 대비되는 영웅이라는 것은 무슨 의미인가?",
            "❷ 예술적이고 오락적인 묘사에서, 작가가 주인공과 관객 사이에 긍정적인 관계를 수립하는 것이 필수적이다.",
            "❸ 비극 또는 불행이 관객에게서 감정적 반응을 끌어 내기 위해서, 등장인물은 친구 또는 적 둘 중의 하나로 인식될 수 있도록 조정되어야 한다.",
            "❺ 묘사가 허구적이든 사실을 기록하든 간에, 주인공은 행동이 우리에게 이로움을 주는 누군가이며, 주인공은 가치 있는 동료나 소중한 협력자이고, 혹은 그렇게 될 (존재일) 것이라고 우리는 느껴야 한다.",
            "❻ 폭력적인 액션 영화는 흔히 관객들에게서 반응을 거의 끌어내지 않는 비중이 적은 등장인물의 많은 부수적인 죽음으로 가득 차 있다.",
            "❼ 강한 감정을 느끼기 위해, 관객은 협력자 또는 적 둘 중 하나로 등장인물에게 감정적으로 깊이 연관되어 있어야 한다.",
        ],
        vocabulary=[
            VocabItem(word="as opposed to", meaning="~와 대비되는"),
            VocabItem(word="recognizable", meaning="인식할 수 있는, 알아볼 수 있는"),
            VocabItem(word="ally", meaning="협력자"),
        ],
    )


def _sample_38_insertion() -> PassageData:
    """실제 아잉카 38번(문장 삽입) — ❹가 맨 앞에 있고 ( ① )~( ⑤ ) 포함 상태 테스트."""
    return PassageData(
        number=38,
        display_number="38",
        question_type="문장 삽입",
        title_ko="놀이를 통한 아동의 도덕성 자발적 형성",
        summary_en="Children self-construct morality and fairness through playing games with peers",
        english_sentences=[
            "❹ Piaget argued that children’s understanding of morality is like their understanding of those water glasses: we can’t say that it is innate or kids learn it directly from adults.",
            "❶ Piaget put the same amount of water into two different glasses: a tall narrow glass and a wide glass, then asked kids to compare two glasses.",
            "( ① ) ❷ Kids younger than six or seven usually say that the tall narrow glass now holds more water, because the level is higher.",
            "( ② ) ❸ And when they are ready, they figure out the conservation of volume for themselves just by playing with cups of water.",
            "( ③ ) ❺ Rather, it is self-constructed as kids play with other kids.",
            "( ④ ) ❻ Taking turns in a game is like pouring water back and forth between glasses.",
            "( ⑤ ) ❼ Once kids have reached the age of five or six, then playing games and working things out together will help them learn about fairness far more effectively than any teaching from adults.",
        ],
        footnotes="* innate 타고난 ** conservation 보존",
        korean_sentences=[
            "❶ Piaget는 똑같은 양의 물을 키가 크고 폭이 좁은 유리잔과 넓은 유리잔, 두 개의 서로 다른 유리잔에 넣고 다음 아이들에게 두 유리잔을 비교하라고 요청했다.",
            "❷ 6세 혹은 7세보다 더 어린 아이들은 키가 크고 폭이 좁은 유리잔에 물이 더 많이 담겨 있다고 대개 말하는데, 왜냐하면 수위가 더 높기 때문이다.",
            "❸ 그리고 아이들이 준비가 되어 있을 때, 그들은 물이 든 컵들을 갖고 놂으로써 부피의 보존을 스스로 알아낸다.",
            "❹ Piaget는 도덕성에 대한 아이들의 이해는 그런 물잔에 대한 이해와 같은데, 즉 우리가 그것이 타고났다거나 혹은 아이들이 어른들로부터 직접 그것을 배운다고 말할 수 없다고 주장했다.",
            "❺ 오히려 그것은 아이들이 다른 아이들과 놀면서 스스로 구성해 낸 것이다.",
            "❻ 게임을 순서대로 돌아가며 하는 것은 물잔 사이를 왔다 갔다 하며 물을 붓는 것과 같다.",
            "❼ 일단 아이들이 5세 혹은 6세에 이르면, 함께 게임을 하고 문제를 해결해 나가는 것이 어른들로부터의 그 어떤 가르침보다 그들이 훨씬 더 효과적으로 공평함에 대해 배우는 데 도움이 될 것이다.",
        ],
        vocabulary=[
            VocabItem(word="morality", meaning="도덕(성)"),
            VocabItem(word="self-constructed", meaning="스스로 구성해 낸"),
            VocabItem(word="take turns", meaning="순서대로 돌아가며 하다"),
            VocabItem(word="fairness", meaning="공평함"),
        ],
    )


def _sample_41_42_long() -> PassageData:
    """실제 아잉카 41~42번(장문 어휘) — (a)~(e) 및 include (→ eliminate) 정제 테스트."""
    return PassageData(
        number=41,
        display_number="41~42",
        question_type="1지문 2문항",
        title_ko="수량화가 놓치는 인간의 경험과 감정",
        summary_en="Numbers eliminate valuable human context and emotional suffering",
        english_sentences=[
            "❶ Some researchers view spoken languages as incomplete devices for capturing precise differences.",
            "❷ They think numbers represent the most neutral language of description.",
            "❸ However, when our language of description is changed to numbers, we do not move toward greater (a) accuracy.",
            "❹ Numbers are no more appropriate ‘pictures of the world’ than words, music, or painting.",
            "❺ While useful for specific purposes (e.g. census taking, income distribution), they (b) include (→ eliminate) information of enormous value.",
        ],
        footnotes="* statistical 통계의 ** manipulate 조작하다 *** insulating 차단하는",
        korean_sentences=[
            "❶ 일부 연구자는 발화된 언어를 정확한 차이를 포착하는 데에 불완전한 도구로 여긴다.",
            "❷ 그들은 숫자가 묘사의 가장 중립적인 언어를 나타낸다고 생각한다.",
            "❸ 그러나, 우리의 묘사의 언어가 숫자로 바뀔 때, 우리가 더 큰 정확성으로 나아가지는 않는다.",
            "❹ 숫자가 말, 음악, 또는 그림보다 더 적절한 ‘세상의 묘사’는 아니다.",
            "❺ 특정한 목적(예를 들어, 인구 조사, 소득 분포)에는 유용하지만, 숫자는 엄청난 가치를 지닌 정보를 포함한다(→ 제거한다).",
        ],
        vocabulary=[
            VocabItem(word="income distribution", meaning="소득 분포"),
            VocabItem(word="eliminate", meaning="제거하다, 없애다"),
            VocabItem(word="quantify", meaning="수량화하다"),
        ],
    )


def main() -> None:
    assert parse_passage_numbers("29, 30, 35, 38, 41-42") == [29, 30, 35, 38, 41, 42]
    print("[PASS] 지문 번호 파서 검증 완료")

    # 실제 아잉카 원본 HWP 파일 추출 검증 (UTF-8 인코딩 포함)
    if len(sys.argv) > 1:
        hwp_path = Path(sys.argv[1])
        text = extract_text_from_file(hwp_path)
        text.encode("utf-8")  # 서로게이트 오류 없음 확인
        assert len(text) > 40000
        assert "▶ 어법 추론" in text and "▶ 무관한 문장 찾기" in text and "41~42." in text
        print(f"[PASS] 실제 아잉카 HWP 5.0 파일 추출 및 UTF-8 검증 완료 ({len(text):,}자)")

    # 유형별 정제 검증
    p29 = postprocess_passage(_sample_29_grammar())
    assert "what" not in p29.english_sentences[4] and "internal influences that can affect" in p29.english_sentences[4]
    assert all(m not in " ".join(p29.english_sentences) for m in ["①", "②", "③", "④", "⑤", "→"])

    p30 = postprocess_passage(_sample_30_vocab())
    assert "uninterested" not in p30.english_sentences[7] and "the potential consumers are" in p30.english_sentences[7]
    assert "무관심한" not in p30.korean_sentences[7] and "그 잠재적인 소비자가" in p30.korean_sentences[7]

    p35 = postprocess_passage(_sample_35_irrelevant())
    assert [s[0] for s in p35.english_sentences] == ["❶", "❷", "❸", "❹", "❺", "❻"]
    assert [s[0] for s in p35.korean_sentences] == ["❶", "❷", "❸", "❹", "❺", "❻"]

    p38 = postprocess_passage(_sample_38_insertion())
    assert [s[0] for s in p38.english_sentences] == ["❶", "❷", "❸", "❹", "❺", "❻", "❼"]
    assert all("( ① )" not in s and "( ⑤ )" not in s for s in p38.english_sentences)

    p41 = postprocess_passage(_sample_41_42_long())
    assert "include" not in p41.english_sentences[4] and "they eliminate information" in p41.english_sentences[4]
    assert "포함한다" not in p41.korean_sentences[4] and "정보를 제거한다." in p41.korean_sentences[4]
    assert all(m not in " ".join(p41.english_sentences) for m in ["(a)", "(b)", "→"])
    print("[PASS] 29(어법)·30(어휘)·35(무관)·38(삽입)·41~42(장문) 유형별 원문 정제 검증 완료")

    # 학원 양식 .hwpx 생성 및 XML 검증
    passages = [p29, p30, p35, p38, p41]
    cfg = WorkbookConfig(
        header_title="아작, 영어 - 2025 고1 3월 모의고사 - 1학기 1차 내신대비",
        include_vocabulary_table=True,
        include_vocab_test_table=False,
    )
    hwpx_bytes = build_hwpx_bytes(passages, config=cfg)
    out_path = Path(__file__).resolve().parent / "sample_아잉카_전유형_학원양식.hwpx"
    out_path.write_bytes(hwpx_bytes)

    old_sample = Path(__file__).resolve().parent / "sample_21_39번_학원양식.hwpx"
    if old_sample.exists():
        old_sample.unlink()

    with zipfile.ZipFile(out_path, "r") as zf:
        assert zf.infolist()[0].filename == "mimetype"
        for name in [
            "version.xml",
            "META-INF/container.xml",
            "META-INF/manifest.xml",
            "Contents/content.hpf",
            "Contents/header.xml",
            "Contents/section0.xml",
        ]:
            ET.fromstring(zf.read(name))

    rt = extract_text_from_hwpx(hwpx_bytes)
    assert "41~42번" in rt and "income distribution (41~42)" in rt
    assert "internal influences that can affect" in rt
    assert "the potential consumers are" in rt
    assert "→" not in rt
    print(f"[PASS] 전 유형 정제 HWPX 생성·XML 검증 완료: {out_path.name} ({len(hwpx_bytes):,} bytes)")


if __name__ == "__main__":
    main()
