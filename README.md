# Hibrain 교수 임용 소식 알리미 (GitHub Actions + Gmail)

지정한 대학교 이름(키워드)이 **Hibrain 채용 페이지**에 등장하면,  
키워드 주변의 HTML을 분석해서 **해당 키워드와 가장 가까운 `<a href="https://...">` 링크 최대 2개**를 골라  
이를 **Gmail로 알림 메일**로 보내는 GitHub Actions용 레포입니다.

- 대상 페이지: https://m.hibrain.net/recruitment
- 실행 주기: ** x시간마다 자동 실행** (GitHub Actions cron)
- 알림 방식: Gmail SMTP를 이용해 메일 발송
- 링크 추출: HTML을 BeautifulSoup으로 파싱하고,  
  각 키워드에 대해 **문자 거리 기준으로 가장 가까운 링크 2개까지 선택**

---

## 1. 레포 구조

```text
hibrain-prof-notifier/
├─ main.py                 # 크롤링 + 키워드 검색 + 링크 추출 + 이메일 발송
├─ keywords.txt            # 검색할 대학교 키워드 목록 (UTF-8)
├─ requirements.txt        # Python 패키지 목록
└─ .github/
   └─ workflows/
      └─ hibrain-notifier.yml   # 4시간마다 실행되는 GitHub Actions 워크플로
```

---

## 2. 설치 및 로컬 테스트

### 2-1. 사전 준비

1. Python 3.10+ 설치
2. Gmail 계정 + 앱 비밀번호(App Password) 준비  
   - Google 계정 보안 설정에서 **2단계 인증**을 켠 뒤,  
     *앱 비밀번호*를 발급받아 사용해야 합니다. (일반 계정 비밀번호 X)

### 2-2. 의존성 설치

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2-3. 환경변수 설정 후 실행

```bash
export GMAIL_USER="yourname@gmail.com"
export GMAIL_APP_PASSWORD="발급받은_앱_비밀번호"
export TARGET_EMAIL="알림을_받을_메일주소"

python main.py
```

- 지정한 키워드가 Hibrain 페이지에 존재하고,  
  키워드 주변의 HTML에서 `<a href="https://...">` 링크가 발견되면  
  → **키워드마다 가장 가까운 링크 최대 2개를 골라 이메일로 발송**합니다.
- 아무 키워드도 발견되지 않으면  
  → 이메일을 보내지 않고 종료합니다.

---

## 3. 키워드 설정 (`keywords.txt`)

루트 디렉토리에 `keywords.txt` 파일을 만들고, 줄마다 하나씩 키워드를 작성합니다.

예시:

```text
성결대학교
수원대학교
경희대학교
용인대학교
협성대학교
```

- 인코딩은 **UTF-8**을 권장합니다.
- 줄 앞/뒤 공백은 자동으로 제거됩니다.

---

## 4. GitHub Actions 설정

`.github/workflows/hibrain-notifier.yml` 파일에는 다음과 같은 워크플로가 정의되어 있습니다.

### 4-1. 스케줄 (4시간마다 실행)

```yaml
on:
  schedule:
    # 4시간마다 실행 (UTC 기준, 매일 0시/4시/8시/12시/16시/20시)
    - cron: "0 */4 * * *"
  workflow_dispatch:  # 수동 실행용
```

- GitHub Actions는 **UTC 기준**으로 동작합니다.
- 한국 시간(KST, UTC+9) 기준으로는  
  대략 **09시, 13시, 17시, 21시, 01시, 05시** 쯤에 실행된다고 보면 됩니다.

### 4-2. GitHub Secrets 설정

레포 화면에서:

1. **Settings → Secrets and variables → Actions → New repository secret**
2. 아래 세 가지를 추가합니다.

- `GMAIL_USER`  
  - 예: `yourname@gmail.com`
- `GMAIL_APP_PASSWORD`  
  - Google 계정에서 발급받은 **앱 비밀번호**
- `TARGET_EMAIL`  
  - 알림을 받을 이메일 주소

워크플로에서는 다음과 같이 사용합니다.

```yaml
env:
  GMAIL_USER: ${{ secrets.GMAIL_USER }}
  GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
  TARGET_EMAIL: ${{ secrets.TARGET_EMAIL }}
```

---

## 5. 동작 방식 상세 (키워드와 가장 가까운 `<a>` 최대 2개 선택)

1. `keywords.txt`에서 **대학교명 키워드** 목록을 읽습니다.
2. `https://m.hibrain.net/recruitment` 페이지 HTML을 가져옵니다.
3. 각 키워드에 대해:
   - HTML에서 키워드 위치를 모두 찾습니다.
   - 각 위치를 중심으로 **앞뒤 일정 범위(예: 1000자)** 를 잘라냅니다.
   - 잘라낸 HTML 조각을 BeautifulSoup으로 파싱합니다.
   - 그 안에서 `<a href="https://...">` 태그를 모두 찾습니다.
   - 각 `<a>` 태그의 문자열이 window 내에서 등장하는 위치를 기준으로  
     **키워드 위치와의 문자 거리**를 계산합니다.
   - 여러 키워드 발생 위치와 여러 `<a>`가 섞여 있어도,  
     전체를 통틀어 **거리(문자 위치 차이)가 짧은 링크 순으로 정렬**하고  
     **최대 2개까지만 선택**합니다.
4. 하나 이상의 키워드에 대해 가까운 링크가 선택되면:
   - 키워드별로 최대 2개의 URL만 포함해서 이메일 본문을 생성
   - Gmail SMTP를 이용해 `TARGET_EMAIL`로 메일 발송
5. 어떤 키워드도 링크를 찾지 못하면:
   - 이메일을 보내지 않고 조용히 종료합니다.

---

## 6. 한계 및 확장 아이디어

현재 버전은 다음과 같은 특성을 가집니다.

- **중복 알림 방지 기능 없음**
  - 같은 공지가 여러 번 감지되면, 실행 시마다 다시 알림을 보낼 수 있습니다.
- **문자 거리 기반 "가까움" 정의**
  - 키워드와 `<a>` 태그 사이에 HTML 태그가 많이 끼어 있어도,  
    실제 HTML 문자열상 거리가 가까우면 "가까운 링크"로 판단합니다.

추후 확장 아이디어:

1. `history.json` 같은 파일을 두고,  
   이미 보낸 `(키워드, URL)` 조합은 다시 보내지 않도록 **중복 발송 방지** 로직 추가
2. `<a>` 텍스트나 부모 노드에 키워드가 포함된 경우만 허용하는  
   **더 강한 연관성 필터** 추가
3. Slack, Telegram 등 다른 채널로도 동시에 알림 전송
4. 여러 페이지(페이징)까지 순회하는 버전 확장

---

## 7. 라이선스

개인/연구/내부 업무 자동화 용도로 자유롭게 사용하시면 됩니다.  
회사/기관 배포용으로 사용할 경우, 내부 보안 정책 및 메일 서버 정책을 반드시 확인해 주세요.


> 주의: 일부 URL은 서버(WAF, IP 차단 등) 정책으로 403 Forbidden을 반환할 수 있습니다. 이 경우 해당 URL은 건너뛰고, 워크플로는 실패하지 않습니다.
