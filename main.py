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
# 모집기간(date-text) 추출
# ---------------------------------------------------------

def _normalize_period_text(txt: str) -> str:
    """예: '25.11.27~25.12.12' -> '25.11.27 ~ 25.12.12'"""
    txt = txt.strip()
    if "~" in txt:
        left, right = txt.split("~", 1)
        return f"{left.strip()} ~ {right.strip()}"
    return txt

def extract_period_for_anchor(a) -> str | None:
    """
    공고 제목을 담고 있는 <a> 태그 기준으로,
    상위 노드에서 <div class="date-text">를 찾아 모집기간을 추출한다.
    """
    # 1) li.banner 안에 있을 확률이 가장 높음
    li = a.find_parent("li")
    if li is not None:
        dt = li.find("div", class_="date-text")
        if dt is not None:
            txt = dt.get_text(strip=True)
            if txt:
                return _normalize_period_text(txt)

    # 2) 혹시 다른 구조면, banner-information 쪽도 한 번 더 탐색
    info = a.find_parent("div", class_="banner-information")
    if info is not None:
        dt = info.find("div", class_="date-text")
        if dt is not None:
            txt = dt.get_text(strip=True)
            if txt:
                return _normalize_period_text(txt)

    r
