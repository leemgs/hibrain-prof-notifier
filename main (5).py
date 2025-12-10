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

def load_config(path: str = "config.json") -> dict:
    """
    config.json을 읽어 환경설정 딕셔너리를 반환.
    기본 구조 예시는 README 참조.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

CONFIG = load_config()

# ---------------------------------------------------------
# 공통 상수
# ---------------------------------------------------------

HIBRAIN_LIST_URL = "https://m.hibrain.net/recruitment/categories/ARAGP/categories/ARA01/recruits"

# GitHub 관련
GITHUB_API_URL = "https://api.github.com"

# ---------------------------------------------------------
# 로깅 유틸
# ---------------------------------------------------------

LOG_MESSAGES = []

def log(msg: str):
    """단순 콘솔 + 메모리 로깅."""
    print(msg)
    LOG_MESSAGES.append(msg)

# ---------------------------------------------------------
# Public IP 조회
# ---------------------------------------------------------

def get_public_ip() -> str:
    """
    GitHub Actions 런너의 퍼블릭 IP를 조회한다.
    여러 서비스를 시도해서, 실패하면 'Unknown'을 리턴한다.
    """
    services = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://checkip.amazonaws.com",
    ]
    for url in services:
        try:
            resp = requests.get(url, timeout=5)
            if resp.ok:
                ip = resp.text.strip()
                # 간단한 검증
                if ip and len(ip) < 64:
                    return ip
        except Exception:
            continue
    return "Unknown"

# ---------------------------------------------------------
# HTML 요청 + 파싱
# ---------------------------------------------------------

def fetch_html_with_retry(url: str, max_retries: int = 3, backoff_min: float = 1.0, backoff_max: float = 2.0) -> str:
    """
    지정 URL에 대해 여러 번 재시도하며 HTML을 가져온다.
    403 에러 등 예외 상황을 상위에서 처리할 수 있도록 raise 한다.
    """
    headers = {
        "User-Agent": CONFIG.get("user_agent", "Mozilla/5.0 (compatible; HibrainBot/1.0)"),
    }

    for attempt in range(1, max_retries + 1):
        # 랜덤 대기 (백오프)
        sleep_sec = random.uniform(backoff_min, backoff_max)
        log(f"[INFO] {url} 요청 전 {sleep_sec:.2f}초 대기... (시도 {attempt}/{max_retries})")
        time.sleep(sleep_sec)

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            log(f"[INFO] 응답 코드: {resp.status_code} (시도 {attempt}/{max_retries})")

            # 403 등 에러 상황은 바로 예외 발생
            if resp.status_code == 403:
                raise PermissionError("403 Forbidden (IP 차단 가능성)")
            resp.raise_for_status()
            return resp.text

        except PermissionError:
            # 403은 즉시 상위로 전달
            raise
        except Exception as e:
            log(f"[WARN] 요청 실패: {url} (사유: {e}), 재시도 {attempt}/{max_retries}")
            if attempt == max_retries:
                raise

    # 논리상 도달 불가이지만 안전하게 예외
    raise RuntimeError("fetch_html_with_retry: 재시도 끝에 실패")

def parse_html_for_keywords(html: str, base_url: str, keywords: list[str]) -> dict:
    """
    HTML에서 키워드가 들어 있는 a 태그 주변의 링크 목록을 추출한다.
    반환 형태:
        {
          "키워드1": [(url1, "모집기간.."), (url2, "모집기간.."), ...],
          "키워드2": [...],
        }
    """
    soup = BeautifulSoup(html, "html.parser")
    keyword_matches: dict[str, list[tuple[str, str]]] = {kw: [] for kw in keywords}

    # 예시: 모집기간이 들어있는 span, div 등을 찾는다면 아래 로직을 커스터마이징
    # 여기서는 단순히 a 태그를 전부 순회하며, 텍스트에 키워드가 있는지 확인
    for a_tag in soup.find_all("a"):
        if not isinstance(a_tag, Tag):
            continue
        text = (a_tag.get_text() or "").strip()
        href = (a_tag.get("href") or "").strip()
        if not href:
            continue

        abs_url = urljoin(base_url, href)

        # 주변에 "모집기간" 문구가 들어간 텍스트를 heuristic하게 찾는 예시
        period_text = ""
        parent = a_tag.parent
        if parent:
            parent_text = parent.get_text(separator=" ", strip=True) if isinstance(parent, Tag) else ""
            if "모집기간" in parent_text:
                period_text = parent_text

        # 각 키워드에 대해 검사
        for kw in keywords:
            if kw in text:
                keyword_matches[kw].append((abs_url, period_text))

    # 빈 리스트(매치가 전혀 없는 키워드)는 그대로 둘 수 있음
    return keyword_matches

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

    # 깃허브 액션 퍼블릭 IP 주소도 함께 표기
    ip = get_public_ip()
    lines.append(f"- 깃허브 액션 IP주소: {ip}")

    lines.append("GitHub Repo Address:")
    lines.append("https://github.com/leemgs/hibrain-prof-notifier/")

    return "\n".join(lines)

# ---------------------------------------------------------
# 이메일 발송
# ---------------------------------------------------------

def send_email(subject: str, body: str):
    """
    SMTP를 이용해 이메일 발송.
    config.json의 email 설정 값을 사용.
    """
    email_conf = CONFIG.get("email", {})
    smtp_host = email_conf.get("smtp_host")
    smtp_port = email_conf.get("smtp_port", 587)
    smtp_user = email_conf.get("smtp_user")
    smtp_pass = email_conf.get("smtp_pass")
    from_addr = email_conf.get("from_addr")
    to_addrs = email_conf.get("to_addrs", [])

    if not (smtp_host and smtp_user and smtp_pass and from_addr and to_addrs):
        log("[WARN] 이메일 설정이 충분하지 않아 메일을 발송하지 않습니다.")
        return

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, to_addrs, msg.as_string())
        log("[INFO] 이메일 발송 성공")
    except Exception as e:
        log(f"[ERROR] 이메일 발송 실패: {e}")

# ---------------------------------------------------------
# GitHub Issue 생성
# ---------------------------------------------------------

def create_github_issue(title: str, body: str):
    """
    GitHub REST API를 사용해 Issue를 생성.
    """
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")

    if not (repo and token):
        log("[WARN] GITHUB_REPOSITORY 또는 GITHUB_TOKEN이 설정되지 않아 Issue를 생성하지 않습니다.")
        return

    url = f"{GITHUB_API_URL}/repos/{repo}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }
    data = {
        "title": title,
        "body": body,
    }

    try:
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        if resp.status_code in (200, 201):
            log("[INFO] GitHub Issue 생성 성공")
        else:
            log(f"[ERROR] GitHub Issue 생성 실패: status={resp.status_code}, body={resp.text}")
    except Exception as e:
        log(f"[ERROR] GitHub Issue 생성 중 예외 발생: {e}")

# ---------------------------------------------------------
# 메인 로직
# ---------------------------------------------------------

def main():
    # 1) 기본 키워드 로딩
    keywords = CONFIG.get("keywords", [])
    if not keywords:
        log("[WARN] config.json에 keywords가 비어있습니다. 기본 키워드를 사용하지 않습니다.")

    log(f"로드된 키워드: {keywords}")

    # 2) Hibrain 서버 워밍업 시도 (선택적)
    try:
        warmup_url = "https://m.hibrain.net"
        log(f"[https://m.hibrain.net] 접근 전 1.82초 대기...")
        time.sleep(1.82)
        warmup_resp = requests.get(warmup_url, timeout=5)
        log(f"[INFO] 워밍업 응답 코드: {warmup_resp.status_code}")
    except Exception as e:
        log(f"[WARN] 워밍업 요청 중 예외 발생: {e}")

    # 3) 실제 목록 페이지 HTML 가져오기
    try:
        html = fetch_html_with_retry(HIBRAIN_LIST_URL)
    except PermissionError as e:
        # 403 Forbidden 등 -> IP 차단 가능성
        log(f"[ERROR] Hibrain 페이지 접근 실패 (403 등). 사유: {e}")

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
        return

    except Exception as e:
        # 그 외 네트워크 예외
        log(f"[ERROR] Hibrain 페이지 접근 중 알 수 없는 오류: {e}")
        ip = get_public_ip()
        logs = "\n".join(LOG_MESSAGES) if LOG_MESSAGES else "(로그 없음)"

        subject = "[Hibrain] 임용 공지 알리미 (Hibrain 페이지 접근 오류)"
        body = (
            "Hibrain 페이지 접근 중 오류가 발생했습니다.\n"
            f"- 깃허브 액션 IP주소: {ip}\n"
            "- 로그 메세지:\n"
            f"{logs}\n"
        )

        send_email(subject, body)
        create_github_issue(subject, body)
        return

    # 4) HTML 파싱해서 키워드 매칭
    matches = parse_html_for_keywords(html, HIBRAIN_LIST_URL, keywords)

    # 실제로 매칭된 것이 있는지 확인
    has_any_match = any(v for v in matches.values())
    if not has_any_match:
        log("[INFO] 금번 실행에서는 신규 매칭된 키워드가 없습니다.")
        return

    # 5) 알림 이메일/Issue 내용 생성
    body = build_email_body(matches)
    subject_prefix = CONFIG.get("email", {}).get("subject_prefix", "[Hibrain] ")
    subject = subject_prefix + "임용 공지 신규 매칭 결과"

    # 디버그용 출력
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
