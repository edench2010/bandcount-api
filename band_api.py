"""BAND Open API 호출(표준 라이브러리만). 문서: https://developers.band.us/develop/guide/api
토큰 = 환경변수 BAND_TOKEN(리더 한 사람의 토큰).

  python band_api.py bands     토큰 주인이 들어가 있는 밴드 이름과 band_key를 보여 준다
"""
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request

BASE = "https://openapi.band.us"
KST = dt.timezone(dt.timedelta(hours=9))


def call(path, method="GET", **params):
    params = dict(params, access_token=os.environ["BAND_TOKEN"])
    data = urllib.parse.urlencode(params)
    req = (urllib.request.Request(f"{BASE}{path}?{data}") if method == "GET"
           else urllib.request.Request(f"{BASE}{path}", data=data.encode(), method="POST"))
    got = json.load(urllib.request.urlopen(req, timeout=30))
    if got.get("result_code") != 1:
        raise RuntimeError(f"{path}: {got}")
    return got["result_data"]


def pages(path, **params):
    """next_params가 없을 때까지 items를 차례로 준다."""
    while True:
        r = call(path, **params)
        yield from r.get("items", [])
        nxt = (r.get("paging") or {}).get("next_params")
        if not nxt:
            return
        params = {k: v for k, v in nxt.items() if k != "access_token"}


def when(ms):
    return dt.datetime.fromtimestamp(ms / 1000, KST).replace(tzinfo=None)


def text(s):
    """언급 표시(<band:refer …>이름</band:refer>)를 벗기고 이스케이프를 푼다."""
    return html.unescape(re.sub(r"<[^>]+>", "", s or ""))


def bands():
    return call("/v2.1/bands")["bands"]


def posts(band_key, since):
    """since(날짜) 뒤에 쓴 글. 최신순으로 오므로 since보다 옛 글이 나오면 멈춘다."""
    out = []
    for p in pages("/v2/band/posts", band_key=band_key, locale="ko_KR"):
        if when(p["created_at"]).date() < since:
            break
        out.append(p)
    return out


def comments(band_key, post_key):
    return [{"name": c["author"]["name"].strip(), "role": c["author"].get("role"),
             "text": text(c.get("content")), "time": when(c["created_at"])}
            for c in pages("/v2/band/post/comments", band_key=band_key, post_key=post_key)]


def write(band_key, content):
    """글쓰기 · 알림 없음(do_push=false)."""
    return call("/v2.2/band/post/create", method="POST", band_key=band_key, content=content, do_push="false")


if __name__ == "__main__" and sys.argv[1:] == ["bands"]:
    for b in bands():
        print(b["band_key"], b["member_count"], b["name"])
