# 섹터별 인기 종목 앱

한국/미국 주식을 섹터(IT, 헬스케어, 금융, 소비재, 에너지)별로 탐색하고,
종목을 클릭하면 주가 차트·주요 지표·관련 뉴스를 보여주는 Streamlit 앱입니다.

## 파일 구성
- `app.py` : 앱 본체
- `requirements.txt` : 필요 패키지 목록

## 로컬 실행
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud 배포 방법
1. GitHub에 새 저장소를 만들고 `app.py`, `requirements.txt`를 올립니다.
2. https://share.streamlit.io 접속 후 GitHub 계정으로 로그인합니다.
3. "New app" → 방금 만든 저장소/브랜치 선택 → Main file path에 `app.py` 입력 → Deploy.
4. 몇 분 내로 공개 URL이 생성됩니다.

## 데이터 소스
- 시세/차트/지표: [yfinance](https://pypi.org/project/yfinance/) (Yahoo Finance 비공식 라이브러리)
- 뉴스: yfinance 뉴스 + Google News RSS(한국어/영어 검색 결과를 함께 수집)

## 종목 리스트 수정
`app.py` 상단의 `SECTORS` 딕셔너리에서 섹터/시장별 종목(티커, 종목명)을 자유롭게
추가·삭제할 수 있습니다. 한국 종목은 코스피 `.KS`, 코스닥 `.KQ` 접미사를 사용합니다.

## 참고 및 한계
- Yahoo Finance 시세는 최대 15~20분 지연될 수 있습니다.
- 일부 한국 종목은 `fast_info`(시가총액, 52주 최고/최저 등)가 비어 있을 수 있습니다.
- yfinance의 뉴스 응답 스키마는 버전에 따라 달라질 수 있어, 실패 시 자동으로
  Google News 검색 결과로 대체됩니다.
- 이 앱은 투자 조언이 아니며, 정보 제공 목적입니다.
