#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import smtplib
from email.mime.text import MIMEText
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------
# 설정 로딩
# ---------------------------------------------------------

def load_config(path: str = "config.json"):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

CONFIG = load_config()
USER_AGENT = CONFIG.get("browser_user_agent")
CONFIG_URLS = CONFIG.get("web_addresses", [])
MAX_LINKS = CONFIG.get("max_links", 2)

# ---------------------------------------------------------
# 키워드 로딩
# ---------------------------------------------------------

def load_keywords(path: str = "keywords.txt"):
    """keywords.txt에서 키워드 목록을 읽는다."""
    keywords = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            kw = line.strip()
            if kw:
                keywords.append(kw)
    return keywords

# ---------------------------------------------------------
# HTML 가져오기
# ---------------------------------------------------------

def fetch_page(url: str) -> str | None:
    """주어진 URL에서 HTML을 가져온다."""
    if not url:
        return None

    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    ua = USER_AGENT or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    )

    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": origin + "/recruitment",
        "Connection": "keep-alive",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"[WARN] 요청 실패: {url} (status={resp.status_code})")
            return None
        resp.encoding = resp.apparent_encoding
        return resp.text
    except Exception as e:
        print(f"[ERROR] 요청 중 예외 발생: {url} ({e})")
        return None

# ---------------------------------------------------------
# HTML에서 키워드 링크 찾기
# ---------------------------------------------------------

def find_keyword_links_in_html(html: str, base_url: str, keyword: str, max_links: int = 2):
    """HTML 본문에서 키워드가 포함된 <a> 링크를 찾는다."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()

    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    for a in soup.find_all("a", href=True):
        raw_href = a["href"].strip()
        if not raw_href:
            continue

        if raw_href.lower().startswith(("javascript:", "mailto:", "#")):
            continue

        if raw_href.startswith(("http://", "https://")):
            href_abs = raw_href
        else:
            href_abs = urljoin(origin, raw_href)

        text = a.get_text(" ", strip=True)
        if not text:
            continue

        if keyword in text:
            if href_abs not in seen:
                results.append(href_abs)
                seen.add(href_abs)
                if len(results) >= max_links:
                    break

    return results

# ---------------------------------------------------------
# 이메일 본문 생성
# ---------------------------------------------------------

def build_email_body(matches):
    lines = []
    lines.append("[Hibrain 임용 알리미] 지정 키워드 신규 감지 결과\n")

    for kw, urls in matches.items():
        lines.append(f"■ 키워드: {kw}")
        if urls:
            for i, u in enumerate(urls, start=1):
                lines.append(f"  - 관련 링크 {i}: {u}")
        else:
            lines.append("  - (키워드 주변 링크 없음)")
        lines.append("")

    # Footer 추가
    lines.append("-----")
    lines.append("GitHub Repo Address:")
    lines.append("https://github.com/leemgs/hibrain-prof-notifier/")

    return "\n".join(lines)

# ---------------------------------------------------------
# 이메일 발송
# ---------------------------------------------------------

def send_email(subject: str, body: str):
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD")
    target_email = os.environ.get("TARGET_EMAIL")

    if not all([gmail_user, gmail_app_password, target_email]):
        raise RuntimeError("GMAIL_USER, GMAIL_APP_PASSWORD, TARGET_EMAIL 환경변수를 모두 설정해야 합니다.")

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = target_email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(gmail_user, gmail_app_password)
        smtp.send_message(msg)

    print("이메일 발송 완료")

# ---------------------------------------------------------
# 메인 로직
# ---------------------------------------------------------

def main():
    keywords = load_keywords()
    print(f"로드된 키워드: {keywords}")

    html_pages = []

    for u in CONFIG_URLS:
        html = fetch_page(u)
        if html:
            html_pages.append((u, html))
        else:
            print(f"[WARN] HTML을 가져오지 못함: {u}")

    if not html_pages:
        print("[WARN] 어떤 URL에서도 HTML을 가져오지 못했습니다. 이메일 발송 없음.")
        return

    matches = {}

    for kw in keywords:
        for base_url, html in html_pages:
            urls = find_keyword_links_in_html(html, base_url, kw, max_links=MAX_LINKS)
            if urls:
                matches.setdefault(kw, []).extend(urls)

    # 중복 제거
    for k in matches:
        matches[k] = list(dict.fromkeys(matches[k]))[:MAX_LINKS]

    if not matches:
        print("키워드 관련 링크 없음. 이메일 발송하지 않음.")
        return

    body = build_email_body(matches)
    subject = f"[Hibrain] 임용 공지 알리미 (최대 {MAX_LINKS}개 링크)"

    print("=== 이메일 미리보기 ===")
    print("Subject:", subject)
    print(body)
    print("=======================")

    send_email(subject, body)

if __name__ == "__main__":
    main()
