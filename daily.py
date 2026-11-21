"""매일 0시 넘어 한 번: 밴드마다 글과 댓글 조회 → 집계 → 현황 글 게시(Open API만).

  python daily.py --config config.json --dry-run           게시하지 않고 out/ 에 글만 만든다
  python daily.py --config config.json --day 2026-11-01    그날 몫으로

config.json(비공개 · 이 저장소에 두지 않음):
  {"lookback_days": 3, "bands": [{"name": "…", "kind": "prayer|bible", "band_key": "…",
    "style": "daily", "mark": true(통독), "day_one": "2025-09-08"(기도 N일째),
    "ment": "env:MENT_URL", "names": {"밴드 이름": "표 이름"}, "exclude": [], "members": [], "readonly": false}]}
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import urllib.request

import band_api as api
from report import build_daily, week_dots
from tally import DAILY, TITLE, load_ment, tally

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


def do_band(band, day, cfg, dry_run):
    today = day + dt.timedelta(days=1)
    title = build_daily({}, day, band).split("\n")[0]
    week_start = day - dt.timedelta(days=6)
    since = min(day.replace(day=1), week_start) - dt.timedelta(days=cfg.get("lookback_days", 3))
    comments, titles, firsts = read(band, since)
    if title in firsts:
        print(f"[{band['name']}] 이미 게시함: {title}")
        return []
    if titles:
        band = dict(band, titles=titles)
    data, flags = tally(band["kind"], comments, day, band)
    prev = tally(band["kind"], comments, week_start, band)[0] if week_start.month != day.month else {}
    ment = load_ment(band, today) if band.get("ment") else ""
    members = [n for n in band.get("members", []) if n not in band.get("exclude", [])]
    text = build_daily(data, day, band, ment or "") + "\n\n" + week_dots(data, prev, day, band["kind"], members)
    OUT.mkdir(exist_ok=True)
    (OUT / f"{band['name']}_{day}.txt").write_text(text, encoding="utf-8")
    print(f"[{band['name']}] 댓글 {len(comments)}개 · 참여 {len(data)}명 · 확인 필요 {len(flags)}개\n{text}\n")
    if not dry_run and not band.get("readonly"):
        api.write(band["band_key"], text)
        print(f"[{band['name']}] 게시함")
    msgs = [f"[{band['name']}] 확인 필요: {n} 「{t}」" for n, t in flags]
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
