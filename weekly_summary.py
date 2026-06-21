#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import json
import requests
from datetime import datetime, timedelta, timezone

def log(msg: str):
    print(f"[WEEKLY-SUMMARY] {msg}")

def parse_utc_to_kst(utc_str: str) -> datetime:
    # GitHub API returns ISO 8601 strings like '2026-06-19T11:22:33Z'
    dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(timedelta(hours=9)))

def get_hiring_data_from_body(body: str) -> list:
    if not body:
        return []
    
    results = []
    # "■ 키워드:" 패턴으로 쪼갬
    parts = body.split("■ 키워드:")
    for part in parts[1:]:
        lines = part.strip().split("\n")
        if not lines:
            continue
        
        # 첫 줄: "대학명 (모집기간: 기간)"
        first_line = lines[0].strip()
        match = re.match(r"^(.*?)\s*\(모집기간:\s*(.*?)\)", first_line)
        if not match:
            continue
        
        univ = match.group(1).strip()
        period = match.group(2).strip()
        
        # 관련 링크 추출
        links = []
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            if "■ 키워드:" in line or "-----" in line:
                break
            
            link_match = re.search(r"https?://[^\s]+", line)
            if link_match:
                links.append(link_match.group(0))
        
        results.append({
            "university": univ,
            "period": period,
            "links": links
        })
    return results

def main():
    # 1. KST 기준 날짜 계산 (실행일 기준 직전 월~금 범위 산정)
    KST = timezone(timedelta(hours=9))
    now_kst = datetime.now(KST)
    
    # 토요일(5) 기준으로 직전 금요일(어제)과 월요일(5일 전) 구하기
    # 수동 실행 등 임의 요일 실행 시에도 견고하게 직전 월~금 주간을 산출
    weekday = now_kst.weekday()
    days_to_subtract_for_friday = (weekday - 4) % 7
    # 만약 오늘이 월~금(0~4) 평일이면 지난주의 완료된 주간을 대상 범위로 잡음
    if weekday in (0, 1, 2, 3, 4):
        days_to_subtract_for_friday += 7
        
    friday_date = now_kst - timedelta(days=days_to_subtract_for_friday)
    monday_date = friday_date - timedelta(days=4)
    
    start_dt = datetime(monday_date.year, monday_date.month, monday_date.day, 0, 0, 0, tzinfo=KST)
    end_dt = datetime(friday_date.year, friday_date.month, friday_date.day, 23, 59, 59, tzinfo=KST)
    
    log(f"실행 시간(KST): {now_kst.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"대상 기간(KST): {start_dt.strftime('%Y-%m-%d %H:%M:%S')} ~ {end_dt.strftime('%Y-%m-%d %H:%M:%S')}")

    # 2. GitHub API 설정
    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    
    if not repo:
        # 로컬 테스트용 폴백
        repo = "leemgs/hibrain-prof-notifier"
        log(f"[WARN] GITHUB_REPOSITORY 환경 변수가 없어 기본값 '{repo}'을 사용합니다.")
        
    api_url = f"https://api.github.com/repos/{repo}/issues"
    headers = {
        "Accept": "application/vnd.github+json"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    # 최근 100개 이슈 조회 (필요 시 state=all 로 닫힌 이슈도 포함하여 유실 방지)
    params = {
        "state": "all",
        "per_page": 100
    }
    
    try:
        resp = requests.get(api_url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        issues = resp.json()
    except Exception as e:
        log(f"[ERROR] GitHub Issues 조회 실패: {e}")
        return

    # 3. 대상 이슈 필터링 및 파싱
    aggregated_status = []
    
    for issue in issues:
        title = issue.get("title", "")
        # "[Hibrain] 임용 공지 알리미"로 시작하고 차단/실패가 아닌 이슈 필터
        if "[Hibrain]" in title and "임용 공지 알리미" in title:
            if "실패" in title or "차단" in title:
                continue
            
            created_at_utc = issue.get("created_at")
            if not created_at_utc:
                continue
                
            created_at_kst = parse_utc_to_kst(created_at_utc)
            
            # 대상 날짜 범위에 포함되는지 확인
            if start_dt <= created_at_kst <= end_dt:
                body = issue.get("body", "")
                hiring_items = get_hiring_data_from_body(body)
                
                for item in hiring_items:
                    # 중복 방지 및 최신화: 동일 대학교가 여러 번 탐지된 경우 최신 이슈 정보로 유지
                    # 혹은 모두 리스트로 모아두기. 여기서는 대학교별 최신 공지 우선 병합
                    existing = next((x for x in aggregated_status if x["university"] == item["university"]), None)
                    if existing:
                        # 이미 존재하는 경우, 탐지 일시가 더 최신인 데이터로 갱신
                        existing_dt = datetime.fromisoformat(existing["detected_at"])
                        if created_at_kst > existing_dt:
                            existing["period"] = item["period"]
                            existing["links"] = list(set(existing["links"] + item["links"]))
                            existing["detected_at"] = created_at_kst.isoformat()
                    else:
                        item["detected_at"] = created_at_kst.isoformat()
                        aggregated_status.append(item)

    # 대학교 이름 순으로 정렬
    aggregated_status.sort(key=lambda x: x["university"])

    # 4. 결과 JSON 파일 작성
    output_data = {
        "last_updated": now_kst.isoformat(),
        "date_range": f"{start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}",
        "total_universities": len(aggregated_status),
        "status_list": aggregated_status
    }
    
    # y:\github-leemgs\hibrain-prof-notifier\data 폴더가 존재하는지 확인 후 기록
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(base_dir, "data")
    os.makedirs(output_dir, exist_ok=True)
    
    output_file_path = os.path.join(output_dir, "university_hiring_status.json")
    
    with open(output_file_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
        
    log(f"주간 현황 파일 업데이트 완료: {output_file_path}")
    log(f"총 {len(aggregated_status)}개 대학교 채용 상태가 집계되었습니다.")

if __name__ == "__main__":
    main()
