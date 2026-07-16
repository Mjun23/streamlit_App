"""
섹터별 인기 종목 탐색 앱
- 섹터(IT/헬스케어/금융/소비재/에너지) 탭 선택
- 각 탭에서 한국/미국 종목 중 인기 종목 리스트 표시 (실시간 가격/등락률)
- 종목 클릭 시 상세 정보(차트, 주요 지표) + 관련 뉴스 표시
"""

import streamlit as st
import pandas as pd
import yfinance as yf
import feedparser
import urllib.parse
from datetime import datetime

# ------------------------------------------------------------
# 기본 설정
# ------------------------------------------------------------
st.set_page_config(page_title="섹터별 인기 종목", page_icon="📈", layout="wide")

# 섹터 -> {시장: [(티커, 종목명), ...]}
SECTORS = {
    "IT / 기술": {
        "한국": [
            ("005930.KS", "삼성전자"),
            ("000660.KS", "SK하이닉스"),
            ("035420.KS", "NAVER"),
            ("035720.KS", "카카오"),
            ("066570.KS", "LG전자"),
            ("018260.KS", "삼성에스디에스"),
        ],
        "미국": [
            ("AAPL", "Apple"),
            ("MSFT", "Microsoft"),
            ("GOOGL", "Alphabet"),
            ("NVDA", "NVIDIA"),
            ("META", "Meta Platforms"),
            ("AVGO", "Broadcom"),
        ],
    },
    "헬스케어": {
        "한국": [
            ("207940.KS", "삼성바이오로직스"),
            ("068270.KS", "셀트리온"),
            ("128940.KS", "한미약품"),
            ("326030.KS", "SK바이오팜"),
            ("196170.KQ", "알테오젠"),
        ],
        "미국": [
            ("UNH", "UnitedHealth"),
            ("JNJ", "Johnson & Johnson"),
            ("LLY", "Eli Lilly"),
            ("PFE", "Pfizer"),
            ("ABBV", "AbbVie"),
            ("MRK", "Merck"),
        ],
    },
    "금융": {
        "한국": [
            ("105560.KS", "KB금융"),
            ("055550.KS", "신한지주"),
            ("086790.KS", "하나금융지주"),
            ("316140.KS", "우리금융지주"),
            ("032830.KS", "삼성생명"),
        ],
        "미국": [
            ("JPM", "JPMorgan Chase"),
            ("BAC", "Bank of America"),
            ("WFC", "Wells Fargo"),
            ("GS", "Goldman Sachs"),
            ("MA", "Mastercard"),
            ("V", "Visa"),
        ],
    },
    "소비재": {
        "한국": [
            ("051900.KS", "LG생활건강"),
            ("097950.KS", "CJ제일제당"),
            ("271560.KS", "오리온"),
            ("090430.KS", "아모레퍼시픽"),
            ("004170.KS", "신세계"),
        ],
        "미국": [
            ("AMZN", "Amazon"),
            ("WMT", "Walmart"),
            ("PG", "Procter & Gamble"),
            ("KO", "Coca-Cola"),
            ("NKE", "Nike"),
            ("MCD", "McDonald's"),
        ],
    },
    "에너지": {
        "한국": [
            ("096770.KS", "SK이노베이션"),
            ("010950.KS", "S-Oil"),
            ("034730.KS", "SK"),
            ("015760.KS", "한국전력"),
        ],
        "미국": [
            ("XOM", "ExxonMobil"),
            ("CVX", "Chevron"),
            ("COP", "ConocoPhillips"),
            ("SLB", "Schlumberger"),
            ("EOG", "EOG Resources"),
        ],
    },
}

# ------------------------------------------------------------
# 데이터 조회 함수 (캐시 적용)
# ------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def get_quotes(tickers: tuple):
    """티커 리스트에 대한 최근 종가/등락률을 일괄 조회"""
    results = {}
    if not tickers:
        return results
    try:
        data = yf.download(
            list(tickers), period="5d", progress=False, group_by="ticker", threads=True
        )
    except Exception:
        data = None

    for t in tickers:
        last, change = None, None
        try:
            if data is not None:
                if len(tickers) == 1:
                    closes = data["Close"].dropna()
                else:
                    closes = data[t]["Close"].dropna()
                if len(closes) >= 2:
                    last = float(closes.iloc[-1])
                    prev = float(closes.iloc[-2])
                    change = (last - prev) / prev * 100
                elif len(closes) == 1:
                    last = float(closes.iloc[-1])
        except Exception:
            pass
        results[t] = (last, change)
    return results


@st.cache_data(ttl=600, show_spinner=False)
def get_history(ticker: str, period: str = "6mo"):
    try:
        hist = yf.Ticker(ticker).history(period=period)
        return hist
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=600, show_spinner=False)
def get_key_stats(ticker: str):
    stats = {}
    try:
        fi = yf.Ticker(ticker).fast_info
        stats["현재가"] = fi.get("last_price")
        stats["통화"] = fi.get("currency")
        stats["52주 최고"] = fi.get("year_high")
        stats["52주 최저"] = fi.get("year_low")
        stats["시가총액"] = fi.get("market_cap")
    except Exception:
        pass
    return stats


@st.cache_data(ttl=600, show_spinner=False)
def get_news(ticker: str, name: str):
    """야후 파이낸스 뉴스 + 구글 뉴스(한/영) RSS를 합쳐서 반환"""
    news_items = []

    # 1) yfinance 뉴스 (best-effort, 스키마가 버전에 따라 다를 수 있어 방어적으로 처리)
    try:
        raw_news = yf.Ticker(ticker).news or []
        for n in raw_news[:5]:
            content = n.get("content", n)  # 신버전은 'content' 하위에 필드가 있음
            title = content.get("title") or n.get("title")
            link = (
                (content.get("canonicalUrl") or {}).get("url")
                or (content.get("clickThroughUrl") or {}).get("url")
                or n.get("link")
            )
            publisher = (content.get("provider") or {}).get("displayName") or n.get(
                "publisher"
            )
            if title and link:
                news_items.append(
                    {"title": title, "publisher": publisher or "Yahoo Finance", "link": link}
                )
    except Exception:
        pass

    # 2) 구글 뉴스 RSS (한국어 + 영어, 언어 무관하게 둘 다 시도)
    for hl, gl, ceid in [("ko", "KR", "KR:ko"), ("en-US", "US", "US:en")]:
        try:
            query = urllib.parse.quote(name)
            url = f"https://news.google.com/rss/search?q={query}&hl={hl}&gl={gl}&ceid={ceid}"
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                source = getattr(entry, "source", {})
                publisher = source.get("title") if isinstance(source, dict) else "Google News"
                news_items.append(
                    {
                        "title": entry.title,
                        "publisher": publisher or "Google News",
                        "link": entry.link,
                    }
                )
        except Exception:
            pass

    # 중복 제거 (제목 기준)
    seen = set()
    deduped = []
    for item in news_items:
        key = item["title"].strip()
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped[:12]


# ------------------------------------------------------------
# 포맷 유틸
# ------------------------------------------------------------
def fmt_price(value, currency=""):
    if value is None:
        return "N/A"
    return f"{value:,.2f} {currency}".strip()


def fmt_change(value):
    if value is None:
        return ""
    color = "red" if value > 0 else ("blue" if value < 0 else "gray")
    sign = "+" if value > 0 else ""
    return f":{color}[{sign}{value:.2f}%]"


def fmt_market_cap(value):
    if value is None:
        return "N/A"
    for unit, div in [("조", 1e12), ("억", 1e8)]:
        pass
    if value >= 1e12:
        return f"{value/1e12:.2f}조"
    if value >= 1e8:
        return f"{value/1e8:.0f}억"
    return f"{value:,.0f}"


# ------------------------------------------------------------
# 세션 상태 초기화
# ------------------------------------------------------------
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = None
if "selected_name" not in st.session_state:
    st.session_state.selected_name = None


def select_stock(ticker, name):
    st.session_state.selected_ticker = ticker
    st.session_state.selected_name = name


def clear_selection():
    st.session_state.selected_ticker = None
    st.session_state.selected_name = None


# ------------------------------------------------------------
# 상세 화면
# ------------------------------------------------------------
def render_detail():
    ticker = st.session_state.selected_ticker
    name = st.session_state.selected_name

    st.button("← 목록으로 돌아가기", on_click=clear_selection)
    st.header(f"{name} ({ticker})")

    with st.spinner("데이터를 불러오는 중..."):
        stats = get_key_stats(ticker)
        hist = get_history(ticker)
        news = get_news(ticker, name)

    currency = stats.get("통화", "")
    cols = st.columns(4)
    cols[0].metric("현재가", fmt_price(stats.get("현재가"), currency))
    cols[1].metric("52주 최고", fmt_price(stats.get("52주 최고"), currency))
    cols[2].metric("52주 최저", fmt_price(stats.get("52주 최저"), currency))
    cols[3].metric("시가총액", fmt_market_cap(stats.get("시가총액")))

    st.subheader("최근 6개월 주가 추이")
    if hist is not None and not hist.empty:
        st.line_chart(hist["Close"])
    else:
        st.info("차트 데이터를 불러올 수 없습니다.")

    st.subheader("관련 뉴스")
    if news:
        for item in news:
            st.markdown(f"- [{item['title']}]({item['link']})  \n  <sub>{item['publisher']}</sub>", unsafe_allow_html=True)
    else:
        st.info("관련 뉴스를 찾을 수 없습니다.")


# ------------------------------------------------------------
# 목록 화면 (섹터 탭)
# ------------------------------------------------------------
def render_sector_tab(sector_name, markets_dict):
    market_choice = st.radio(
        "시장 선택",
        options=["전체", "한국", "미국"],
        horizontal=True,
        key=f"market_{sector_name}",
    )

    if market_choice == "전체":
        stock_list = markets_dict["한국"] + markets_dict["미국"]
    else:
        stock_list = markets_dict[market_choice]

    tickers = tuple(t for t, _ in stock_list)
    with st.spinner("시세를 불러오는 중..."):
        quotes = get_quotes(tickers)

    n_cols = 3
    cols = st.columns(n_cols)
    for i, (ticker, name) in enumerate(stock_list):
        last, change = quotes.get(ticker, (None, None))
        with cols[i % n_cols]:
            with st.container(border=True):
                st.markdown(f"**{name}**  \n`{ticker}`")
                st.markdown(f"{fmt_price(last)}  {fmt_change(change)}")
                st.button(
                    "상세보기",
                    key=f"btn_{sector_name}_{ticker}",
                    on_click=select_stock,
                    args=(ticker, name),
                    use_container_width=True,
                )


# ------------------------------------------------------------
# 메인
# ------------------------------------------------------------
def main():
    st.title("📈 섹터별 인기 종목")
    st.caption("관심있는 섹터를 선택하고, 종목을 눌러 상세 정보와 뉴스를 확인하세요. (데이터 출처: Yahoo Finance, Google News)")

    if st.session_state.selected_ticker:
        render_detail()
        return

    tab_names = list(SECTORS.keys())
    tabs = st.tabs(tab_names)
    for tab, sector_name in zip(tabs, tab_names):
        with tab:
            render_sector_tab(sector_name, SECTORS[sector_name])

    st.divider()
    st.caption(f"마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')} · 시세는 최대 15~20분 지연될 수 있습니다.")


if __name__ == "__main__":
    main()
