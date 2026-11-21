"""댓글 → 사람별 · 날짜별 참여 기록. 밴드 접속은 하지 않는다(접속은 band_api.py).
comments = [{name, text, time(한국 시각 datetime), post_day(그 댓글이 달린 글의 날짜)}]"""
import datetime as dt
import os
import pathlib
import re
import urllib.request

from parse import BOOK, chapters, has_number, prayer_minutes

HERE = pathlib.Path(__file__).resolve().parent

TITLE = re.compile(r"(?m)^\s*(\d{4})\.(\d{1,2})\.(\d{1,2})\.[^(\n]*\(([^)\n]+)\)")  # 통독방 제목 「2026.10.28.수(눅10~11)」 · 줄 머리에서만(공지 글의 「예) …」는 아님)
DAILY = re.compile(r"(?m)^\s*\d+일(?:째)?\s*\(\d{4}\.|" + TITLE.pattern[4:])  # 「411일째 (…)」 「380일(…)」도  # 매일 글 제목(한방 · 통독). 공지 · 통독표 같은 다른 글은 안 센다


# 날짜 표시: 「10/24」 「9월30일」 「29일」 「어제(27)」 「어제」
DATE_MARK = re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})|(?:(\d{1,2})\s*월\s*)?(\d{1,2})\s*일|어제\s*(?:\(\s*(\d{1,2})\s*일?\s*\))?")


def resolve(base, month, dayn):
    """댓글에 적힌 월·일 → 날짜. 기준일보다 뒤면 지난해(월을 쓴 경우) 또는 지난달(일만 쓴 경우)."""
    try:
        if month:
            d = dt.date(base.year, month, dayn)
            return d if d <= base else d.replace(year=base.year - 1)
        if dayn <= base.day:
            return dt.date(base.year, base.month, dayn)
        prev = base.replace(day=1) - dt.timedelta(days=1)  # 11월 1일에 「31일」 → 10월 31일
        return dt.date(prev.year, prev.month, dayn)
    except ValueError:
        return None


def mark_date(m, base):
    """DATE_MARK 한 개 → 날짜(「10/24」「9월30일」「29일」「어제(27)」「어제」)."""
    if m[1]:
        return resolve(base, int(m[1]), int(m[2]))
    if m[4]:
        return resolve(base, int(m[3]) if m[3] else None, int(m[4]))
    return resolve(base, None, int(m[5])) if m[5] else base - dt.timedelta(days=1)


DAY_LIST = re.compile(r"\d{1,2}(?:\s*,\s*\d{1,2})+\s*일")
GAP = re.compile(r"^[\s,./·와과및]*$")


def segments(text, base):
    """댓글 → [(날짜, 글 조각)]. 날짜 표시가 없으면 [(base, 전체)].
    「17,18,19일 한방」「14일,15일 한방」처럼 날짜만 늘어놓으면 뒤의 양을 날마다 똑같이 준다."""
    text = DAY_LIST.sub(lambda m: ",".join(f"{n}일" for n in re.findall(r"\d{1,2}", m[0])), text)
    text = re.sub(r"어젯밤|지난밤", "어제 ", text)
    two = base - dt.timedelta(days=2)
    text = re.sub(r"엊그제|그저께|그제", f"{two.month}/{two.day} ", text)
    marks = list(DATE_MARK.finditer(text))
    out = [(base, text[:marks[0].start()] if marks else text)]
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        out.append((mark_date(m, base), text[m.end():end]))
    for k in range(len(out) - 2, 0, -1):  # 날짜 사이가 비었으면(「14일,15일 한방」) 다음 조각의 양을 받는다
        if GAP.match(out[k][1]):
            out[k] = (out[k][0], out[k + 1][1])
    return out


def short_name(name, names):
    """「홍길동(OO상회)」 → 「홍길동」. config의 names가 먼저."""
    return names.get(name) or re.sub(r"\s*\(.*?\)\s*", "", name).strip()


STATS = re.compile(r"어제는\s*\d+\s*명이")
GIDO = re.compile(r"기도\s*했")  # 「기도했습니다」「기도했어요」(사용자 2026-10-27: 한 방으로 · 목사님 셈과 같음)


def chapters_of(s):
    """읽을 곳 → {(책, 장)}. 「눅8~9」 「마28~막1」 「느11~13/시126」 「막14~16,눅1」. 모르는 책(오타 「먁」)은 (None, 장)."""
    out, book, prev = set(), None, None
    for part in re.split(r"[,/·]", re.sub(r"\s+", "", s).replace("-", "~")):
        prev = None
        for m in re.finditer(rf"({BOOK})?(\d+)(?:장|편)?(~)?", part):
            b, n = m[1] or book, int(m[2])
            if prev is not None and b == book and 0 <= n - prev <= 12:  # ponytail: 13장 넘는 범위는 오타로 보고 끝만 넣는다(「마18~190」)
                out |= {(b, k) for k in range(prev, n + 1)}
            else:
                out.add((b, n))
            book, prev = b, (n if m[3] else None)
    return out


def passage_days(text, titles):
    """댓글의 읽을 곳이 덮는 날들. 그날 제목의 (책, 장)이 모두 댓글 안에 있으면 그날(「마10~13」 = 마10~11 · 마12~13 이틀)."""
    have = chapters_of(text)
    return [d for d, p in titles.items() if (need := chapters_of(p)) and None not in {b for b, _ in need} and need <= have]


LATE = re.compile(r"어제|그제|그저께|\d+\s*일|\d+\s*/\s*\d+|[월화수목금토일]\s*(?:요일|욜)|지난\s*주|저번\s*주")
NOREAD = re.compile(r"못\s*(?:읽|했|봤)|안\s*읽")  # 「오늘은 못 읽었어요」


def lost_day(text, titles, base):
    """통독 댓글에 다른 날 몫을 적은 것 같은데 어느 날인지 못 찾았나.
    읽을 곳으로 찾은 날이 없고 「아멘」 줄의 숫자가 그날 읽을 곳 숫자와 다르면(「먁8~9」 = 그날 오타라 괜찮음),
    또는 「어제」「27일」「목욜」「저번주」를 썼는데 그날 것만 찾았으면(「저번주 목욜 토욜은 읽고도 못 달았습니다」)."""
    found, own = passage_days(text, titles), titles.get(base, "")
    nums = lambda s: re.findall(r"\d+", s)
    if not found and any(re.search("아[멘엔]", ln) and nums(ln) and nums(ln) != nums(own) for ln in text.splitlines()):
        return True
    return bool(LATE.search(text)) and set(found) <= {base}


def tally(kind, comments, day, band=None):
    """그달 1일~day까지 {이름: {일: 값}}, 그리고 day 몫의 못 읽은 댓글 목록.
    band["count_by"] == "post"이면 댓글이 달린 글의 날짜가 그 댓글의 날(한방기도방 방식). 아니면 댓글 쓴 날."""
    band = band or {}
    fn = chapters if kind == "bible" else prayer_minutes
    data, flags = {}, []
    for c in sorted(comments, key=lambda c: c["time"] or dt.datetime.min):  # 쓴 차례대로 → 같은 날 몫은 나중 댓글이 진본
        if not c["time"]:
            continue
        if STATS.search(c["text"]):  # 봇이 단 통계 댓글(「어제는 19명이 29시간…」)은 기도가 아니다
            continue
        pd = c.get("post_day")
        if band.get("count_by") == "post" and pd and c["time"] >= dt.datetime.combine(pd + dt.timedelta(days=1), dt.time()):
            continue  # 자정 마감(사용자 2026-10-28): 자정 뒤 지난 글에 단 댓글은 안 센다 → 다음 날 글에 날짜 · 읽을 곳을 적어 단다
        if band.get("mark"):  # 통독방: 읽었으면 ○(값 1) 하나. 한 글자(「ㄴ」 잘못 누름)는 뺀다
            name = short_name(c["name"], band.get("names", {}))
            if name in band.get("exclude", []) or len(c["text"].strip()) < 2:
                continue
            base = c.get("post_day") or c["time"].date()
            found = passage_days(c["text"], band.get("titles", {}))
            read = found or not NOREAD.search(c["text"]) and re.search(r"아[멘엔]|읽|\d", c["text"])  # 「못 읽었어요」 · 「기도했습니다」는 ○ 아님
            if base == day and (lost_day(c["text"], band.get("titles", {}), base) or not read and not NOREAD.search(c["text"])):
                flags.append((name, c["text"].strip()))  # 어느 날 몫인지 · 읽음인지 확실하지 않음 → 목사님 확인
            for when in (found or [base]) if read else []:
                if (when.year, when.month) == (day.year, day.month) and when <= day:
                    data.setdefault(name, {})[when.day] = 1
            continue
        base = c.get("post_day") if band.get("count_by") == "post" and c.get("post_day") else c["time"].date()
        text = c["text"].strip() if kind == "prayer" else c["text"].strip().split("\n")[0]
        name = short_name(c["name"], band.get("names", {}))
        if name in band.get("exclude", []):  # 밴드를 떠난 사람
            continue
        mine = {}  # 이 댓글 하나의 날마다 값(한 댓글 안에서는 더함)
        for when, piece in segments(text, base):
            done = kind == "prayer" and not has_number(piece) and GIDO.search(piece)  # 숫자 없는 「기도했습니다」 = 한 방
            if not when or not has_number(piece) and not done and not (kind == "prayer" and re.search("아[멘엔]", piece)):
                continue
            v = 60 if done else None if "요일" in piece else fn(piece)  # 「토요일 한방」: 어느 날인지 모름 → 확인 필요
            if v is None:
                if base == day and has_number(piece):
                    flags.append((name, text))
                continue
            if (when.year, when.month) != (day.year, day.month) or when > day:
                continue
            mine[when.day] = mine.get(when.day, 0) + v
            if done and kind == "prayer" and data.get(name, {}).get(when.day):
                mine.pop(when.day)  # 「한방아멘」 뒤 「기도했습니다」 = 같은 기도(10/21 목사님 셈)
        for d, v in mine.items():
            if kind == "prayer":
                data.setdefault(name, {})[d] = v  # 같은 날 몫을 또 달면 나중 댓글로(사용자 2026-10-28 · 고치려고 새로 단 댓글)
            else:
                data.setdefault(name, {})[d] = data.get(name, {}).get(d, 0) + v  # 옛 성경방(장 수): 더함
    return data, flags


# 관리 밴드 지시(목사님만 있는 비공개 밴드의 지시 글 댓글): 수정 · 이름 · 넣기 · 빼기
ORDER = re.compile(r"^\s*(수정|이름|빼기|넣기)\s*[:：]?\s*(.*?)\s*$")
WORDS = ("수정", "이름", "빼기", "넣기")
ARROW = re.compile(r"\s*(?:=|→|->|⇒)\s*")


def clean_name(s):
    return re.sub(r"\s*님$", "", s.strip())


def order_value(text, kind):
    """「2」「2방」「두방」「1시간 반」「3장」 → 분(기도) · 장(성경). 통독방(mark): 「○」「1」「읽음」 → 1 · 「0」「x」 → 0. 못 읽으면 None."""
    t = text.strip()
    if kind == "mark":
        return 1 if t in ("○", "o", "O", "1", "읽음") else 0 if t in ("0", "x", "X", "×", "안읽음") else None
    if re.fullmatch(r"\d+(?:\.\d+)?", t):
        return round(float(t) * 60) if kind == "prayer" else int(float(t))
    return prayer_minutes(t) if kind == "prayer" else chapters(t)


def show(v, kind):
    return "○" if kind == "mark" else f"{v / 60:g}방" if kind == "prayer" else f"{v}장"


def apply_orders(orders, band, kind="prayer"):
    """공지 글 지시(notice.md)를 band 설정 사본에 반영한다. 양식을 조금 틀려도 알아듣는다(쌍점 · 님 · 화살표 · 「2방」「두방」 · 「10월 25일」「25일」「어제」).
    돌려줌: band 사본, fixes [(날짜 또는 None(빼기 확인용), 이름, 값, 쓴 때, 줄)], notes [(쓴 때, 알림 글)]."""
    band = dict(band, names=dict(band.get("names", {})), exclude=list(band.get("exclude", [])),
                members=list(band.get("members", [])))
    tag = f"[{band.get('name', '')}]"
    fixes, notes = [], []
    for text, when in orders:
        for line in text.splitlines():
            if not any(w in line for w in WORDS):
                continue  # 지시가 아닌 말은 그냥 둔다
            m, ok = ORDER.match(line), False
            if m:
                cmd, rest = m[1], m[2]
                if cmd == "이름" and ARROW.search(rest):
                    a, b = ARROW.split(rest, 1)
                    band["names"][a.strip()] = clean_name(b)
                    notes.append((when, f"{tag} 반영함: {a.strip()} → {clean_name(b)}"))
                    ok = True
                elif cmd == "넣기" and rest:
                    band["members"].append(clean_name(rest))
                    notes.append((when, f"{tag} 반영함: 표에 {clean_name(rest)} 줄을 둡니다"))
                    ok = True
                elif cmd == "빼기" and rest:
                    band["exclude"].append(clean_name(rest))
                    fixes.append((None, clean_name(rest), None, when, line.strip()))
                    ok = True
                elif cmd == "수정":
                    d = when.date() - dt.timedelta(days=1)  # 날짜를 빼면 지시를 쓴 날의 어제
                    dm = DATE_MARK.search(rest)
                    if dm:
                        d = mark_date(dm, when.date())
                        rest = (rest[:dm.start()] + " " + rest[dm.end():]).strip()
                    parts = rest.split(None, 1)
                    if d and len(parts) == 2 and (v := order_value(parts[1], kind)) is not None:
                        fixes.append((d, clean_name(parts[0]), v, when, line.strip()))
                        ok = True
            if not ok:
                notes.append((when, f"{tag} 이 지시를 못 알아들었습니다: {line.strip()}\n양식 예: 수정 10/25 박민수 2"))
    return band, fixes, notes


def apply_fixes(data, flags, fixes, kind, day, known, tag=""):
    """「수정」을 셈에 덮어쓴다(0 = 뺌). 표에 없는 이름은 반영하지 않고 알린다. 고친 사람의 그날 확인 필요는 지운다.
    돌려줌: notes [(쓴 때, 알림 글)]."""
    notes = []
    for d, name, v, when, line in fixes:
        if name not in known:
            notes.append((when, f"{tag} 「{name}」을 표에서 못 찾아 반영하지 않았습니다: {line}\n"
                                f"이름을 확인하세요. 이번 달 댓글이 없는 분이면 먼저 「넣기 {name}」를 다세요."))
            continue
        if d is None:  # 빼기: 이름 확인만
            notes.append((when, f"{tag} 반영함: 표에서 {name} 줄을 뺍니다"))
            continue
        if (d.year, d.month) != (day.year, day.month) or d > day:
            continue
        if v:
            data.setdefault(name, {})[d.day] = v
        elif name in data:
            data[name].pop(d.day, None)
            if not data[name]:
                del data[name]
        notes.append((when, f"{tag} 반영함: {d.month}/{d.day} {name} {show(v, kind) if v else '뺌'}"))
        if d == day:
            flags[:] = [f for f in flags if f[0] != name]
    return notes


DOC_DATE = re.compile(r"^\s*(?:(\d{4})\s*[./-]\s*)?(\d{1,2})\s*(?:[./-]|월)\s*(\d{1,2})\s*일?\.?\s*(?:\(.\))?\s*$")


def load_ment(band, today):
    """목사님 멘트. 구글 문서(링크 공유) 또는 글 파일. 날짜만 있는 줄(10/27 · 2026.10.27 · 10월 27일) 아래가 그날 멘트."""
    src = band.get("ment")
    if src and src.startswith("env:"):  # 문서 주소는 저장소에 안 두고 비밀값(환경변수)으로 받는다
        src = os.environ.get(src[4:])
    if not src:
        return ""
    if "docs.google.com/document/d/" in src:
        doc_id = src.split("/d/")[1].split("/")[0]
        src = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
    try:  # 문서를 못 읽어도 글은 올린다(사용자 「실패하면 안 됨」) → None이면 main이 멘트 없이 올리고 알림
        raw = urllib.request.urlopen(src, timeout=30).read().decode("utf-8-sig") if src.startswith("http") \
            else (HERE / src).read_text(encoding="utf-8-sig")
    except Exception as e:
        print("멘트 문서를 못 읽음:", e)
        return None
    if "<html" in raw[:500].lower():  # 공유가 풀리면 구글이 로그인 화면을 준다
        print("멘트 문서를 못 읽음: 공유 설정을 보세요")
        return None
    out, cur, year = {}, None, None
    for line in raw.splitlines():
        y = re.match(r"^\s*(\d{4})\s*년?\s*$", line)  # 「2026」 「2026년」만 있는 줄 = 아래 날짜들의 연도
        m = DOC_DATE.match(line)
        if y:
            year, cur = int(y[1]), None
        elif m:
            cur = (int(m[1]) if m[1] else year, int(m[2]), int(m[3]))
            out[cur] = []
        elif cur:
            out[cur].append(line.rstrip())
    # 연도를 쓴 것이 먼저, 연도 없는 같은 날짜는 그다음
    lines = out.get((today.year, today.month, today.day)) or out.get((None, today.month, today.day)) or []
    ment = "\n".join(lines).strip()
    if not ment:
        print("멘트 없음:", today)
    return ment
