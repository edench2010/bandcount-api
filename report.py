"""현황 글(글자만). data = {이름: {일: 값}} (기도 = 분, 통독 = 1)."""
import datetime as dt

WEEK = "월화수목금토일"


def fmt(v, kind):
    if kind == "bible":
        return str(v)
    h = v / 60
    return str(int(h)) if h == int(h) else f"{h:g}"


def build_daily(data, day, band, ment=""):
    """한방기도방 꼴: 「414일째(2026.10.26.월)」 · 멘트 · 「어제는 7명이 14시간을 방언으로 기도했습니다.」
    통독방 꼴: 「2026.10.28.수(눅10~11)」 · 해설 · 「어제는 N명이 성경을 읽었습니다.」
    day = 통계를 내는 날(어제). 글 제목은 오늘."""
    today = day + dt.timedelta(days=1)
    wd = "주일" if today.weekday() == 6 else WEEK[today.weekday()]
    vals = [d[day.day] for d in data.values() if d.get(day.day)]
    if band["kind"] == "bible":
        first, _, rest = ment.strip().partition("\n")  # 멘트 문서: 날짜 줄 아래 첫 줄 = 읽을 곳, 그 아래 = 해설
        if len(first) > 20:  # 읽을 곳을 빠뜨렸으면 첫 줄도 해설이다
            first, rest = "", ment.strip()
        lines = [f"{today.year}.{today.month}.{today.day}.{wd}" + (f"({first.strip()})" if first.strip() else ""), ""]
        if rest.strip():
            lines += [rest.strip(), ""]
        return "\n".join(lines + [f"어제는 {len(vals)}명이 성경을 읽었습니다."])
    n = (today - dt.date.fromisoformat(band["day_one"])).days + 1
    lines = [f"{n}일째({today.year}.{today.month}.{today.day}.{wd})", ""]
    if ment.strip():
        lines += [ment.strip(), ""]
    lines.append(f"어제는 {len(vals)}명이 {fmt(sum(vals), 'prayer')}시간을 방언으로 기도했습니다.")
    return "\n".join(lines)


def week_dots(month, prev, day, kind, members=()):
    """최근 1주일 점 · 이달 합계. 휴대폰 한 줄(약 17자)에 들어가게 한 사람 한 줄.
    month = day가 있는 달의 data, prev = 지난달 data(1주일이 지난달에 걸칠 때)."""
    days = [day - dt.timedelta(days=i) for i in range(6, -1, -1)]
    at = lambda name, d: (month if (d.year, d.month) == (day.year, day.month) else prev).get(name, {}).get(d.day)
    w = lambda d: "주" if d.weekday() == 6 else WEEK[d.weekday()]
    legend = "● 기도함 ○ 안 함 · (이달 시간)" if kind == "prayer" else "● 읽음 ○ 안 읽음 · (이달 읽은 날)"
    lines = [f"▶ 최근 1주일 {days[0].month}/{days[0].day}({w(days[0])}) ~ {day.month}/{day.day}({w(day)})", legend, ""]
    for name in sorted(set(month) | set(members)):
        v = month.get(name, {})
        total = f"{fmt(sum(v.values()), 'prayer')}" if kind == "prayer" else f"{len(v)}일"
        lines.append(f"{name} {''.join('●' if at(name, d) else '○' for d in days)} ({total})")
    return "\n".join(lines)


if __name__ == "__main__":  # 자체 확인: 달이 바뀌는 주 · 기록 없는 멤버
    day = dt.date(2026, 11, 2)
    month = {"김가": {1: 60, 2: 120}}
    prev = {"김가": {31: 60}, "박나": {27: 60}}
    out = week_dots(month, prev, day, "prayer", members=["박나"])
    assert "▶ 최근 1주일 10/27(화) ~ 11/2(월)" in out, out
    assert "김가 ○○○○●●● (3)" in out, out
    assert "박나 ●○○○○○○ (0)" in out, out  # 10/27 점은 찍고, 지난달 기록은 이달 합계에 안 들어간다
    print(out)
    print("OK")
