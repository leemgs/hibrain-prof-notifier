#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
교수 임용 공고 제목 필터(is_faculty_posting) 회귀 테스트.

목적:
    "산학 교수" 채용(산학협력중점교수/산학중점교수/산학협력교수/겸임교수(산학) 등)이
    이메일 알림에 정상적으로 포함되는지 고정(regression)한다.
    동시에 교수가 아닌 산학 공고(산학장학생/산학협력단 직원)는 제외되는지 확인한다.

실행:
    python test_faculty_filter.py
    (의존성: main.py 가 import 가능해야 함 → requirements.txt 설치 필요)
"""

import sys

from main import is_faculty_posting

# (제목, 기대값)  기대값 True = 수집(이메일 발송 대상), False = 제외
CASES = [
    # ── 기존 전임교원 케이스 (대조군) ──────────────────────────
    ("아주대학교 2027학년도 1학기 전임교원 초빙", True),
    ("명지대학교 2027-1학기 전임교원 초빙", True),
    # ── 산학 교수 → 반드시 포함되어야 함 ──────────────────────
    ("경희대학교 2027학년도 산학협력중점교수 초빙", True),
    ("명지대학교 산학중점교수 채용", True),
    ("아주대학교 산학협력교수 모집", True),
    ("경기대학교 2027-1학기 산학협력중점교수(비전임) 공고", True),
    ("수원대학교 겸임교수(산학) 채용", True),
    ("강남대학교 산학협력중점교원 초빙", True),
    ("성결대학교 산학협력중점 교수 임용", True),
    ("협성대학교 산학협력중점교수(계약직) 채용공고", True),
    # 실제 Hibrain 목록에서 관측된 산학 교수 공고 형태
    ("UNIST 인공지능대학원 산학협력중점교수(비전임) 채용 (근무지: 부산)", True),
    ("국립부경대학교 2027학년도 전기 전임교원 초빙 (일반 전임교원/산학협력중점교수)", True),
    # ── 산학이지만 교수가 아닌 공고 → 제외되어야 함 ───────────
    ("용인대학교 산학협력단 행정직원 채용", False),
    ("롯데케미칼 2026년 10월 첨단소재사업 신입 박사 / 산학장학생 채용", False),
    # ── 비전임/제외 직군 (대조군) ─────────────────────────────
    ("한신대학교 산학협력 Post-Doc 연구원 모집", False),
    ("ㅇㅇ대학교 시간강사 위촉 공고", False),
]


def main() -> int:
    failures = []
    for title, expected in CASES:
        actual = is_faculty_posting(title)
        status = "OK " if actual == expected else "FAIL"
        if actual != expected:
            failures.append((title, expected, actual))
        print(f"  [{status}] expected={expected!s:5} actual={actual!s:5}  {title}")

    print()
    if failures:
        print(f"❌ {len(failures)}개 케이스 실패:")
        for title, exp, act in failures:
            print(f"   - {title}  (기대 {exp}, 실제 {act})")
        return 1

    print(f"✅ 전체 {len(CASES)}개 케이스 통과 — 산학 교수 공고 정상 포함 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
