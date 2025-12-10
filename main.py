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
# 로그 버퍼 & 헬퍼
# ---------------------------------------------------------

LOG_MESSAGES: list[str] = []
LAST_FORBIDDEN_INFO: dict | None = None  # 마지막 403 정보 저장용

def log(msg: str):
    """콘솔에 출력 + LOG_MESSAGES에 저장"""
    print(msg)
    LOG_MESSAGES.append(msg)

# ---------------------------------------------------------
# 공인 IP 조회
# ---------------------------------------------------------

def get_public_ip() -> str:
    """GitHub Actions 러너의 공인 IP 조회 (실패 시 '(조회 실패)' 반환)"""
    try:
        resp = requests.get("https://api.ipify.org", timeout=5)
        if resp.status_code == 200:
            return resp.text.strip()
        return f"(조회 실패: status={resp.status_code})"
    except Exception as e:
        log(f"[WARN] 공인 IP 조회 실패: {e}")
        return "(조회 실패)"

# ---------------------------------------------------------
# 워밍업 요청 (추가된 부분)
# ---------------------------------------------------------

def warmup_session(url: str) -> None:
    """
    같은 도메인의 루트 페이지를 한 번 찍어서
    쿠키/세션 확보를 시도한다.
    한 실행(run) 안에서는 한 번만 수행한다.
    """
    if getattr(SESSION, "_warmed_up", False):
        return

    try:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        log(f"[INFO] 워밍업 요청: {origin}")
        resp = SESSION.get(origin, timeout=10)
        log(f"[INFO] 워밍업 응답 코드: {resp.status_code}")
    except Exception as e:
        log(f"[WARN] 워밍업 요청 실패: {e}")
    finally:
        # 성공/실패와 관계없이 추가 워밍업은 하지 않도록 플래그 설정
        SESSION._warmed_up = True

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
    """주어진 URL에서 HTML을 가져온다. (403/429/503 재시도 + 워밍업 + 지수형 딜레이)"""
    global LAST_FORBIDDEN_INFO

    if not url:
        return None

    # 모바일 도메인으로 자동 전환
    parsed_for_domain = urlparse(url)
    if parsed_for_domain.netloc == "www.hibrain.net":
        mobile_url = url.replace("://www.", "://m.")
        log(f"[INFO] www.hibrain.net 대신 모바일 도메인으로 시도: {mobile_url}")
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

    # ★ 추가: 도메인 루트 워밍업 (실행당 1회)
    warmup_session(url)

    last_status: int | None = None

    # 재시도
    for attempt in range(1, max_retries + 1):
        # 시도할 때마다 딜레이를 조금씩 늘리는 지수형 + 랜덤 딜레이
        delay = random.uniform(1.0, 3.0) * attempt
        log(f"[INFO] {url} 요청 전 {delay:.2f}초 대기... (시도 {attempt}/{max_retries})")
        time.sleep(delay)

        try:
            resp = SESSION.get(url, timeout=15)
            last_status = resp.status_code
        except Exception as e:
            log(
                f"[ERROR] 요청 중 예외 발생: {url} ({e}) "
                f"(재시도 {attempt}/{max_retries})"
            )
            if attempt < max_retries:
                # 네트워크 예외 시에도 재시도
                continue
            return None

        # 정상 응답
        if resp.status_code == 200:
            resp.encoding = resp.apparent_encoding
            return resp.text

        # 403/429/503 → 접근 제한/과도한 요청/서비스 불가 → 재시도 후보
        if resp.status_code in (403, 429, 503):
            log(
                f"[WARN] 요청 실패: {url} (status={resp.status_code}), "
                f"재시도 {attempt}/{max_retries}"
            )
            # 마지막 시도 + 403이면 IP 차단 상황으로 기록
            if resp.status_code == 403 and attempt == max_retries:
                LAST_FORBIDDEN_INFO = {
                    "url": url,
                    "status": resp.status_code,
                }
            if attempt < max_retries:
                continue
            return None

        # 그 외 상태코드: 재시도해도 의미 없다고 보고 바로 종료
        log(f"[WARN] 요청 실패: {url} (status={resp.status_code})")
        return None

    log(f"[WARN] 재시도 후에도 HTML을 가져오지 못했습니다: {url} (마지막 status={last_status})")
    return None

# ---------------------------------------------------------
# HTML에서 키워드 링크와 모집기간 찾기
# ---------------------------------------------------------

def extract_period(a_tag: Tag) -> str:
    """
    주어진 <a> 태그를 포함하는 블록에서 모집 기간을 추출한다.
    - 모바일 구조 예시:
        <li class="banner ...">
          ...
          <div class="banner-information ...">
            <a class="banner-text-link" ...>
              <div class="date-text">25.12.01~내일마감</div>
              ...
    """
    # 우선 a_tag가 속한 최상위 <li>를 찾는다.
    li = a_tag.find_parent("li")
    if not li:
        return "(모집기간 정보 없음)"

    # 1) 모바일(hibrain m 사이트) 구조: .date-text 안에 기간이 들어있음
    date_div = li.find("div", class_="date-text")
    if date_div:
        text = date_div.get_text(strip=True)
        if text:
            # 예: "25.12.01~내일마감"
            return text

    # 2) 기존 PC 버전(또는 다른 구조) 대응: span.td_receipt 내부 숫자/특수기호 조합
    li_row = li if ("row" in li.get("class", []) and "sortRoot" in li.get("class", [])) else li.find_parent("li", class_="row sortRoot")
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
    ip = get_public_ip() 
    lines = []
    lines.append("[Hibrain 임용 알리미] 지정 키워드 신규 감지 결과\n")
    lines.append(f"- 깃허브 액션 IP주소: {ip}\n")
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

    log("이메일 발송 완료")

# ---------------------------------------------------------
# GitHub Issue 자동 생성 (추가된 부분)
# ---------------------------------------------------------

def create_github_issue(title: str, body: str):
    """
    크롤링 결과를 GitHub Issue로도 남긴다.
    - GITHUB_REPOSITORY: 'owner/repo' 형식 (GitHub Actions에서 기본 제공)
    - GITHUB_TOKEN: GitHub API 인증 토큰 (GitHub Actions의 GITHUB_TOKEN 사용 권장)
    """
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")

    if not repo or not token:
        log("[WARN] GITHUB_REPOSITORY 또는 GITHUB_TOKEN 이 설정되어 있지 않아 Issue를 생성하지 않습니다.")
        return

    api_url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    payload = {
        "title": title,
        "body": body,
    }

    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        log(f"[ERROR] GitHub Issue 생성 중 예외 발생: {e}")
        return

    if resp.status_code == 201:
        issue_url = resp.json().get("html_url")
        log(f"[INFO] GitHub Issue 생성 완료: {issue_url}")
    else:
        log(f"[WARN] GitHub Issue 생성 실패: status={resp.status_code}, body={resp.text}")

# ---------------------------------------------------------
# 메인 로직
# ---------------------------------------------------------

def main():
    keywords = load_keywords()
    log(f"로드된 키워드: {keywords}")

    html_pages = []

    for u in CONFIG_URLS:
        t = random.uniform(1.0, 3.0)
        log(f"[{u}] 접근 전 {t:.2f}초 대기...")
        time.sleep(t)

        html = fetch_page(u)
        if html:
            html_pages.append((u, html))
        else:
            log(f"[WARN] HTML을 가져오지 못함: {u}")

    # ✅ 모든 URL에서 HTML을 못 가져왔고, 마지막 상태가 403인 경우 → IP 차단 에러 메일/Issue
    if not html_pages:
        if LAST_FORBIDDEN_INFO and LAST_FORBIDDEN_INFO.get("status") == 403:
            ip = get_public_ip()
            logs = "\n".join(LOG_MESSAGES) if LOG_MESSAGES else "(로그 없음)"

            subject = "[Hibrain] 임용 공지 알리미 (서버측 IP차단으로 정보수집 실패)"
            body = (
                "Hibrain 서버측의 특정 IP 차단(403 에러)으로 인한 정보 수집 불가\n"
                f"- 깃허브 액션 IP주소: {ip}\n"
                "- 로그 메세지:\n"
                f"{logs}\n"
            )

            log("=== IP 차단 에러 발생: 이메일/Issue 전송 ===")
            send_email(subject, body)
            create_github_issue(subject, body)
        else:
            log("[WARN] 어떤 URL에서도 HTML을 가져오지 못했습니다. 이메일/Issue 발송 없음.")
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
        log("키워드 관련 링크 없음. 이메일/Issue 발송하지 않음.")
        return

    body = build_email_body(matches)
    subject = f"[Hibrain] 임용 공지 알리미 (최대 {MAX_LINKS}개 링크)"

    log("=== 이메일/Issue 미리보기 ===")
    log(f"Subject: {subject}")
    log(body)
    log("=======================")

    # 이메일 발송
    send_email(subject, body)

    # GitHub Issue 생성
    create_github_issue(subject, body)

if __name__ == "__main__":
    main()
