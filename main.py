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
# HTML 가져오기
# ---------------------------------------------------------

def fetch_page(url: str, max_retries: int = 3) -> str | None:
    """주어진 URL에서 HTML을 가져온다. (403/429 재시도 포함)"""
    if not url:
        return None

    # hibrain은 모바일(m)에서 차단이 훨씬 덜함 — 자동 변환
    parsed = urlparse(url)
    if parsed.netloc == "www.hibrain.net":
        mobile_url = url.replace("://www.", "://m.")
        print(f"[INFO] www.hibrain.net 대신 모바일 도메인으로 시도: {mobile_url}")
        url = mobile_url

    # User-Agent 설정
    ua = USER_AGENT or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/100.0.4896.127 Safari/537.36"
    )
    SESSION.headers["User-Agent"] = ua

    # 재시도 로직
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
    """주어진 <a> 태그를 포함하는 <li> 태그에서 모집 기간을 추출한다."""
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
            text = content.strip()
            if text and text != '&nbsp;~&nbsp;':
                period_parts.append(text)

    period_str = "".join(period_parts).replace('~~', '~').strip()
    
    if period_str and '~' in period_str:
        return period_str
    
    return "(모집기간 정보 없음)"


def find_keyword_links_in_html(html: str, base_url: str, keyword: str, max_links: int = 2):
    """HTML 본문에서 키워드가 포함된 <a> 링크와 모집 기간을 찾는다."""
    soup = BeautifulSoup(html, "html.parser")
    results = [] 
    seen_urls = set()

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
            if href_abs not in seen_urls:
                period = extract_period(a)
                results.append((href_abs, period))
                seen_urls.add(href_abs)
                if len(results) >= max_links:
                    break

    return results 

# ---------------------------------------------------------
# 이메일 본문 생성
# ---------------------------------------------------------

def build_email_body(matches: dict):
    """matches 딕셔너리를 기반으로 이메일 본문을 생성한다."""
    lines = []
    lines.append("[Hibrain 임용 알리미] 지정 키워드 신규 감지 결과\n")

    for kw, link_periods in matches.items():
        period_info = link_periods[0][1] if link_periods else "(모집기간 정보 없음)"
        
        lines.append(f"■ 키워드: {kw} (모집기간: {period_info})")
        
        if link_periods:
            for i, (u, _) in enumerate(link_periods, start=1):
                lines.append(f"  - 관련 링크 {i}: {u}")
        else:
            lines.append("  - (키워드 주변 링크 없음)")
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
        sleep_time = random.uniform(1.0, 3.0)
        print(f"[{u}] 접근 전 {sleep_time:.2f}초 대기...")
        time.sleep(sleep_time) 
        
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
        keyword_matches = [] 
        
        for base_url, html in html_pages:
            link_period_pairs = find_keyword_links_in_html(html, base_url, kw, max_links=MAX_LINKS)
            if link_period_pairs:
                keyword_matches.extend(link_period_pairs)

        if keyword_matches:
            unique_matches = []
            seen_urls = set()
            for url, period in keyword_matches:
                if url not in seen_urls:
                    unique_matches.append((url, period))
                    seen_urls.add(url)
                    if len(unique_matches) >= MAX_LINKS:
                        break
            
            if unique_matches:
                matches[kw] = unique_matches
                
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
