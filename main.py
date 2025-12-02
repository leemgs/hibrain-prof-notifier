#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import smtplib
from email.mime.text import MIMEText
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag
import random
import time 

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

# 전역 세션 및 기본 헤더 설정 (403 완화용)
SESSION = requests.Session()
BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}
SESSION.headers.update(BASE_HEADERS)

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
# HTML 가져오기 (403 완화 핵심)
# ---------------------------------------------------------

def fetch_page(url: str, max_retries: int = 3) -> str | None:
    """주어진 URL에서 HTML을 가져온다. (403/429 재시도 포함)"""
    if not url:
        return None

    # 모바일 도메인으로 자동 전환
    parsed_for_domain = urlparse(url)
    if parsed_for_domain.netloc == "www.hibrain.net":
        mobile_url = url.replace("://www.", "://m.")
        print(f"[INFO] www.hibrain.net 대신 모바일 도메인으로 시도: {mobile_url}")
        url = mobile_url

    # User-Agent 설정
    ua = USER_AGENT or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/100.0.4896.127 Safari/537.36"
    )

    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    # 브라우저와 최대한 비슷한 헤더 세팅
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

    # 재시도
    for attempt in range(1, max_retries + 1):
        try:
            resp = SESSION.get(url, timeout=15)
        except Exception as e:
            print(f"[ERROR] 요청 중 예외 발생: {url} ({e}) (재시도 {attempt}/{max_retries})")
            if attempt < max_retries:
                time.sleep(2 * attempt)
                continue
            return None

        if resp.status_code == 200:
            resp.encoding = resp.apparent_encoding
            return resp.text

        if resp.status_code in (403, 429):
            print(f"[WARN] 요청 실패: {url} (status={resp.status_code}), 재시도 {attempt}/{max_retries}")
            if attempt < max_retries:
                time.sleep(3 * attempt)
                continue
            return None

        print(f"[WARN] 요청 실패: {url} (status={resp.status_code})")
        return None

    print(f"[WARN] 재시도 후에도 HTML을 가져오지 못했습니다: {url}")
    return None

# ---------------------------------------------------------
# HTML에서 키워드 링크와 모집기간 찾기
# ---------------------------------------------------------

def extract_period(a_tag: Tag) -> str:
    """<a> 태그가 속한 <li>에서 모집 기간을 추출."""
    li_row = a_tag.find_parent("li", class_="row sortRoot")
    if not li_row:
        return "(모집기간 정보 없음)"
    
    receipt_span = li_row.find("span", class_="td_receipt")
    if not receipt_span:
        return "(모집기간 정보 없음)"
    
    period_parts = []
    for content in receipt_span.contents:
        if isinstance(content, Tag) and 'number' in content.get('class', []):
            period_parts.append(content.get_text(strip=True))
        elif isinstance(content, Tag) and 'specialCharacter' in content.get('class', []):
            period_parts.append('~')
        elif isinstance(content, str):
            t = content.strip()
            if t and t != '&nbsp;~&nbsp;':
                period_parts.append(t)

    period_str = "".join(period_parts).replace("~~", "~").strip()
    if period_str and "~" in period_str:
        return period_str

    return "(모집기간 정보 없음)"


def find_keyword_links_in_html(html: str, base_url: str, keyword: str, max_links: int = 2):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()

    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    for a in soup.find_all("a", href=True):
        raw = a["href"].strip()
        if not raw or raw.startswith(("javascript:", "mailto:", "#")):
            continue

        if raw.startswith("http"):
            href_abs = raw
        else:
            href_abs = urljoin(origin, raw)

        text = a.get_text(" ", strip=True)
        if keyword in text and href_abs not in seen:
            period = extract_period(a)
            results.append((href_abs, period))
            seen.add(href_abs)
            if len(results) >= max_links:
                break

    return results

# ---------------------------------------------------------
# 이메일 생성
# ---------------------------------------------------------

def build_email_body(matches: dict):
    lines = []
    lines.append("[Hibrain 임용 알리미] 지정 키워드 신규 감지 결과\n")

    for kw, pairs in matches.items():
        period = pairs[0][1] if pairs else "(모집기간 정보 없음)"
        lines.append(f"■ 키워드: {kw} (모집기간: {period})")
        for i, (url, _) in enumerate(pairs, start=1):
            lines.append(f"  - 관련 링크 {i}: {url}")
        lines.append("")

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
        t = random.uniform(1.0, 3.0)
        print(f"[{u}] 접근 전 {t:.2f}초 대기...")
        time.sleep(t)

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
        found = []
        for base, html in html_pages:
            pairs = find_keyword_links_in_html(html, base, kw, max_links=MAX_LINKS)
            if pairs:
                found.extend(pairs)

        if found:
            unique = []
            seen = set()
            for url, period in found:
                if url not in seen:
                    unique.append((url, period))
                    seen.add(url)
                    if len(unique) >= MAX_LINKS:
                        break
            if unique:
                matches[kw] = unique

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
