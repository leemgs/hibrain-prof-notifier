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
├── config.json         # 설정 파일 (User-Agent, 대상 URL 등)
├── keywords.txt        # 검색할 대학교 키워드 목록
├── requirements.txt    # 필요한 Python 패키지
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

### 3) 환경 변수 설정

Gmail SMTP를 사용하므로 아래 3개를 반드시 설정해야 합니다.

```bash
export GMAIL_USER="your@gmail.com"
export GMAIL_APP_PASSWORD="your_google_app_password"
export TARGET_EMAIL="notify@yourdomain.com"
```

> ❗ Gmail에서는 앱 비밀번호(App Password)가 필요합니다.
> 2단계 인증 활성화 후 발급하세요.

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

`.github/workflows/notify.yml`

```yaml
name: Hibrain Notifier

on:
  schedule:
    - cron: "0 */4 * * *"
  workflow_dispatch:

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: 3.11
      - run: pip install -r requirements.txt
      - run: python main.py
        env:
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          TARGET_EMAIL: ${{ secrets.TARGET_EMAIL }}
```

---

## 🧪 테스트 팁

1. 키워드를 실제 존재하는 대학교로 설정
2. `web_addresses`에 m.hibrain.net URL 사용
3. `print()` 로그로 파싱되는 기간·링크 확인
4. Gmail SMTP 오류가 있으면 앱 비밀번호 확인

---

## 📜 License

MIT License
자유롭게 수정·배포 가능합니다.

---
