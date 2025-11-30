#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import smtplib
from email.mime.text import MIMEText

import requests
from bs4 import BeautifulSoup

HIBRAIN_URL = None  # loaded from config.txt

# 키워드 주변에서 URL을 찾을 때 사용할 검색 윈도우 크기 (앞뒤 1000자)
URL_SEARCH_WINDOW = 1000



def load_config(path="config.json"):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data

CONFIG = load_config()
USER_AGENT = CONFIG.get("browser_user_agent")
CONFIG_URLS = CONFIG.get("web_addresses", [])
MAX_LINKS = CONFIG.get("max_links", 2)
HIBRAIN_URL = None



def load_keywords(path: str = "keywords.txt"):
    """keywords.txt에서 키워드 목록을 읽어온다."""
    keywords = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            kw = line.strip()
            if kw:
                keywords.append(kw)
    return keywords


def fetch_page(url: str) -> str:
    headers={"User-Agent": USER_AGENT}
    resp=requests.get(url,headers=headers,timeout=15)
    resp.raise_for_status()
    resp.encoding=resp.apparent_encoding
    return resp.text


def find_closest_urls_for_keyword(html: str, keyword: str, max_links: int = 2):
    """
    HTML 문자열에서 keyword가 등장하는 위치 주변에서
    <a href="https://..."> 형태의 URL 중
    keyword와의 문자 거리(absolute offset difference)가 가장 가까운 것들을
    최대 max_links 개까지 반환한다.
    """
    candidates = []  # (distance, href) 목록

    start = 0
    html_len = len(html)

    while True:
        idx = html.find(keyword, start)
        if idx == -1:
            break

        # 키워드 기준 앞뒤로 일정 구간만 잘라서 URL 검색
        window_start = max(0, idx - URL_SEARCH_WINDOW)
        window_end = min(html_len, idx + len(keyword) + URL_SEARCH_WINDOW)
        window = html[window_start:window_end]

        # 키워드의 window 내 상대 위치
        keyword_pos_in_window = idx - window_start

        soup = BeautifulSoup(window, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            # 절대 URL이면서 https:// 로 시작하는 경우만 사용
            if not href.startswith("https://"):
                continue

            a_str = str(a)
            pos_in_window = window.find(a_str)
            if pos_in_window == -1:
                # 파서가 문자열을 약간 변경했을 수 있으므로, 실패 시 건너뜀
                continue

            a_center = pos_in_window + len(a_str) // 2
            distance = abs(a_center - keyword_pos_in_window)

            candidates.append((distance, href))

        start = idx + len(keyword)

    if not candidates:
        return []

    # 거리 기준 정렬 후, href 기준으로 중복 제거하면서 상위 max_links 개 추출
    candidates.sort(key=lambda x: x[0])

    selected = []
    seen = set()
    for dist, href in candidates:
        if href in seen:
            continue
        selected.append(href)
        seen.add(href)
        if len(selected) >= max_links:
            break

    return selected


def build_email_body(matches):
    """
    matches: { keyword: [url1, url2, ...], ... } 형태
    (각 키워드당 최대 2개 URL)
    """
    lines = []
    lines.append("[Hibrain 임용 알리미] 지정 키워드 신규 감지 결과\n")
    lines.append(f"대상 페이지: {HIBRAIN_URL}\n")

    for kw, urls in matches.items():
        lines.append(f"■ 키워드: {kw}")
        if urls:
            for i, u in enumerate(urls, start=1):
                lines.append(f"  - 가까운 링크 {i}: {u}")
        else:
            lines.append("  - (키워드 주변에서 https:// 링크를 찾지 못했습니다.)")
        lines.append("")  # 빈 줄

    return "\n".join(lines)


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


def main():
    keywords = load_keywords()
    print(f"로드된 키워드: {keywords}")

    html_pages = [fetch_page(u) for u in CONFIG_URLS]
    print("페이지 다운로드 완료")

    matches = {}  # { keyword: [url1, url2, ...] }

    for kw in keywords:
        urls = find_closest_urls_for_keyword(html, kw, max_links=MAX_LINKS)
        if urls:
            matches[kw] = urls

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
