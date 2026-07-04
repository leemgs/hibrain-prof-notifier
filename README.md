# 📢 Hibrain 임용 공지 알리미

지정한 대학교 키워드가 **Hibrain(하이브레인)** 사이트에 신규로 등록되었는지 자동으로 감지하여
이메일로 알려주는 Python 기반 자동화 도구입니다.

GitHub Actions 또는 로컬 PC에서 실행할 수 있습니다.

---

## ✨ 기능 요약

* 🔍 **키워드 기반 신규 임용 공지 자동 검색**
* 🎓 **교수 임용(채용) 공고만 선별 수집** — 기업·연구원·Post-Doc·시간강사 등 비전임 공고는 자동 제외
* 🏷 **공고 제목·모집기간을 이메일에 함께 표시**
* 📡 **m.hibrain.net 모바일 페이지 기반 안정적 크롤링**
* 🛡 **403 방지를 위한 브라우저 UA·헤더·세션 자동 설정**
* 📅 **모집 기간 자동 추출**
  예: `25.12.01~내일마감`
* 📧 **이메일 자동 발송(Gmail SMTP)** — 가독성 높은 **HTML 카드 디자인** + 평문(plain text) 폴백을 함께 전송
* 🐙 **GitHub Issue 자동 생성** — 감지 결과를 Issue로도 기록 (주간 요약의 데이터 소스)
* ⚡ **GitHub Actions 스케줄링 지원**
* 📊 **주간 채용 현황 자동 집계 및 커밋** (저장소 Activity 유지)

---

## 📂 프로젝트 구조

```bash
.
├── main.py             # 메인 실행 파일 (크롤링 → HTML 이메일 발송 → Issue 생성)
├── weekly_summary.py   # 주간 채용 공지 현황 요약 스크립트
├── config.json         # 설정 파일 (User-Agent, 대상 URL, max_links)
├── keywords.txt        # 검색할 대학교 키워드 목록
├── requirements.txt    # 필요한 Python 패키지 (requests, beautifulsoup4)
├── data/
│   ├── email.json      # 이메일 전송 상세 설정 (SMTP 서버, 발신/수신인 등)
│   └── university_hiring_status.json # [자동 생성] 주간 교수 채용 현황 요약 데이터
├── .github/
│   └── workflows/
│       ├── hibrain-notifier.yml   # 일일 임용 공지 알림 워크플로우
│       └── weekly-summary.yml     # 주간 현황 집계 + 자동 커밋 워크플로우
└── README.md           # 프로젝트 설명
```

---

## 🔧 설치 및 실행 방법

### 1) 저장소 클론

```bash
git clone https://github.com/leemgs/hibrain-prof-notifier.git
cd hibrain-prof-notifier
```

### 2) Python 패키지 설치

```bash
pip install -r requirements.txt
```

### 3) 이메일 설정 및 환경 변수 설정

이메일 발송 계정 및 수신인 등의 설정은 `./data/email.json` 파일에서 관리합니다. 보안을 필요로 하는 SMTP 비밀번호(`SMTP_PASS`)만 환경변수 또는 GitHub Secrets로 주입합니다.

#### 1. `./data/email.json` 파일 설정
기본 템플릿 파일이 제공되며, 상황에 맞게 편집하여 사용합니다. 수신인(`receivers`)은 배열 형식으로 여러 명을 지정할 수 있습니다.

```json
{
  "_comment": "receiver의 이메일 주소는 회사 이메일의 경우에 회사 방화벽에서 이메일의 수신자체를 막거나, 스팸함으로 분류되는 경우가 많습니다.",
  "smtp_host": "smtp.gmail.com",
  "smtp_port": 465,
  "smtp_user": "leemgs@gmail.com",
  "sender": "leemgs@gmail.com",
  "receivers": [
    "leemgs@gmail.com"
  ]
}
```

#### 2. 환경 변수 설정
이메일 비밀번호(앱 비밀번호)만 환경 변수로 지정합니다. (하위 호환성을 위해 `GMAIL_APP_PASSWORD`도 지원합니다.)

```bash
export SMTP_PASS="your_google_app_password"
```

> ❗ Gmail을 사용하는 경우, 2단계 인증 활성화 후 생성한 **앱 비밀번호**를 입력해야 합니다.

### 4) 실행

```bash
python main.py
```

---

## 📝 설정 파일(config.json)

```json
{
  "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.6647.44 Safari/537.36",
  "web_addresses": [
    "https://m.hibrain.net/recruitment/categories/ARAGP/categories/ARA01/recruits",
    "https://m.hibrain.net/recruitment/recruits?listType=RECOMM"
  ],
  "max_links": 2,
  "faculty_include_terms": ["교수", "교원", "초빙", "임용"],
  "faculty_exclude_terms": ["Post-Doc", "Postdoc", "Post Doc", "포닥", "박사후", "시간강사"]
}
```

| 옵션 | 설명 |
| --- | --- |
| `browser_user_agent` | 403 완화를 위한 브라우저 User-Agent |
| `web_addresses` | 크롤링 대상 Hibrain 모바일 목록 페이지 |
| `max_links` | 키워드(대학)당 수집할 최대 공고 링크 수 |
| `faculty_include_terms` | 공고 제목에 **하나 이상** 포함되어야 하는 교수 임용 신호어 |
| `faculty_exclude_terms` | 제목에 포함되면 **제외**할 단어 (비전임/연구직 등) |

> 🎓 **교수 임용 필터**: `recruits?listType=RECOMM` 페이지에는 대학 교수 공고뿐 아니라 기업·연구원 채용, Post-Doc, 시간강사 공고가 함께 노출됩니다. 위 두 옵션으로 **교수 임용(채용) 공고만** 걸러냅니다. (`faculty_include_terms` 중 하나 이상 포함 **AND** `faculty_exclude_terms`는 미포함)

---

## 🔍 키워드 파일(keywords.txt)

각 줄마다 한 개의 대학교 이름을 적습니다.

```
경희대학교
아주대학교
명지대학교
경기대학교
수원대학교
용인대학교
강남대학교
한신대학교
협성대학교
성결대학교
```

---

## 🛠 주요 기술 요소

### ● 1. 403 방지 로직 강화

* 모바일 도메인 자동 전환(`www → m.hibrain.net`)
* 실 브라우저와 동일한 수준의 HTTP 헤더 적용
* `Sec-Fetch-*`, `Origin`, `Referer` 자동 설정
* `requests.Session()` 재사용으로 서버 안정성 강화
* GitHub Actions의 실행 IP는 매 실행마다 달라질 수 있어 서버측에서 특정 대역 차단 시 어떤 코드도 403을 100% 방지할 수 없습니다. 만약 진짜 안정적인 실행 원하시면:
```bash
추천 해결책 순위
  * self-hosted runner 사용 (집 PC, NAS 등): → IP 고정 → 403 발생률 최저 수준
  * 실행 시간 변경: 예: 매일 일찍 새벽 → 트래픽 낮은 시간
  * 요청 횟수 줄임 (현재는 적절함)
```
### ● 2. 모집기간 추출 로직 개선

Hibrain 모바일 페이지 구조에 맞춘 자동 파싱:

```html
<div class="date-text">25.12.01~내일마감</div>
```

이 문자열을 그대로 추출하여 이메일 본문에 표시합니다.

### ● 3. 중복 공고 제거 및 링크 개수 제한

* 키워드당 최대 N개의 링크만 추출 (`max_links` 옵션)
* 두 목록 페이지(`ING`/`RECOMM`)에 동일 공고가 서로 다른 쿼리스트링으로 중복 노출되는 경우, 채용 고유번호(`/recruits/{id}`) 기준으로 **동일 공고를 하나로 합쳐** 이메일에 한 번만 표시합니다.

### ● 4. 교수 임용(채용) 공고 선별 필터

키워드(대학명)가 제목에 포함되더라도, 공고 제목이 **교수 임용 공고**일 때만 수집합니다.

* `faculty_include_terms`(예: `교수`, `교원`, `초빙`, `임용`) 중 하나 이상 포함
* **AND** `faculty_exclude_terms`(예: `Post-Doc`, `박사후`, `시간강사`)는 미포함

이를 통해 추천 피드(`listType=RECOMM`)에 섞여 들어오는 기업 채용·연구원 채용·Post-Doc·시간강사 공고를 자동으로 걸러냅니다. 또한 수집한 **공고 제목**을 이메일 본문(HTML/평문)에 함께 표시하여 가독성을 높였습니다.

---

## 📧 이메일 예시

이메일은 **HTML 카드 디자인**으로 발송되며, HTML을 지원하지 않는 클라이언트를 위해 아래와 같은 **평문(plain text) 폴백**이 함께 전송됩니다(`multipart/alternative`).

* 상단 헤더: 감지된 대학 수 / 교수 임용 공고 건수 요약
* 대학별 카드: 학교명 · 공고 건수 배지 · **공고 제목(클릭 링크)** · 공고별 모집기간
* 푸터: GitHub Actions 실행 IP · 저장소 주소

평문 폴백 예시(공고 제목이 `[ ]` 안에 함께 표기됩니다):

```
[Hibrain 임용 알리미] 지정 키워드 신규 감지 결과

- 깃허브 액션 IP주소: 59.12.126.245

■ 키워드: 경희대학교 (모집기간: 26.06.29~26.07.09)
  - 관련 링크 1: [경희대학교 서울캠퍼스 2026학년도 2학기 교수 초빙 (추가)] https://m.hibrain.net/recruitment/...

■ 키워드: 성결대학교 (모집기간: 26.06.19~26.07.03)
  - 관련 링크 1: [성결대학교 2026학년도 2학기 전임교원 초빙] https://m.hibrain.net/recruitment/...

-----
GitHub Repo Address:
https://github.com/leemgs/hibrain-prof-notifier/
```

> 참고: GitHub Issue 본문에도 위 평문 형식이 그대로 기록되며, 이 형식을 주간 요약 스크립트(`weekly_summary.py`)가 파싱합니다.

---

## 🕒 GitHub Actions 자동 실행 설정

저장소에는 두 개의 워크플로우가 구성되어 있습니다.

### 1) 일일 알림 — `.github/workflows/hibrain-notifier.yml`

매일 KST 08:00(UTC 23:00)에 실행되어 신규 공지를 감지하고 이메일·Issue를 발송합니다.

```yaml
name: Hibrain 교수 임용 소식 알리미

on:
  schedule:
    # KST 08:00 실행 (UTC 23:00)
    - cron: "0 23 * * *"
  workflow_dispatch:  # 수동 실행용

permissions:
  contents: read
  issues: write       # Issue 생성 권한

jobs:
  check-hibrain:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python main.py
        env:
          SMTP_PASS: ${{ secrets.SMTP_PASS }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

> ⚠️ 필요한 시크릿: `SMTP_PASS`(Gmail 앱 비밀번호). `GITHUB_TOKEN`은 Actions가 자동 제공합니다.

### 2) 주간 요약 — `.github/workflows/weekly-summary.yml`

매주 토요일 KST 09:00(UTC 00:00)에 실행되어 직전 월~금 알림을 집계하고 `data/university_hiring_status.json`을 자동 커밋·푸시합니다. (자세한 내용은 아래 **「주간 채용 공지 현황 요약 및 자동 커밋」** 섹션 참조)

---

## 🧪 테스트 팁

1. 키워드를 실제 존재하는 대학교로 설정
2. `web_addresses`에 m.hibrain.net URL 사용
3. `print()` 로그로 파싱되는 기간·링크 확인
4. Gmail SMTP 오류가 있으면 앱 비밀번호 확인

---

## 📊 주간 채용 공지 현황 요약 및 자동 커밋 (Activity 유지)

GitHub Actions는 60일 동안 저장소에 커밋 등 코드 변화가 전혀 없으면 크론(Schedule) 실행이 자동으로 중단되는 정책이 있습니다. 이를 방지하고 매주 채용 현황을 요약하기 위해 다음이 구성되어 있습니다:

1. **주간 집계 스크립트 (`weekly_summary.py`)**: 
   * 매주 월~금요일 동안 깃허브 Issue에 등록된 알림 데이터들을 수집 및 파싱합니다.
   * 중복을 최신 정보 기준으로 필터링하여 대학교별 모집 기간 및 공지 링크 목록을 정리한 `data/university_hiring_status.json` 파일을 업데이트합니다.
2. **주간 자동 커밋 워크플로우 (`.github/workflows/weekly-summary.yml`)**:
   * 매주 토요일 오전 9시(KST)에 동작하여 위 요약 스크립트를 수행합니다.
   * `data/university_hiring_status.json` 파일에 변경이 생기면 자동으로 커밋 및 푸시하여 저장소를 활성화된 상태로 유지합니다.

---

## 📜 License

MIT License
자유롭게 수정·배포 가능합니다.

---
