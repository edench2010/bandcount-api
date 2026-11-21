"""매일 0시 넘어 한 번: 밴드마다 글과 댓글 조회 → 집계 → 현황 글 게시(Open API만).

  python daily.py --config config.json --dry-run           게시하지 않고 out/ 에 글만 만든다
  python daily.py --config config.json --day 2026-11-01    그날 몫으로

config.json(비공개 · 이 저장소에 두지 않음):
  {"lookback_days": 3, "bands": [{"name": "…", "kind": "prayer|bible", "band_key": "…",
    "style": "daily", "mark": true(통독), "day_one": "2025-09-08"(기도 N일째),
    "ment": "env:MENT_URL", "names": {"밴드 이름": "표 이름"}, "exclude": [], "members": [], "readonly": false,
    "orders_band_key": "…", "orders_post_key": "…"(관리 밴드의 이 밴드 몫 지시 글)}]}

명단(표에 나오는 사람) = 지난달 참여자 + 이달 댓글 단 사람 + 「넣기」 − 「빼기」 · exclude.
지난달 참여자는 말일 몫을 돌릴 때(게시 성공 여부와 상관없이 · --dry-run 빼고) active-<밴드 이름>.json(config 옆)에 남긴다.
→ 1일 글(말일 몫)에는 그달 기록이 있는 사람만 나온다(「넣기」도 기록이 없으면 안 나옴). 기록이 0이면 빠진다(사용자 2026-11-20 「1일 볼 필요가 없어」).
"""
import argparse
import calendar
import datetime as dt
import json
import os
import pathlib
import urllib.request

import band_api as api
from report import build_daily, week_dots
from tally import DAILY, TITLE, apply_fixes, apply_orders, load_ment, short_name, tally

OUT = pathlib.Path("out")


def notify(msgs):
    """휴대폰 알림(ntfy). 주제 = 비밀값 NTFY_TOPIC. 없으면 화면에만."""
    topic = os.environ.get("NTFY_TOPIC")
    for msg in msgs:
        print("알림:", msg)
        if topic:
            urllib.request.urlopen(urllib.request.Request(f"https://ntfy.sh/{topic}", data=msg.encode()), timeout=20)


def read(band, since):
    """매일 글의 댓글 전부 [{name, text, time, post_day}] · 통독방 제목 {날짜: 읽을 곳} · 글 첫 줄들."""
    comments, titles, firsts = [], {}, set()
    for p in api.posts(band["band_key"], since):
        body = api.text(p.get("content"))
        firsts.add(body.strip().split("\n")[0].strip())
        if not DAILY.search(body):
            continue  # 매일 글이 아님(공지 등) → 그 댓글은 안 센다
        pday = api.when(p["created_at"]).date()
        if m := TITLE.search(body):
            try:
                td = dt.date(int(m[1]), int(m[2]), int(m[3]))
                pday = td if abs((td - pday).days) <= 1 else pday  # 새벽에 미리 올린 글은 제목 날짜
            except ValueError:
                pass
            titles[pday] = m[4]
        if p.get("comment_count"):
            comments += [dict(c, post_day=pday) for c in api.comments(band["band_key"], p["post_key"])]
    return comments, titles, firsts


def read_orders(band):
    """관리 밴드 지시 글에 리더 · 공동리더가 단 댓글 [(글, 쓴 때)]. 역할로 가린다 → 이름을 흉내 내도 안 통한다."""
    if not band.get("orders_post_key"):
        return []
    return [(c["text"], c["time"]) for c in api.comments(band["orders_band_key"], band["orders_post_key"])
            if c["role"] in ("leader", "coleader")]


def do_band(band, day, cfg, dry_run):
    today = day + dt.timedelta(days=1)
    tag = f"[{band['name']}]"
    kind = "mark" if band.get("mark") else band["kind"]  # 지시(수정) 값 읽는 법
    msgs = []
    try:  # 관리 밴드를 못 읽어도 현황 글은 올린다
        orders = read_orders(band)
    except Exception as e:
        orders = []
        msgs.append(f"{tag} 관리 밴드 지시를 못 읽어 지시 없이 만들었습니다: {e}")
    band, fixes, notes = apply_orders(orders, band, kind)
    title = build_daily({}, day, band).split("\n")[0]
    week_start = day - dt.timedelta(days=6)
    prev_end = day.replace(day=1) - dt.timedelta(days=1)  # 지난달 말일
    since = min(day.replace(day=1), week_start) - dt.timedelta(days=cfg.get("lookback_days", 3))
    comments, titles, firsts = read(band, since)
    if titles:
        band = dict(band, titles=titles)
    active = cfg["_dir"] / f"active-{band['name']}.json"
    last = json.loads(active.read_text(encoding="utf-8")) if active.exists() else {}
    month_end = day.day == calendar.monthrange(day.year, day.month)[1]
    carry = last.get("names", []) if last.get("month") == prev_end.strftime("%Y-%m") else []
    data, flags = tally(band["kind"], comments, day, band)
    prev = tally(band["kind"], comments, prev_end, band)[0] if week_start.month != day.month else {}
    known = {short_name(c["name"], band.get("names", {})) for c in comments} | set(band["members"]) | set(carry)
    notes += apply_fixes(data, flags, fixes, kind, day, known, tag, prev)
    if month_end and not dry_run:  # 게시 성공 · 실패와 상관없이 이달 참여자를 다음 달 명단으로(손으로 올려도 이어지게)
        active.write_text(json.dumps({"month": day.strftime("%Y-%m"), "names": sorted(data)}, ensure_ascii=False), encoding="utf-8")
    if title in firsts:
        print(f"[{band['name']}] 이미 게시함: {title}")
        return []
    ment = load_ment(band, today) if band.get("ment") else ""
    members = [] if month_end else [n for n in set(band["members"]) | set(carry) if n not in band.get("exclude", [])]  # 1일 글엔 그달 기록이 있는 사람만
    text = build_daily(data, day, band, ment or "") + "\n\n" + week_dots(data, prev, day, band["kind"], members)
    OUT.mkdir(exist_ok=True)
    (OUT / f"{band['name']}_{day}.txt").write_text(text, encoding="utf-8")
    print(f"[{band['name']}] 댓글 {len(comments)}개 · 참여 {len(data)}명 · 확인 필요 {len(flags)}개\n{text}\n")
    if not dry_run and not band.get("readonly"):
        api.write(band["band_key"], text)
        print(f"[{band['name']}] 게시함")
    # 통계 날(day)부터 쓴 지시만 알린다 → 실행 시각이 밀려도 빠지지 않는다(자정 ~ 실행 사이 지시는 두 번 갈 수 있음)
    msgs += [msg for when, msg in notes if when.date() >= day]
    msgs += [f"{tag} 확인 필요: {n} 「{t}」" for n, t in flags]
    if ment is None:
        msgs.append(f"[{band['name']}] 멘트 문서를 못 읽어 멘트 없이 만들었습니다(문서 공유 설정을 보세요)")
    return msgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--day", help="통계 날(기본 = 한국 어제)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = json.loads(pathlib.Path(a.config).read_text(encoding="utf-8"))
    cfg["_dir"] = pathlib.Path(a.config).resolve().parent
    day = dt.date.fromisoformat(a.day) if a.day else dt.datetime.now(api.KST).date() - dt.timedelta(days=1)
    msgs, failed = [], []
    for band in cfg["bands"]:
        try:
            msgs += do_band(band, day, cfg, a.dry_run)
        except Exception as e:  # 밴드 하나가 실패해도 나머지는 한다
            failed.append(f"{band['name']}: {e}")
    if failed:
        msgs.append("현황 글을 못 만든 밴드가 있습니다. 손으로 올려 주세요.\n" + "\n".join(failed))
    if not a.dry_run:
        notify(msgs)
    if failed:
        raise SystemExit("실패: " + " · ".join(failed))


if __name__ == "__main__":
    main()
