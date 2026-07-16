"""
서울시 공영주차장 안내 - Streamlit Cloud 앱
------------------------------------------------
- CSV(서울시 공영주차장 안내 정보) 기반 지도 시각화
- 자치구별 최저 요금 주차장 추천
- 무료/주말운영/실시간 운영 여부 필터
- 사용자 CSV 업로드로 데이터 교체 가능
- (선택) 카카오 로컬 API로 좌표 없는 주소 좌표 보완
"""

import io
import re
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium

# --------------------------------------------------------------------------
# 기본 설정
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="서울시 공영주차장 안내",
    page_icon="🅿️",
    layout="wide",
    initial_sidebar_state="expanded",
)

DEFAULT_CSV_PATH = "서울시_공영주차장_안내_정보.csv"
SEOUL_CENTER = [37.5665, 126.9780]

CUSTOM_CSS = """
<style>
    .main .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
    div[data-testid="stMetric"] {
        background: #F7F5F1;
        border: 1px solid #E7E3DA;
        border-radius: 10px;
        padding: 14px 16px;
    }
    div[data-testid="stMetricLabel"] {font-weight: 600; color: #5B5347;}
    .badge-free {
        display:inline-block; padding:2px 10px; border-radius:999px;
        background:#E4F3E6; color:#1E7A34; font-size:0.8rem; font-weight:600;
    }
    .badge-paid {
        display:inline-block; padding:2px 10px; border-radius:999px;
        background:#FCEEE6; color:#B4531F; font-size:0.8rem; font-weight:600;
    }
    .rank-card {
        border:1px solid #E7E3DA; border-radius:12px; padding:14px 18px;
        margin-bottom:10px; background:#FFFFFF;
    }
    .rank-num {
        font-size:1.3rem; font-weight:800; color:#B4531F; margin-right:8px;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# 데이터 로딩 & 전처리
# --------------------------------------------------------------------------
def _read_csv_any_encoding(file_or_path):
    """CP949 / EUC-KR / UTF-8(BOM) 순으로 시도해서 CSV를 읽는다."""
    encodings = ["cp949", "euc-kr", "utf-8-sig", "utf-8"]
    last_err = None
    for enc in encodings:
        try:
            if hasattr(file_or_path, "seek"):
                file_or_path.seek(0)
            return pd.read_csv(file_or_path, encoding=enc)
        except (UnicodeDecodeError, UnicodeError) as e:
            last_err = e
            continue
    raise last_err


@st.cache_data(show_spinner=False)
def load_and_process(file_bytes: bytes) -> pd.DataFrame:
    df = _read_csv_any_encoding(io.BytesIO(file_bytes))
    df.columns = [c.strip() for c in df.columns]

    required = ["주차장명", "주소", "유무료구분명", "총 주차면"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"필수 컬럼이 없습니다: {', '.join(missing)}. "
            "서울 열린데이터광장의 '서울시 공영주차장 안내 정보' 원본 형식을 사용해주세요."
        )

    # 자치구 추출
    df["자치구"] = df["주소"].astype(str).str.extract(r"^(\S+?구)\b")
    df["자치구"] = df["자치구"].fillna("자치구 미상")

    # 무료 여부
    df["무료여부"] = df["유무료구분명"].astype(str).str.strip() == "무료"

    # 주말 운영 상태: 운영 / 미운영 / 정보없음
    def weekend_status(row):
        s, e = row.get("주말 운영 시작시각(HHMM)"), row.get("주말 운영 종료시각(HHMM)")
        if pd.isna(s) or pd.isna(e):
            return "정보없음"
        if s == e:
            return "미운영"
        return "운영"

    df["주말운영상태"] = df.apply(weekend_status, axis=1)

    # 시간당 요금(원/시간) 추정 - 정렬/추천용 지표
    def hourly_fee(row):
        if row["무료여부"]:
            return 0.0
        base_fee, base_time = row.get("기본 주차 요금"), row.get("기본 주차 시간(분 단위)")
        add_fee, add_time = row.get("추가 단위 요금"), row.get("추가 단위 시간(분 단위)")
        if pd.isna(base_fee) or pd.isna(base_time) or base_time in (0, None):
            return np.nan
        if pd.notna(add_fee) and pd.notna(add_time) and add_time > 0:
            extra_minutes = max(60 - base_time, 0)
            extra_units = np.ceil(extra_minutes / add_time) if extra_minutes > 0 else 0
            return round(base_fee + extra_units * add_fee, 0)
        return round(base_fee / base_time * 60, 0)

    df["시간당요금"] = df.apply(hourly_fee, axis=1)

    # 위경도 컬럼 정리
    for col in ["위도", "경도"]:
        if col not in df.columns:
            df[col] = np.nan
    df["좌표있음"] = df["위도"].notna() & df["경도"].notna()

    return df


def geocode_missing_with_kakao(df: pd.DataFrame, api_key: str, max_calls: int = 300) -> pd.DataFrame:
    """카카오 로컬 API로 좌표가 없는 주소를 보완한다 (Streamlit Cloud 배포 후 인터넷 연결 환경에서 동작)."""
    import requests

    df = df.copy()
    targets = df[~df["좌표있음"]].index.tolist()[:max_calls]
    if not targets:
        return df

    progress = st.progress(0.0, text="주소 좌표 변환 중...")
    headers = {"Authorization": f"KakaoAK {api_key}"}
    url = "https://dapi.kakao.com/v2/local/search/address.json"

    success = 0
    for i, idx in enumerate(targets):
        addr = str(df.at[idx, "주소"])
        try:
            resp = requests.get(url, headers=headers, params={"query": addr}, timeout=5)
            if resp.status_code == 200:
                docs = resp.json().get("documents", [])
                if docs:
                    df.at[idx, "위도"] = float(docs[0]["y"])
                    df.at[idx, "경도"] = float(docs[0]["x"])
                    df.at[idx, "좌표있음"] = True
                    success += 1
        except Exception:
            pass
        progress.progress((i + 1) / len(targets), text=f"주소 좌표 변환 중... ({i + 1}/{len(targets)})")

    progress.empty()
    st.success(f"좌표 변환 완료: {success}/{len(targets)}건 성공 (전체 미보완분 중 최대 {max_calls}건만 처리)")
    return df


def now_open_status(row, now: datetime) -> str:
    """오늘 요일 기준 현재 운영중 여부를 간단히 추정한다 (공휴일은 별도 고려하지 않음)."""
    weekday = now.weekday()  # 0=월 ... 5=토 6=일
    if weekday < 5:
        s, e = row.get("평일 운영 시작시각(HHMM)"), row.get("평일 운영 종료시각(HHMM)")
    else:
        s, e = row.get("주말 운영 시작시각(HHMM)"), row.get("주말 운영 종료시각(HHMM)")

    if pd.isna(s) or pd.isna(e):
        return "정보없음"
    s, e = int(s), int(e)
    if s == e:
        return "휴무"
    cur = now.hour * 100 + now.minute
    if s == 0 and e >= 2400:
        return "운영중"
    if s <= e:
        return "운영중" if s <= cur <= e else "운영종료"
    else:  # 자정을 넘기는 경우 (예: 2200~0600)
        return "운영중" if (cur >= s or cur <= e) else "운영종료"


# --------------------------------------------------------------------------
# 사이드바 - 데이터 소스 & 필터
# --------------------------------------------------------------------------
st.sidebar.title("🅿️ 데이터 & 필터")

uploaded = st.sidebar.file_uploader(
    "다른 CSV로 교체하기 (선택)",
    type=["csv"],
    help="서울 열린데이터광장의 '서울시 공영주차장 안내 정보' 형식과 동일한 CSV만 지원합니다.",
)

try:
    if uploaded is not None:
        raw_bytes = uploaded.getvalue()
        source_label = f"업로드한 파일: {uploaded.name}"
    else:
        with open(DEFAULT_CSV_PATH, "rb") as f:
            raw_bytes = f.read()
        source_label = "기본 제공 데이터 (서울시 공영주차장 안내 정보.csv)"
    df_raw = load_and_process(raw_bytes)
except FileNotFoundError:
    st.error(
        f"기본 데이터 파일을 찾을 수 없습니다. 앱과 같은 폴더에 "
        f"`{DEFAULT_CSV_PATH}` 파일을 함께 배포했는지 확인해주세요. "
        "또는 사이드바에서 CSV를 업로드해주세요."
    )
    st.stop()
except ValueError as e:
    st.error(str(e))
    st.stop()

st.sidebar.caption(source_label)

# 카카오 좌표 보완 (선택 기능)
with st.sidebar.expander("좌표 없는 주소 보완 (선택)"):
    missing_cnt = int((~df_raw["좌표있음"]).sum())
    st.write(f"좌표가 없는 주차장: **{missing_cnt}개**")
    st.caption(
        "카카오 로컬 API 키를 입력하면 주소를 좌표로 변환해 지도에 추가로 표시할 수 있습니다. "
        "(Kakao Developers에서 무료 발급 가능, Streamlit Cloud 배포본에서만 동작)"
    )
    kakao_key = st.text_input("카카오 REST API 키", type="password")
    if st.button("좌표 변환 실행", disabled=(missing_cnt == 0 or not kakao_key)):
        st.session_state["df_geocoded"] = geocode_missing_with_kakao(df_raw, kakao_key)

df_raw = st.session_state.get("df_geocoded", df_raw)

st.sidebar.divider()

gu_options = sorted([g for g in df_raw["자치구"].unique() if g != "자치구 미상"])
selected_gus = st.sidebar.multiselect("자치구 선택 (복수 가능)", gu_options, default=[])

free_only = st.sidebar.checkbox("무료 주차장만 보기")
weekend_only = st.sidebar.checkbox("주말 운영하는 곳만 보기")
keyword = st.sidebar.text_input("주차장명 / 주소 검색", placeholder="예: 시청, 역삼동 ...")

min_spots, max_spots = int(df_raw["총 주차면"].min()), int(df_raw["총 주차면"].max())
spot_range = st.sidebar.slider("총 주차면 수", min_spots, max_spots, (min_spots, max_spots))

# --------------------------------------------------------------------------
# 필터 적용
# --------------------------------------------------------------------------
df = df_raw.copy()
if selected_gus:
    df = df[df["자치구"].isin(selected_gus)]
if free_only:
    df = df[df["무료여부"]]
if weekend_only:
    df = df[df["주말운영상태"] == "운영"]
if keyword:
    kw = keyword.strip()
    df = df[df["주차장명"].str.contains(kw, case=False, na=False) | df["주소"].str.contains(kw, case=False, na=False)]
df = df[(df["총 주차면"] >= spot_range[0]) & (df["총 주차면"] <= spot_range[1])]

# --------------------------------------------------------------------------
# 헤더 & 요약 지표
# --------------------------------------------------------------------------
st.title("🅿️ 서울시 공영주차장 안내")
st.caption("주소 기반 지도 시각화 · 자치구별 최저요금 추천 · 실시간 운영여부 확인")

m1, m2, m3, m4 = st.columns(4)
m1.metric("검색된 주차장", f"{len(df):,}개", f"전체 {len(df_raw):,}개 중")
m2.metric("무료 주차장", f"{int(df['무료여부'].sum()):,}개")
m3.metric("주말 운영", f"{int((df['주말운영상태']=='운영').sum()):,}개")
m4.metric("지도에 표시 가능", f"{int(df['좌표있음'].sum()):,}개", help="좌표(위경도) 정보가 있는 주차장만 지도에 표시됩니다.")

tab_map, tab_recommend, tab_stats, tab_table = st.tabs(
    ["🗺️ 지도", "💰 자치구별 추천", "📊 통계", "📋 전체 데이터"]
)

# --------------------------------------------------------------------------
# 탭 1: 지도
# --------------------------------------------------------------------------
with tab_map:
    df_map = df[df["좌표있음"]]
    no_coord_cnt = len(df) - len(df_map)

    if no_coord_cnt > 0:
        st.info(
            f"현재 필터 조건 중 {no_coord_cnt}개 주차장은 좌표 정보가 없어 지도에 표시되지 않습니다. "
            "사이드바의 '좌표 없는 주소 보완' 기능을 사용해보세요."
        )

    if df_map.empty:
        st.warning("지도에 표시할 데이터가 없습니다. 필터 조건을 조정해보세요.")
    else:
        show_now_status = st.toggle("지금 운영중인 곳만 강조 표시", value=False)
        now = datetime.now()

        center_lat = df_map["위도"].mean()
        center_lon = df_map["경도"].mean()
        zoom = 12 if selected_gus else 11

        fmap = folium.Map(location=[center_lat, center_lon], zoom_start=zoom, tiles="CartoDB positron")
        cluster = MarkerCluster(name="주차장").add_to(fmap)

        for _, row in df_map.iterrows():
            is_free = row["무료여부"]
            fee_text = "무료" if is_free else (
                f"{int(row['시간당요금']):,}원/시간 (추정)" if pd.notna(row["시간당요금"]) else "요금 정보 확인 필요"
            )
            weekend_text = {"운영": "주말 운영", "미운영": "주말 휴무", "정보없음": "주말 운영정보 없음"}[row["주말운영상태"]]

            status_text = ""
            if show_now_status:
                status_text = f"<br><b>{now_open_status(row, now)}</b>"

            tooltip_html = f"""
            <div style="font-family: sans-serif; font-size: 13px; min-width:200px;">
                <b style="font-size:14px;">{row['주차장명']}</b><br>
                {row['주소']}<br>
                <span style="color:{'#1E7A34' if is_free else '#B4531F'}; font-weight:600;">{fee_text}</span><br>
                주차면: {int(row['총 주차면'])}면 · {weekend_text}<br>
                전화: {row['전화번호'] if pd.notna(row.get('전화번호')) else '정보없음'}
                {status_text}
            </div>
            """

            color = "green" if is_free else "orange"
            if show_now_status and now_open_status(row, now) == "운영종료":
                color = "gray"

            folium.CircleMarker(
                location=[row["위도"], row["경도"]],
                radius=6,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.75,
                weight=1,
                tooltip=folium.Tooltip(tooltip_html),
            ).add_to(cluster)

        st.markdown(
            "🟢 무료 &nbsp;&nbsp; 🟠 유료" + (" &nbsp;&nbsp; ⚪ 지금 운영종료" if show_now_status else ""),
            unsafe_allow_html=True,
        )
        st_folium(fmap, use_container_width=True, height=560, returned_objects=[])

# --------------------------------------------------------------------------
# 탭 2: 자치구별 최저요금 추천
# --------------------------------------------------------------------------
with tab_recommend:
    st.subheader("자치구를 선택하면 가장 저렴한 주차장을 추천해드려요")
    rec_gu = st.selectbox("자치구 선택", gu_options, key="rec_gu")
    top_n = st.slider("추천 개수", 3, 15, 5)

    df_gu = df_raw[df_raw["자치구"] == rec_gu].copy()

    # 무료 주차장 우선, 그 다음 시간당요금 오름차순 (요금 정보 없는 곳은 뒤로)
    df_gu["_정렬키"] = df_gu.apply(
        lambda r: -1 if r["무료여부"] else (r["시간당요금"] if pd.notna(r["시간당요금"]) else 1e9),
        axis=1,
    )
    df_gu = df_gu.sort_values("_정렬키").head(top_n)

    if df_gu.empty:
        st.warning("해당 자치구에 데이터가 없습니다.")
    else:
        for rank, (_, row) in enumerate(df_gu.iterrows(), start=1):
            fee_badge = (
                '<span class="badge-free">무료</span>'
                if row["무료여부"]
                else f'<span class="badge-paid">{int(row["시간당요금"]):,}원/시간</span>'
                if pd.notna(row["시간당요금"])
                else '<span class="badge-paid">요금 정보 확인 필요</span>'
            )
            weekend_text = {"운영": "주말 운영 ✅", "미운영": "주말 휴무 ❌", "정보없음": "주말 정보 없음"}[row["주말운영상태"]]
            st.markdown(
                f"""
                <div class="rank-card">
                    <span class="rank-num">{rank}</span>
                    <b style="font-size:1.05rem;">{row['주차장명']}</b> &nbsp; {fee_badge}<br>
                    <span style="color:#6B6459;">{row['주소']}</span><br>
                    총 {int(row['총 주차면'])}면 · {weekend_text} ·
                    일 최대요금 {"정보없음" if pd.isna(row.get("일 최대 요금")) else f"{int(row['일 최대 요금']):,}원"}
                </div>
                """,
                unsafe_allow_html=True,
            )

        if df_gu["좌표있음"].any():
            st.markdown("##### 추천 주차장 위치")
            rec_map = folium.Map(
                location=[df_gu[df_gu["좌표있음"]]["위도"].mean(), df_gu[df_gu["좌표있음"]]["경도"].mean()],
                zoom_start=14,
                tiles="CartoDB positron",
            )
            for rank, (_, row) in enumerate(df_gu.iterrows(), start=1):
                if row["좌표있음"]:
                    folium.Marker(
                        location=[row["위도"], row["경도"]],
                        tooltip=f"{rank}. {row['주차장명']}",
                        icon=folium.Icon(color="green" if row["무료여부"] else "orange", icon="car", prefix="fa"),
                    ).add_to(rec_map)
            st_folium(rec_map, use_container_width=True, height=400, returned_objects=[])

# --------------------------------------------------------------------------
# 탭 3: 통계
# --------------------------------------------------------------------------
with tab_stats:
    st.subheader("자치구별 통계")

    gu_stats = (
        df_raw.groupby("자치구")
        .agg(
            주차장수=("주차장명", "count"),
            무료주차장수=("무료여부", "sum"),
            평균시간당요금=("시간당요금", "mean"),
            총주차면=("총 주차면", "sum"),
        )
        .reset_index()
    )
    gu_stats = gu_stats[gu_stats["자치구"] != "자치구 미상"]
    gu_stats["무료비율(%)"] = (gu_stats["무료주차장수"] / gu_stats["주차장수"] * 100).round(1)
    gu_stats["평균시간당요금"] = gu_stats["평균시간당요금"].round(0)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**자치구별 주차장 수**")
        st.bar_chart(gu_stats.set_index("자치구")["주차장수"])
    with c2:
        st.markdown("**자치구별 무료 주차장 비율(%)**")
        st.bar_chart(gu_stats.set_index("자치구")["무료비율(%)"])

    st.markdown("**자치구별 평균 시간당 요금(원, 유료 주차장 기준)**")
    st.bar_chart(gu_stats.set_index("자치구")["평균시간당요금"])

    st.markdown("**자치구별 상세 통계표**")
    st.dataframe(
        gu_stats.sort_values("주차장수", ascending=False).rename(
            columns={"무료주차장수": "무료 주차장 수", "평균시간당요금": "평균 시간당요금(원)", "총주차면": "총 주차면 수"}
        ),
        use_container_width=True,
        hide_index=True,
    )

# --------------------------------------------------------------------------
# 탭 4: 전체 데이터 & 다운로드
# --------------------------------------------------------------------------
with tab_table:
    st.subheader(f"필터링된 데이터 ({len(df):,}개)")
    show_cols = [
        "주차장명", "자치구", "주소", "무료여부", "시간당요금", "총 주차면",
        "주말운영상태", "일 최대 요금", "전화번호", "좌표있음",
    ]
    show_cols = [c for c in show_cols if c in df.columns]
    st.dataframe(
        df[show_cols].rename(columns={"시간당요금": "시간당요금(추정,원)", "좌표있음": "지도표시가능"}),
        use_container_width=True,
        hide_index=True,
    )

    csv_bytes = df[show_cols].to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "필터링된 데이터 CSV 다운로드",
        data=csv_bytes,
        file_name=f"공영주차장_필터결과_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )

st.divider()
st.caption(
    "데이터 출처: 서울 열린데이터광장 '서울시 공영주차장 안내 정보'. "
    "요금은 기본요금/추가요금을 기준으로 추정한 시간당 요금이며 실제 요금과 다를 수 있습니다. "
    "운영시간 정보는 공휴일 등 예외를 완전히 반영하지 못할 수 있으니 방문 전 실제 운영 여부를 확인하세요."
)
