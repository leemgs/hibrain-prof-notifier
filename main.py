#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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

# 교수 임용(채용) 공고만 수집하기 위한 제목 필터
#  - include: 제목에 아래 단어 중 하나 이상이 있어야 함 (교수/교원 채용 신호)
#  - exclude: 아래 단어가 제목에 있으면 교수 임용이 아니라고 보고 제외
#    (Post-Doc/박사후연구원, 시간강사 등 비전임 직군)
FACULTY_INCLUDE_TERMS = CONFIG.get("faculty_include_terms") or ["교수", "교원", "초빙", "임용"]
FACULTY_EXCLUDE_TERMS = CONFIG.get("faculty_exclude_terms") or [
    "Post-Doc", "Postdoc", "Post Doc", "포닥", "박사후", "시간강사",
]


def is_faculty_posting(title: str) -> bool:
    """공고 제목이 '교수 임용(채용)' 공고인지 판별한다.

    include 단어 중 하나 이상을 포함하면서 exclude 단어는 포함하지 않아야 한다.
    """
    if not title:
        return False
    low = title.lower()
    if any(ex.lower() in low for ex in FACULTY_EXCLUDE_TERMS):
        return False
    return any(inc.lower() in low for inc in FACULTY_INCLUDE_TERMS)

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
    """HTML 본문에서 키워드가 포함된 '교수 임용(채용)' 공고 링크를 찾는다.

    반환값: (절대 URL, 모집기간, 공고 제목) 튜플의 리스트.
    키워드(대학명)가 제목에 포함되면서, 동시에 교수 임용 공고로 판별된
    (is_faculty_posting) 링크만 수집한다. → 기업/연구원/Post-Doc/시간강사 등
    비전임 공고는 제외된다.
    """
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

        if keyword not in text:
            continue

        # ★ 교수 임용(채용) 공고만 수집 (그 외 직군/광고성 링크 제외)
        if not is_faculty_posting(text):
            log(f"[SKIP] 교수 임용 공고 아님으로 제외: {text[:60]}")
            continue

        if href_abs not in seen_urls:
            period = extract_period(a)
            results.append((href_abs, period, text))
            seen_urls.add(href_abs)
            if len(results) >= max_links:
                break

    return results

# ---------------------------------------------------------
# 이메일 본문 생성
# ---------------------------------------------------------

REPO_URL = "https://github.com/leemgs/hibrain-prof-notifier/"


def build_email_body(matches: dict, ip: str | None = None):
    """matches 딕셔너리를 기반으로 평문(plain text) 이메일 본문을 생성한다."""
    if ip is None:
        ip = get_public_ip()
    lines = []
    lines.append("[Hibrain 임용 알리미] 지정 키워드 신규 감지 결과\n")
    lines.append(f"- 깃허브 액션 IP주소: {ip}\n")
    for kw, link_periods in matches.items():
        period_info = link_periods[0][1] if link_periods else "(모집기간 정보 없음)"
        lines.append(f"■ 키워드: {kw} (모집기간: {period_info})")

        if link_periods:
            for i, (u, _period, title) in enumerate(link_periods, start=1):
                if title:
                    lines.append(f"  - 관련 링크 {i}: [{title}] {u}")
                else:
                    lines.append(f"  - 관련 링크 {i}: {u}")
        else:
            lines.append("  - (교수 임용 공고 링크 없음)")
        lines.append("")

    lines.append("-----")
    lines.append("GitHub Repo Address:")
    lines.append(REPO_URL)

    return "\n".join(lines)


def _esc(text: str) -> str:
    """HTML 특수문자 이스케이프."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_email_html(matches: dict, ip: str | None = None):
    """matches 딕셔너리를 기반으로 가독성 높은 HTML 이메일 본문을 생성한다.

    이메일 클라이언트(Gmail 등) 호환성을 위해 모든 스타일은 인라인으로 작성한다.
    """
    if ip is None:
        ip = get_public_ip()

    total_kw = len(matches)
    total_links = sum(len(v) for v in matches.values())

    # 카드 색상 팔레트 (키워드별로 순환)
    accents = ["#2563eb", "#0891b2", "#7c3aed", "#db2777", "#ea580c", "#16a34a"]

    cards = []
    for idx, (kw, link_periods) in enumerate(matches.items()):
        accent = accents[idx % len(accents)]
        count = len(link_periods)

        link_rows = []
        if link_periods:
            for i, (u, period, title) in enumerate(link_periods, start=1):
                title_html = _esc(title) if title else "공고 바로가기"
                period_html = (
                    f'<span style="color:#64748b;font-size:12px;margin-left:32px;">🗓 {_esc(period)}</span>'
                    if period and period != "(모집기간 정보 없음)" else ""
                )
                link_rows.append(
                    f'''
                    <tr>
                      <td style="padding:8px 0;vertical-align:top;">
                        <span style="display:inline-block;min-width:22px;height:22px;line-height:22px;text-align:center;
                                     background:{accent};color:#ffffff;border-radius:11px;font-size:12px;font-weight:700;
                                     margin-right:10px;">{i}</span>
                        <a href="{_esc(u)}" target="_blank"
                           style="color:{accent};text-decoration:none;font-size:15px;word-break:break-word;font-weight:700;">
                           {title_html} →
                        </a>
                        {period_html}
                        <div style="color:#94a3b8;font-size:11px;margin:3px 0 0 32px;word-break:break-all;">{_esc(u)}</div>
                      </td>
                    </tr>'''
                )
        else:
            link_rows.append(
                '<tr><td style="padding:6px 0;color:#94a3b8;font-size:14px;">교수 임용 공고 링크 없음</td></tr>'
            )

        cards.append(
            f'''
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                   style="margin:0 0 16px 0;border:1px solid #e2e8f0;border-left:4px solid {accent};
                          border-radius:10px;background:#ffffff;">
              <tr>
                <td style="padding:18px 20px;">
                  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="font-size:18px;font-weight:800;color:#0f172a;">🎓 {_esc(kw)}</td>
                      <td align="right" style="white-space:nowrap;">
                        <span style="display:inline-block;background:#f1f5f9;color:#475569;font-size:12px;font-weight:600;
                                     padding:5px 12px;border-radius:20px;">교수 임용 공고 {count}건</span>
                      </td>
                    </tr>
                  </table>
                  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:10px;">
                    {''.join(link_rows)}
                  </table>
                </td>
              </tr>
            </table>'''
        )

    html = f'''<!DOCTYPE html>
<html lang="ko">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f1f5f9;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Apple SD Gothic Neo','Malgun Gothic',sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0"
               style="max-width:600px;width:100%;">

          <!-- 헤더 -->
          <tr>
            <td style="background:linear-gradient(135deg,#1e3a8a 0%,#2563eb 100%);
                       border-radius:12px 12px 0 0;padding:28px 28px 24px 28px;">
              <div style="color:#bfdbfe;font-size:13px;font-weight:600;letter-spacing:1px;">HIBRAIN · 교수 임용 알리미</div>
              <div style="color:#ffffff;font-size:24px;font-weight:800;margin-top:6px;">교수 임용 공고 신규 감지 🔔</div>
              <div style="color:#dbeafe;font-size:14px;margin-top:8px;">
                대학교 <b style="color:#ffffff;">{total_kw}</b>곳 · 교수 임용 공고 <b style="color:#ffffff;">{total_links}</b>건이 새로 감지되었습니다.
              </div>
            </td>
          </tr>

          <!-- 본문 -->
          <tr>
            <td style="background:#f8fafc;padding:22px 22px 6px 22px;">
              {''.join(cards)}
            </td>
          </tr>

          <!-- 푸터 -->
          <tr>
            <td style="background:#f8fafc;border-radius:0 0 12px 12px;padding:12px 22px 24px 22px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                     style="border-top:1px solid #e2e8f0;padding-top:16px;">
                <tr>
                  <td style="color:#94a3b8;font-size:12px;line-height:1.7;">
                    🌐 GitHub Actions IP: <span style="color:#475569;font-weight:600;">{_esc(ip)}</span><br>
                    📦 Repository:
                    <a href="{REPO_URL}" target="_blank" style="color:#2563eb;text-decoration:none;">{REPO_URL}</a><br>
                    <span style="color:#cbd5e1;">본 메일은 자동 발송되었습니다 · Self-hosted</span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>'''
    return html

# ---------------------------------------------------------
# 이메일 발송
# ---------------------------------------------------------

def send_email(subject: str, body: str, html_body: str | None = None):
    # 1. 기본값 설정 및 email.json 로드
    base_dir = os.path.dirname(os.path.abspath(__file__))
    email_json_path = os.path.join(base_dir, "data", "email.json")
    
    smtp_host = "smtp.gmail.com"
    smtp_port = 465
    smtp_user = None
    sender = None
    receivers = []
    
    if os.path.exists(email_json_path):
        try:
            with open(email_json_path, "r", encoding="utf-8") as f:
                email_cfg = json.load(f)
                smtp_host = email_cfg.get("smtp_host", smtp_host)
                smtp_port = int(email_cfg.get("smtp_port", smtp_port))
                smtp_user = email_cfg.get("smtp_user")
                sender = email_cfg.get("sender", smtp_user)
                
                recv_val = email_cfg.get("receivers", [])
                if isinstance(recv_val, list):
                    receivers = recv_val
                elif isinstance(recv_val, str):
                    receivers = [recv_val]
        except Exception as e:
            log(f"[WARN] 이메일 설정 파일(email.json) 파싱 실패: {e}")

    # 2. 환경변수 오버라이드 및 폴백 지원
    env_smtp_user = os.environ.get("GMAIL_USER")
    env_target_email = os.environ.get("TARGET_EMAIL")
    smtp_pass = os.environ.get("SMTP_PASS") or os.environ.get("GMAIL_APP_PASSWORD")
    
    if env_smtp_user:
        smtp_user = env_smtp_user
        sender = env_smtp_user
    if env_target_email:
        receivers = [env_target_email]

    # 유효성 검증
    if not smtp_pass:
        raise RuntimeError("SMTP_PASS (또는 GMAIL_APP_PASSWORD) 환경변수를 설정해야 합니다.")
    if not smtp_user:
        raise RuntimeError("SMTP 사용자 계정(smtp_user)이 지정되지 않았습니다.")
    if not receivers:
        raise RuntimeError("수신자 이메일(receivers)이 지정되지 않았습니다.")

    to_addrs = [r.strip() for r in receivers if r.strip()]

    if html_body:
        # 평문 + HTML 멀티파트 (HTML 미지원 클라이언트는 평문 표시)
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain", _charset="utf-8"))
        msg.attach(MIMEText(html_body, "html", _charset="utf-8"))
    else:
        msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to_addrs)

    log(f"[INFO] 이메일 발송 시도... Host: {smtp_host}, Port: {smtp_port}, User: {smtp_user}, To: {to_addrs}")

    if smtp_port == 465:
        # SSL 발송
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=20) as smtp:
            smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg)
    else:
        # STARTTLS 발송 (예: 587)
        import ssl
        ctx = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls(context=ctx)
            smtp.login(smtp_user, smtp_pass)
            smtp.sendmail(sender, to_addrs, msg.as_string())

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
            for url, period, title in found:
                if url not in seen:
                    unique.append((url, period, title))
                    seen.add(url)
                    if len(unique) >= MAX_LINKS:
                        break
            if unique:
                matches[kw] = unique

    if not matches:
        log("키워드 관련 링크 없음. 이메일/Issue 발송하지 않음.")
        return

    ip = get_public_ip()
    body = build_email_body(matches, ip)
    html_body = build_email_html(matches, ip)
    subject = f"[Hibrain] 임용 공지 알리미 (최대 {MAX_LINKS}개 링크, Self-hosted)"

    log("=== 이메일/Issue 미리보기 ===")
    log(f"Subject: {subject}")
    log(body)
    log("=======================")

    # 이메일 발송 (HTML + 평문 멀티파트)
    send_email(subject, body, html_body=html_body)

    # GitHub Issue 생성
    create_github_issue(subject, body)

if __name__ == "__main__":
    main()
