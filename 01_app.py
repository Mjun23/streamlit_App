import streamlit as st

st.set_page_config(
    page_title="Stock Explorer",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Stock Explorer")
st.caption("산업별 인기 주식을 한눈에 확인하세요.")

# -----------------------------
# 산업별 인기 종목
# -----------------------------

SECTORS = {
    "IT": {
        "Apple": "AAPL",
        "Microsoft": "MSFT",
        "Alphabet": "GOOGL",
        "Meta": "META",
        "Oracle": "ORCL"
    },
    "AI": {
        "NVIDIA": "NVDA",
        "Palantir": "PLTR",
        "C3.ai": "AI",
        "Super Micro": "SMCI",
        "AMD": "AMD"
    },
    "반도체": {
        "NVIDIA": "NVDA",
        "TSMC": "TSM",
        "Broadcom": "AVGO",
        "삼성전자": "005930.KS",
        "SK하이닉스": "000660.KS"
    },
    "헬스케어": {
        "Eli Lilly": "LLY",
        "Johnson & Johnson": "JNJ",
        "Pfizer": "PFE",
        "UnitedHealth": "UNH",
        "AbbVie": "ABBV"
    },
    "자동차": {
        "Tesla": "TSLA",
        "Toyota": "TM",
        "BYD": "1211.HK",
        "현대차": "005380.KS",
        "기아": "000270.KS"
    },
    "금융": {
        "JPMorgan": "JPM",
        "Goldman Sachs": "GS",
        "Bank of America": "BAC",
        "KB금융": "105560.KS",
        "신한지주": "055550.KS"
    }
}

# -----------------------------
# Session State
# -----------------------------

if "selected_stock" not in st.session_state:
    st.session_state.selected_stock = None

# -----------------------------
# 산업 탭
# -----------------------------

tabs = st.tabs(list(SECTORS.keys()))

for i, sector in enumerate(SECTORS.keys()):

    with tabs[i]:

        st.subheader(f"{sector} 인기 종목")

        stocks = SECTORS[sector]

        cols = st.columns(3)

        idx = 0

        for name, ticker in stocks.items():

            with cols[idx % 3]:

                st.markdown(f"### {name}")
                st.write(f"티커 : {ticker}")

                if st.button(
                    "종목 보기",
                    key=ticker
                ):
                    st.session_state.selected_stock = ticker

            idx += 1

# -----------------------------
# 사이드바
# -----------------------------

st.sidebar.title("선택한 종목")

if st.session_state.selected_stock:

    st.sidebar.success(st.session_state.selected_stock)

else:

    st.sidebar.info("종목을 선택하세요.")
