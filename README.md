# 📢 Hibrain 임용 공지 알리미

지정한 대학교 키워드가 **Hibrain(하이브레인)** 사이트에 신규로 등록되었는지 자동으로 감지하여
이메일로 알려주는 Python 기반 자동화 도구입니다.

GitHub Actions 또는 로컬 PC에서 실행할 수 있습니다.

---

## ✨ 기능 요약

* 🔍 **키워드 기반 신규 임용 공지 자동 검색**
* 📡 **m.hibrain.net 모바일 페이지 기반 안정적 크롤링**
* 🛡 **403 방지를 위한 브라우저 UA·헤더·세션 자동 설정**
* 📅 **모집 기간 자동 추출**
  예: `25.12.01~내일마감`
* 📧 **이메일 자동 발송(Gmail SMTP)**
* ⚡ **Github Actions 스케줄링 지원**

---

## 📂 프로젝트 구조

```bash
.
├── main.py             # 메인 실행 파일
├── weekly_summary.py   # 주간 채용 공지 현황 요약 스크립트
├── config.json         # 설정 파일 (User-Agent, 대상 URL 등)
├── keywords.txt        # 검색할 대학교 키워드 목록
├── requirements.txt    # 필요한 Python 패키지
├── data/
│   ├── email.json      # 이메일 전송 상세 설정 (SMTP 서버, 수신인 등)
│   └── university_hiring_status.json # [자동 생성] 주간 교수 채용 현황 요약 데이터
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
  "max_links": 2
}
```

---

## 🔍 키워드 파일(keywords.txt)

각 줄마다 한 개의 대학교 이름을 적습니다.

```
성결대학교
경희대학교
아주대학교
용인대학교
한신대학교
...
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

### ● 3. 중복 링크 제거 및 링크 개수 제한

키워드당 최대 N개의 링크만 추출 (`max_links` 옵션)

---

## 📧 이메일 예시

```
[Hibrain 임용 알리미] 지정 키워드 신규 감지 결과

■ 키워드: 건국대학교 (모집기간: 25.12.01~내일마감)
  - 관련 링크 1: https://m.hibrain.net/recruitment/...

-----
GitHub Repo Address:
https://github.com/leemgs/hibrain-prof-notifier/
```

---

## 🕒 GitHub Actions 자동 실행 설정 (예시)

`.github/workflows/hibrain-notifier.yml`

```yaml
name: Hibrain Notifier

on:
  schedule:
    # KST 기준: 08:00, 20:00 실행 (UTC 기준: 23:00, 11:00)
    - cron: "0 23 * * *"
  workflow_dispatch:

jobs:
  run:
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
```

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
