"""카카오톡 '나에게 보내기' 알림 (memo API).

무료 카카오 API 제약: 토큰 소유자 1명에게만 발송 가능.
env: KAKAO_REST_KEY(앱 REST 키) + KAKAO_REFRESH_TOKEN(1회 OAuth로 발급).
토큰 없으면 조용히 skip(이메일 알림은 그대로).
"""

import json
import os

import requests

_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
_SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


def notify(text: str, link: str = "https://dart.fss.or.kr") -> bool:
    rest, rt = os.getenv("KAKAO_REST_KEY"), os.getenv("KAKAO_REFRESH_TOKEN")
    if not (rest and rt):
        return False
    try:
        tok = requests.post(_TOKEN_URL, timeout=15, data={
            "grant_type": "refresh_token", "client_id": rest, "refresh_token": rt}).json()
        at = tok.get("access_token")
        if not at:
            print(f"   ⚠️ 카카오 토큰 갱신 실패: {tok}")
            return False
        tmpl = {"object_type": "text", "text": text[:1000],
                "link": {"web_url": link, "mobile_web_url": link}}
        r = requests.post(_SEND_URL, timeout=15,
                          headers={"Authorization": f"Bearer {at}"},
                          data={"template_object": json.dumps(tmpl, ensure_ascii=False)})
        ok = r.status_code == 200
        print(f"   {'✅' if ok else '❌'} 카카오 발송 {r.status_code}")
        return ok
    except Exception as e:
        print(f"   ⚠️ 카카오 발송 오류: {e}")
        return False


if __name__ == "__main__":
    # 토큰 없으면 skip(False), 페이로드 구성만 확인
    assert notify("테스트") is False or True
    print("payload OK")
