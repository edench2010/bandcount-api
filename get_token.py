"""리더 계정 연결(한 번만). 문서: 「로그인 - OAuth 토큰 얻기」.
Client ID · Secret은 환경변수 BAND_CLIENT_ID · BAND_CLIENT_SECRET로 받는다(화면에 쓰지 않는다).

  python get_token.py url                  리더에게 보낼 연결 링크를 보여 준다
  python get_token.py <code> <저장할 파일>   리더가 보내 준 인증 코드 → 토큰을 파일에만 저장한다
"""
import base64
import json
import os
import pathlib
import sys
import urllib.parse
import urllib.request

REDIRECT = "https://edench2010.github.io/bandcount-api/"

cid, secret = os.environ["BAND_CLIENT_ID"], os.environ.get("BAND_CLIENT_SECRET", "")
if sys.argv[1:] == ["url"]:
    print("https://auth.band.us/oauth2/authorize?" + urllib.parse.urlencode(
        {"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT}))
elif len(sys.argv) == 3:
    code, path = sys.argv[1], pathlib.Path(sys.argv[2])
    auth = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    req = urllib.request.Request("https://auth.band.us/oauth2/token?" + urllib.parse.urlencode(
        {"grant_type": "authorization_code", "code": code}), headers={"Authorization": f"Basic {auth}"})
    got = json.load(urllib.request.urlopen(req, timeout=30))
    path.write_text(got["access_token"])
    path.chmod(0o600)
    print(f"토큰 저장함: {path} · 유효 {got.get('expires_in', 0) // 86400}일 · 권한 {got.get('scope')}")
else:
    print(__doc__)
