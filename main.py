#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import smtplib
from email.mime.text import MIMEText
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ----------------------------------------------------------------------
# 설정 로딩
# ----------------------------------------------------------------------

def load_config(path: str = "config.json"):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data

CONFIG = load_config()
USER_AGENT = CONFIG.get("browser_user_agent")
CONFIG_URLS = CONFIG.get("web_addresses", [])
MAX_LINKS = CONFIG.get("max_links", 2)


# ----------------------------------------------------------------------
# 키워드 로딩
# ----------------------------------------------------------------------

def load_keywords(path: str = "keywords.txt"):
    """keywords.txt에서 키워드 목록을 읽어온다."""
    keywords = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            kw = line.strip()
            if kw:
                keywords.append(kw)
    return keywords


# ----------------------------------------------------------------------
# HTML 가져오기
# ----------------------------------------------------------------------

def fetch_page(url: str) -> str | None:
    """
    주어진 URL에서 HTML을 가져온다.
    - 실제 브라우저와 유사한 헤더를 사용.
    - 200 OK가 아니거나 예외가 발생하면 None을 반환하고 로그만 출력한다.
    """
    if not url:
        return None

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-User": "?1",
        "Sec-Fetch-Dest": "document",
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


# ----------------------------------------------------------------------
# 키워드 기준으로 <a> 텍스트 매칭 + 상대경로 → 절대 URL 변환
# ----------------------------------------------------------------------

def find_keyword_links_in_html(html: str, base_url: str, keyword: str, max_links: int = 2):
    """
    BeautifulSoup으로 파싱한 후, <a> 태그의 텍스트에 키워드가 포함된 링크를 찾는다.
    - HTML 소스에서 태그로 인해 단어가 분리된 경우에도 get_text()로 자연스럽게 붙으므로
      "경희대학교"처럼 한글 대학명이 span 등으로 갈라져 있어도 탐지가 가능하다.
    - href가 상대경로(/recruitment/...)여도 base_url을 기준으로 절대 URL로 변환한다.
    - 각 키워드당 최대 max_links 개까지만 반환한다.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()

    # base_url에서 scheme+netloc 추출 (https://m.hibrain.net)
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    for a in soup.find_all("a", href=True):
        raw_href = a["href"].strip()
        if not raw_href:
            continue

        # javascript:, mailto: 등은 스킵
        lower = raw_href.lower()
        if lower.startswith("javascript:") or lower.startswith("mailto:") or lower.startswith("#"):
            continue

        # 절대/상대 URL 모두 허용 → 절대 URL로 변환
        # - raw_href가 http로 시작하면 그대로 사용
        # - 그렇지 않으면 base_url 기준으로 urljoin
        href_abs = raw_href
        if not (raw_href.startswith("http://") or raw_href.startswith("https://")):
            # origin 기준으로 조합 (예: /recruitment/... → https://m.hibrain.net/recruitment/...)
            href_abs = urljoin(origin, raw_href)

        # <a> 텍스트에서 키워드 검색
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


# ----------------------------------------------------------------------
# 이메일 본문 생성
# ----------------------------------------------------------------------

def build_email_body(matches):
    """
    matches: { keyword: [url1, url2, ...], ... } 형태
    (각 키워드당 최대 MAX_LINKS 개 URL)
    """
    lines = []
    lines.append("[Hibrain 임용 알리미] 지정 키워드 신규 감지 결과\n")

    for kw, urls in matches.items():
        lines.append(f"■ 키워드: {kw}")
        if urls:
            for i, u in enumerate(urls, start=1):
                lines.append(f"  - 관련 링크 {i}: {u}")
        else:
            lines.append("  - (키워드 주변에서 링크를 찾지 못했습니다.)")
        lines.append("")  # 빈 줄

    return "\n".join(lines)


# ----------------------------------------------------------------------
# 이메일 발송
# ----------------------------------------------------------------------

def send_email(subject: str, body: str):
    """
    Gmail SMTP를 이용해 이메일 발송.
    GitHub Actions에서는 환경변수로 계정/비밀번호/수신자 설정.
    """
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD")
    target_email = os.environ.get("TARGET_EMAIL")

    if not all([gmail_user, gmail_app_password, target_email]):
        raise RuntimeError("환경변수 GMAIL_USER, GMAIL_APP_PASSWORD, TARGET_EMAIL를 모두 설정해야 합니다.")

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = target_email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(gmail_user, gmail_app_password)
        smtp.send_message(msg)

    print("이메일 발송 완료")


# ----------------------------------------------------------------------
# 메인 로직
# ----------------------------------------------------------------------

def main():
    keywords = load_keywords()
    print(f"로드된 키워드: {keywords}")

    # 1) 각 URL에서 HTML 가져오기
    html_pages: list[tuple[str, str]] = []  # (base_url, html)

    for u in CONFIG_URLS:
        html = fetch_page(u)
        if html:
            html_pages.append((u, html))
        else:
            print(f"[WARN] HTML을 가져오지 못해 건너뜀: {u}")

    if not html_pages:
        print("[WARN] 어떤 URL에서도 HTML을 가져오지 못했습니다. 이메일을 보내지 않습니다.")
        return

    # 2) 키워드별 링크 수집
    matches: dict[str, list[str]] = {}

    for kw in keywords:
        for base_url, html in html_pages:
            urls = find_keyword_links_in_html(html, base_url, kw, max_links=MAX_LINKS)
            if urls:
                matches.setdefault(kw, []).extend(urls)

    # 3) 키워드별로 중복 제거 및 max_links 제한
    for k in list(matches.keys()):
        dedup = list(dict.fromkeys(matches[k]))  # 순서 유지하며 중복 제거
        matches[k] = dedup[:MAX_LINKS]

    if not matches:
        print("키워드를 포함한 신규 공지/링크를 찾지 못했습니다. 이메일을 보내지 않습니다.")
        return

    body = build_email_body(matches)
    subject = f"[Hibrain] 지정 대학교 임용 공지 링크 감지 (최대 {MAX_LINKS}개)"

    print("=== 이메일 미리보기 ===")
    print("Subject:", subject)
    print(body)
    print("=======================")

    send_email(subject, body)


if __name__ == "__main__":
    main()

