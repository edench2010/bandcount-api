"""밴드 댓글에서 성경 장 수·기도 시간(분)을 뽑는 시험 파서. 표준 라이브러리만 씀."""
import re

NATIVE = {"한": 1, "하나": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "네": 4, "넷": 4, "다섯": 5,
          "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10, "스무": 20, "스물": 20}
SINO = {c: i for i, c in enumerate("영일이삼사오육칠팔구")}
UNIT = r"(?=\s*(?:장|편|시간|분|방))"  # 방 = 한방기도방의 기도 단위(1방 = 1시간)
ONES = "한|하나|두|둘|세|셋|네|넷|다섯|여섯|일곱|여덟|아홉"
NATIVE_RE = re.compile(rf"(열|스무|스물)?\s?({ONES})?{UNIT}")
SINO_RE = re.compile(r"([일이삼사오육칠팔구]?)십([일이삼사오육칠팔구]?)" + UNIT)  # '이 시간'(this time) 오인 막으려고 십 들어간 것만

BOOKS = ("창세기 출애굽기 레위기 민수기 신명기 여호수아 사사기 룻기 사무엘상 사무엘하 열왕기상 열왕기하 역대상 역대하 "
         "에스라 느헤미야 에스더 욥기 시편 잠언 전도서 아가 이사야 예레미야 예레미야애가 에스겔 다니엘 호세아 요엘 아모스 "
         "오바댜 요나 미가 나훔 하박국 스바냐 학개 스가랴 말라기 마태복음 마가복음 누가복음 요한복음 사도행전 로마서 "
         "고린도전서 고린도후서 갈라디아서 에베소서 빌립보서 골로새서 데살로니가전서 데살로니가후서 디모데전서 디모데후서 "
         "디도서 빌레몬서 히브리서 야고보서 베드로전서 베드로후서 요한일서 요한이서 요한삼서 유다서 요한계시록 "
         "창 출 레 민 신 수 삿 룻 삼상 삼하 왕상 왕하 대상 대하 스 느 에 욥 시 잠 전 아 사 렘 애 겔 단 호 욜 암 옵 욘 미 나 합 "
         "습 학 슥 말 마 막 눅 요 행 롬 고전 고후 갈 엡 빌 골 살전 살후 딤전 딤후 딛 몬 히 약 벧전 벧후 요일 요이 요삼 유 계").split()
BOOK = "|".join(sorted(BOOKS, key=len, reverse=True))
# 책이름 + 장(범위). 뒤에 ':'가 오면 절 인용(롬 8:28)이라 뺀다.
REF_RE = re.compile(rf"(?:{BOOK})\s?(\d+)\s?(?:장|편)?\s?(?:[-~]\s?(\d+)\s?(?:장|편)?)?(?![\d:])")
COUNT_RE = re.compile(rf"(?<![\d가-힣])(?<!(?:{'|'.join(b for b in BOOKS if len(b) == 1)}) )(\d+)\s?(?:장|편)")


def to_digits(text):
    def native(m):
        n = NATIVE.get(m.group(1) or "", 0) + NATIVE.get(m.group(2) or "", 0)
        return str(n) if n else m.group(0)
    text = NATIVE_RE.sub(native, text)
    return SINO_RE.sub(lambda m: str(SINO.get(m.group(1), 1) * 10 + SINO.get(m.group(2), 0)), text)


def has_number(text):
    return bool(re.search(r"\d", to_digits(text)))


def chapters(text):
    """장 수. 못 읽으면 None → 목사님 확인 목록으로."""
    text = to_digits(text)
    refs = list(REF_RE.finditer(text))
    ref_spans = [m.span() for m in refs]
    counts = [int(m.group(1)) for m in COUNT_RE.finditer(text)
              if not any(a <= m.start() < b for a, b in ref_spans)]
    if counts:  # "3장"처럼 장 수를 직접 쓴 게 우선
        return counts[0] if len(counts) == 1 else None
    if refs:
        return sum(int(m.group(2)) - int(m.group(1)) + 1 if m.group(2) else 1 for m in refs)
    return None


TYPO = {**{k: v for k, v in NATIVE.items() if len(k) > 1 or k in "한두세네열"}, "핸": 1, "헌": 1, "핫": 1, "투": 2, "새": 3, "셰": 3}
TYPO_RE = re.compile(rf"({'|'.join(sorted(TYPO, key=len, reverse=True))})\s?[가-힣]\s?아[멘엔]")


def prayer_minutes(text):
    """기도 시간(분). 숫자가 둘 이상 섞여 애매하면 None."""
    text = to_digits(text)
    hits = re.findall(r"(\d+(?:\.\d+)?)\s?(?:시간|방)(\s?반)?(?:\s?(\d+)\s?분)?|(\d+)\s?분", text)
    if not hits:  # 오타: 「한빙아멘」「핸방아멘」 → 숫자말 + 아무 한 글자 + 아멘
        m = TYPO_RE.search(text)
        return TYPO[m[1]] * 60 if m else None
    if len(hits) != 1:
        return None
    h, half, m1, m2 = hits[0]
    return round(float(h or 0) * 60) + (30 if half else 0) + int(m1 or m2 or 0)


if __name__ == "__main__":
    bible = [
        ("3장 창세기 1-3장", 3), ("오늘 창 4~6 읽었습니다 할렐루야", 3), ("마태복음 5장", 1),
        ("세 장 읽었어요 (출 1-3)", 3), ("열두장 완료!", 12), ("창세기 5장~7장, 시편 23편", 4),
        ("2장 롬 8-9 은혜받은 구절: 롬 8:28 모든 것이 합력하여", 2), ("오늘은 못 읽었어요 ㅠ", None),
        ("요 3:16 말씀에 은혜받았습니다", None), ("10장! 레 1~10", 10), ("다섯 장 읽음", 5),
    ]
    prayer = [
        ("1시간", 60), ("한시간 반 기도했습니다", 90), ("두 시간 기도했습니다 아멘", 120), ("30분", 30),
        ("1시간 30분", 90), ("삼십분 기도", 30), ("1.5시간", 90), ("이 시간 주님께 감사드립니다 1시간", 60),
        ("오늘 2시간, 어제 1시간 빠뜨렸어요", None), ("기도했습니다", None),
        ("한빙아멘", 60), ("한빙아엔", 60), ("핫방아멘", 60), ("핸빙 아멘", 60), ("두뱡아멘", 120), ("기도했습니다 아멘", None), ("네 아멘", None),
        ("한방 아멘", 60), ("두방 아멘", 120), ("네방아멘", 240), ("다섯방아멘", 300), ("3방", 180),
    ]
    ok = 0
    for fn, cases in ((chapters, bible), (prayer_minutes, prayer)):
        for text, want in cases:
            got = fn(text)
            ok += got == want
            print("OK  " if got == want else "FAIL", f"{fn.__name__}({text!r}) = {got}  (기대 {want})")
    total = len(bible) + len(prayer)
    print(f"\n{ok}/{total} 통과")
    assert ok == total
