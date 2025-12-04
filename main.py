#!/usr/bin/env bash

import json
import time
import random
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup


# -------------------------------------------
# 1) 세션 & 헤더 설정 (최적화된 실제 브라우저 헤더)
# -------------------------------------------
SESSION = requests.Session()

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
SESSION.headers.update(DEFAULT_HEADERS)



# -------------------------------------------
# 2) 워밍업 요청 - 최초 1회만 실행
# -------------------------------------------
def warmup_session(url: str) -> None:
    if getattr(SESSION, "_warmed_up", False):
        return

    try:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        print(f"[INFO] 워밍업 요청: {origin}")
        resp = SESSION.get(origin, timeout=10)
        print(f"[INFO] 워밍업 응답 코드: {resp.status_code}")
    except Exception as e:
        print(f"[WARN] 워밍업 실패: {e}")
    finally:
        SESSION._warmed_up = True



# -------------------------------------------
# 3) HTML 요청 함수 (403 회피/지수 백오프 적용)
# -------------------------------------------
def fetch_page(url: str, max_retries: int = 3, base_delay: float = 1.5):
    warmup_session(url)

    last_status = None
    for attempt in range(1, max_retries + 1):

        delay = base_delay * attempt * random.uniform(1.0, 2.8)
        print(f"[INFO] {url} 요청 전 {delay:.2f}초 대기...")
        time.sleep(delay)

        try:
            resp = SESSION.get(url, timeout=10)
            last_status = resp.status_code

            if resp.status_code == 200:
                print(f"[INFO] 성공: {url}")
                return resp.text

            if resp.status_code in (403, 429):
                print(f"[WARN] 접근 제한 (status={last_status}), 재시도 {attempt}/{max_retries}")
                continue

            print(f"[WARN] 예외 응답 코드={last_status}, 재시도 중단")
            break

        except requests.RequestException as e:
            print(f"[WARN] 네트워크 오류 발생 — {e} (재시도 {attempt}/{max_retries})")

    print(f"[WARN] {url}에서 HTML을 끝내 가져오지 못함 (마지막 상태={last_status})")
    return None



# -------------------------------------------
# 4) config.json 읽기
# -------------------------------------------
def load_keywords():
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
        return config.get("keywords", []), config.get("target_urls", [])



# -------------------------------------------
# 5) 신규 공고 감지 로직
# -------------------------------------------
def extract_notice_titles(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")

    titles = []
    for a in soup.find_all("a"):
        text = (a.text or "").strip()
        if text:
            titles.append(text)

    return titles



# -------------------------------------------
# 6) 이메일 전송(형식은 유지)
# -------------------------------------------
def send_email(keyword: str, links: list[str]):
    print("\n===== 이메일 발송 시작 =====")
    print(f"키워드: {keyword}")
    for link in links:
        print(f" - {link}")
    print("===== 이메일 발송 종료 =====\n")
    


# -------------------------------------------
# 7) 메인 실행
# -------------------------------------------
def main():
    keywords, target_urls = load_keywords()
    print(f"로드된 키워드: {keywords}")

    detected_changes = {}

    for url in target_urls:
        html = fetch_page(url)
        if not html:
            print(f"[WARN] HTML 읽지 못함. URL 건너뜀 → {url}")
            continue

        titles = extract_notice_titles(html)

        for kw in keywords:
            matched = [title for title in titles if kw in title]
            if matched:
                if kw not in detected_changes:
                    detected_changes[kw] = []
                detected_changes[kw].append((url, matched))

    # 결과 처리
    if not detected_changes:
        print("[INFO] 신규 항목 없음. 이메일 발송 없음.")
        return

    # 이메일 전송
    for kw, items in detected_changes.items():
        links = [f"{u} ({', '.join(t)})" for u, t in items]
        send_email(kw, links)



if __name__ == "__main__":
    main()


