#!/usr/bin/env bash

import json
import os
import time
import random
import requests
import smtplib
from urllib.parse import urlparse
from email.mime.text import MIMEText
from email.utils import formataddr
from bs4 import BeautifulSoup


CONFIG_FILE = "config.json"


# =========================================================
# LOAD CONFIG.JSON
# =========================================================
def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("[WARN] 설정 파일을 읽는 중 오류 발생:", e)
        return {}


CONFIG = load_config()
USER_AGENT = CONFIG.get("browser_user_agent")
CONFIG_URLS = CONFIG.get("web_addresses", [])
MAX_LINKS = CONFIG.get("max_links", 2)
KEYWORDS = CONFIG.get("keywords", [])


# =========================================================
# GLOBAL SESSION 설정
# =========================================================
SESSION = requests.Session()
BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}
SESSION.headers.update(BASE_HEADERS)


# =========================================================
# 워밍업 요청 (최소 변경)
# =========================================================
def warmup_session(url):
    """같은 도메인의 루트 페이지를 한 번 찍어서 쿠키/세션 확보를 시도한다."""
    if getattr(SESSION, "_warmed_up", False):
        return
    try:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        print(f"[INFO] 워밍업 요청: {origin}")
        resp = SESSION.get(origin, timeout=10)
        print(f"[INFO] 워밍업 응답코드: {resp.status_code}")
    except Exception as e:
        print("[WARN] 워밍업 실패:", e)
    finally:
        SESSION._warmed_up = True


# =========================================================
# 페이지 요청 함수 (기존 형태 유지 + 403 개선)
# =========================================================
def fetch_page(url, max_retries=3):
    if not url:
        return None

    parsed = urlparse(url)
    if parsed.netloc == "www.hibrain.net":
        url = url.replace("://www.", "://m.")
        parsed = urlparse(url)

    ua = USER_AGENT or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    origin = f"{parsed.scheme}://{parsed.netloc}"

    SESSION.headers.update({
        "User-Agent": ua,
        "Referer": origin + "/recruitment",
        "Origin": origin,
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-User": "?1",
        "Accept-Encoding": "gzip, deflate, br",
    })

    # 워밍업 수행
    warmup_session(url)

    last_status = None

    for attempt in range(1, max_retries + 1):
        delay = random.uniform(1.0, 3.0) * attempt
        print(f"[INFO] {url} 요청 전 {delay:.2f}초 대기... (시도 {attempt}/{max_retries})")
        time.sleep(delay)

        try:
            resp = SESSION.get(url, timeout=15)
            last_status = resp.status_code
        except requests.RequestException as e:
            print(f"[WARN] 네트워크 오류 ({attempt}/{max_retries}) → {e}")
            continue

        if resp.status_code == 200:
            print(f"[INFO] 요청 성공: {url}")
            return resp.text

        if resp.status_code in (403, 429, 503):
            print(f"[WARN] 상태코드 {resp.status_code} → 재시도 {attempt}/{max_retries}")
            continue

        print(f"[WARN] 예기치 못한 상태코드 {resp.status_code} → 재시도 중단")
        break

    print(f"[WARN] 최종 요청 실패. 마지막 상태코드: {last_status}")
    return None


# =========================================================
# 공고 제목 파싱 (원래 구조와 비슷하게 유지)
# =========================================================
def parse_titles(html):
    soup = BeautifulSoup(html, "html.parser")
    titles = []
    for a in soup.find_all("a"):
        text = (a.text or "").strip()
        if text:
            titles.append(text)
    return titles


# =========================================================
# 이메일 발송 함수 - 요청하신 포맷 반영
#   items: [ {"link": ..., "period": ...}, ... ]
# =========================================================
def send_email(keyword, items):
    """
    keyword별 신규 감지 내역을 이메일 포맷에 맞게 전송.

    items 예시 구조:
    [
      {"link": "https://...", "period": "25.11.28~25.12.10"},
      ...
    ]

    실제 모집기간 추출 로직은 main() 쪽에서 items를 만들 때 채워주면 됩니다.
    (여기서는 포맷만 책임)
    """
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_from = os.environ.get("SMTP_FROM", smtp_user)
    smtp_to_raw = os.environ.get("SMTP_TO")  # 콤마로 여러 명 가능

    if not (smtp_user and smtp_password and smtp_to_raw and smtp_from):
        print("[WARN] SMTP 환경변수가 부족하여 이메일을 보낼 수 없습니다.")
        print("       (SMTP_USER, SMTP_PASSWORD, SMTP_TO, SMTP_FROM 필요)")
        return

    to_addrs = [addr.strip() for addr in smtp_to_raw.split(",") if addr.strip()]

    subject = "[Hibrain 임용 알리미] 지정 키워드 신규 감지 결과"

    lines = []
    lines.append(subject)
    lines.append("")
    # 키워드 블록
    # 예: ■ 키워드: 경희대학교 (모집기간: 25.11.28~25.12.10)
    #       - 관련 링크 1: https://....
    period_str = None
    if items and isinstance(items[0], dict):
        period_str = items[0].get("period")  # 대표 모집기간 (필요시 확장 가능)

    if period_str:
        lines.append(u"■ 키워드: {kw} (모집기간: {p})".format(kw=keyword, p=period_str))
    else:
        lines.append(u"■ 키워드: {kw}".format(kw=keyword))

    for idx, item in enumerate(items, start=1):
        link = item.get("link") if isinstance(item, dict) else str(item)
        lines.append(u"  - 관련 링크 {i}: {link}".format(i=idx, link=link))

    lines.append("")
    lines.append("※ 이 메일은 자동으로 발송되었습니다.")
    lines.append("")
    lines.append("-----")
    lines.append("GitHub Repo Address:")
    lines.append("https://github.com/leemgs/hibrain-prof-notifier/")

    body = "\n".join(lines)

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr(("Hibrain 임용 알리미", smtp_from))
    msg["To"] = ", ".join(to_addrs)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_from, to_addrs, msg.as_string())
        print(f"[INFO] 이메일 발송 완료 (키워드: {keyword}, 수신자: {msg['To']})")
    except Exception as e:
        print("[ERROR] 이메일 발송 실패:", e)


# =========================================================
# 메인 로직 (period는 placeholder, 실제 로직에 맞게 수정 가능)
# =========================================================
def main():
    print("로드된 키워드:", KEYWORDS)
    if not CONFIG_URLS:
        print("[WARN] web_addresses가 설정되어 있지 않습니다.")
        return

    # detected 구조 예:
    # { "경희대학교": [ {"link": ..., "period": ...}, ... ], ... }
    detected = {}

    for url in CONFIG_URLS:
        html = fetch_page(url)
        if not html:
            print(f"[WARN] HTML을 가져오지 못해 건너뜀: {url}")
            continue

        titles = parse_titles(html)

        for kw in KEYWORDS:
            matched = [t for t in titles if kw in t]
            if not matched:
                continue

            if kw not in detected:
                detected[kw] = []

            # ★ 여기서 실제 코드에 맞게 모집기간을 추출해서 넣으면 됨
            #   현재는 placeholder로 "알 수 없음"을 사용
            period_placeholder = "알 수 없음"

            # 너무 많으면 상위 MAX_LINKS개만
            use_count = len(matched)
            if MAX_LINKS and MAX_LINKS > 0:
                use_count = min(use_count, MAX_LINKS)

            for i in range(use_count):
                detected[kw].append({
                    "link": url,
                    "period": period_placeholder,
                })

    if not detected:
        print("[INFO] 신규 감지된 공고가 없습니다. 이메일 발송 없음.")
        return

    for kw, items in detected.items():
        send_email(kw, items)


if __name__ == "__main__":
    main()
