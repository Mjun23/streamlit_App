import re
import os
from collections import Counter
from datetime import datetime

import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.express as px
from wordcloud import WordCloud

# ──────────────────────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="유튜브 댓글 분석기", page_icon="📊", layout="wide")

# 깃허브 리포지토리에 업로드한 나눔고딕 폰트 경로 (워드클라우드 전용)
FONT_PATH = os.path.join("fonts", "NanumGothic.ttf")

# secrets.toml (또는 Streamlit Cloud > App settings > Secrets)에 아래처럼 등록해야 합니다.
# YOUTUBE_API_KEY = "여기에_발급받은_API_키"
try:
    API_KEY = st.secrets["YOUTUBE_API_KEY"]
except (KeyError, FileNotFoundError):
    API_KEY = None

# 워드클라우드에서 제외할 불용어 (필요에 따라 자유롭게 추가하세요)
STOPWORDS = {
    "그리고", "그래서", "하지만", "그런데", "그냥", "정말", "진짜", "너무",
    "제가", "저는", "그냥", "이거", "저거", "그거", "이렇게", "저렇게",
    "합니다", "입니다", "있습니다", "없습니다", "했습니다", "했어요",
    "이번", "우리", "당신", "여러분", "영상", "댓글", "구독", "채널",
    "그것", "이것", "저것", "때문", "정도", "생각", "사람", "오늘",
}

# ──────────────────────────────────────────────────────────────
# 유틸 함수
# ──────────────────────────────────────────────────────────────

def extract_video_id(url: str):
    """유튜브 URL에서 영상 ID를 추출한다."""
    patterns = [
        r"(?:youtube\.com\/watch\?v=)([0-9A-Za-z_-]{11})",
        r"(?:youtu\.be\/)([0-9A-Za-z_-]{11})",
        r"(?:youtube\.com\/shorts\/)([0-9A-Za-z_-]{11})",
        r"(?:youtube\.com\/embed\/)([0-9A-Za-z_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


@st.cache_data(ttl=600, show_spinner=False)
def get_video_info(video_id: str, api_key: str):
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {"part": "snippet,statistics", "id": video_id, "key": api_key}
    res = requests.get(url, params=params, timeout=10).json()
    if "error" in res:
        raise RuntimeError(res["error"].get("message", "YouTube API 오류"))
    items = res.get("items", [])
    if not items:
        return None
    item = items[0]
    stats = item.get("statistics", {})
    snippet = item.get("snippet", {})
    return {
        "title": snippet.get("title", ""),
        "channel": snippet.get("channelTitle", ""),
        "published_at": snippet.get("publishedAt", ""),
        "view_count": int(stats.get("viewCount", 0)),
        "like_count": int(stats.get("likeCount", 0)),
        "comment_count": int(stats.get("commentCount", 0)),
        "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
    }


@st.cache_data(ttl=600, show_spinner=False)
def get_comments(video_id: str, api_key: str, max_count: int):
    comments = []
    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "key": api_key,
        "maxResults": min(100, max_count),
        "order": "time",
        "textFormat": "plainText",
    }
    while len(comments) < max_count:
        res = requests.get(url, params=params, timeout=10).json()
        if "error" in res:
            raise RuntimeError(res["error"].get("message", "YouTube API 오류"))
        for item in res.get("items", []):
            top = item["snippet"]["topLevelComment"]["snippet"]
            comments.append({
                "author": top.get("authorDisplayName", ""),
                "text": top.get("textDisplay", ""),
                "like_count": top.get("likeCount", 0),
                "published_at": top.get("publishedAt", ""),
                "reply_count": item["snippet"].get("totalReplyCount", 0),
            })
            if len(comments) >= max_count:
                break
        next_token = res.get("nextPageToken")
        if not next_token or len(comments) >= max_count:
            break
        params["pageToken"] = next_token
    return comments[:max_count]


def extract_korean_words(texts):
    """한글 2음절 이상 단어를 추출하고 불용어를 제거한다."""
    words = []
    for text in texts:
        tokens = re.findall(r"[가-힣]{2,}", text)
        for t in tokens:
            if t not in STOPWORDS:
                words.append(t)
    return words


def build_wordcloud(word_freq: dict):
    if not os.path.exists(FONT_PATH):
        return None, f"폰트 파일을 찾을 수 없습니다: {FONT_PATH} (깃허브 저장소에 fonts/NanumGothic.ttf 경로로 업로드했는지 확인해 주세요)"
    wc = WordCloud(
        font_path=FONT_PATH,
        width=900,
        height=500,
        background_color="white",
        colormap="viridis",
        max_words=150,
    ).generate_from_frequencies(word_freq)
    return wc, None


def pick_time_bucket(span_days: float):
    """댓글 작성 기간에 따라 적절한 집계 단위를 고른다."""
    if span_days <= 2:
        return "H", "시간별"
    elif span_days <= 60:
        return "D", "일별"
    else:
        return "W", "주별"


# ──────────────────────────────────────────────────────────────
# 사이드바 - 입력
# ──────────────────────────────────────────────────────────────
st.sidebar.title("📊 유튜브 댓글 분석기")
st.sidebar.markdown("영상 링크를 입력하면 댓글을 분석해 드려요.")

video_url = st.sidebar.text_input("유튜브 영상 링크", placeholder="https://www.youtube.com/watch?v=...")
max_comments = st.sidebar.slider("분석할 댓글 개수", min_value=50, max_value=1000, value=200, step=50)
run_btn = st.sidebar.button("분석 시작", type="primary", use_container_width=True)

st.title("유튜브 댓글 분석기")

if not API_KEY:
    st.error(
        "YouTube API 키가 설정되어 있지 않습니다. "
        "Streamlit Cloud의 App settings > Secrets에 아래와 같이 등록해 주세요.\n\n"
        "```\nYOUTUBE_API_KEY = \"여기에_발급받은_API_키\"\n```"
    )
    st.stop()

if not run_btn:
    st.info("왼쪽 사이드바에 유튜브 영상 링크를 입력하고 [분석 시작] 버튼을 눌러 주세요.")
    st.stop()

video_id = extract_video_id(video_url.strip()) if video_url else None
if not video_id:
    st.error("올바른 유튜브 영상 링크가 아닙니다. 링크를 다시 확인해 주세요.")
    st.stop()

# ──────────────────────────────────────────────────────────────
# 데이터 가져오기
# ──────────────────────────────────────────────────────────────
with st.spinner("영상 정보를 가져오는 중..."):
    try:
        video_info = get_video_info(video_id, API_KEY)
    except RuntimeError as e:
        st.error(f"영상 정보를 가져오지 못했습니다: {e}")
        st.stop()

if video_info is None:
    st.error("영상을 찾을 수 없습니다. 링크를 다시 확인해 주세요.")
    st.stop()

with st.spinner(f"댓글 최대 {max_comments}개를 가져오는 중..."):
    try:
        comments = get_comments(video_id, API_KEY, max_comments)
    except RuntimeError as e:
        st.error(f"댓글을 가져오지 못했습니다: {e}")
        st.stop()

if not comments:
    st.warning("이 영상에는 댓글이 없거나, 댓글이 비활성화되어 있습니다.")
    st.stop()

df = pd.DataFrame(comments)
df["published_at"] = pd.to_datetime(df["published_at"])

# ──────────────────────────────────────────────────────────────
# 영상 정보 + 요약 지표
# ──────────────────────────────────────────────────────────────
col_video, col_info = st.columns([1.2, 1])
with col_video:
    st.video(f"https://www.youtube.com/watch?v={video_id}")
with col_info:
    st.subheader(video_info["title"])
    st.caption(f"채널: {video_info['channel']}")
    m1, m2, m3 = st.columns(3)
    m1.metric("조회수", f"{video_info['view_count']:,}")
    m2.metric("좋아요", f"{video_info['like_count']:,}")
    m3.metric("전체 댓글 수", f"{video_info['comment_count']:,}")
    st.caption(f"이번 분석에는 최신 댓글 {len(df):,}개를 사용했어요.")

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["⏱ 시간대별 추이", "👍 댓글 반응도", "☁ 워드클라우드", "📋 댓글 목록"])

# ──────────────────────────────────────────────────────────────
# 탭 1. 시간대별 댓글 작성 추이
# ──────────────────────────────────────────────────────────────
with tab1:
    st.subheader("시간대별 댓글 작성 추이")

    span_days = (df["published_at"].max() - df["published_at"].min()).total_seconds() / 86400
    freq, label = pick_time_bucket(span_days)

    trend = (
        df.set_index("published_at")
        .resample(freq)
        .size()
        .reset_index(name="댓글 수")
    )
    fig_trend = px.line(
        trend, x="published_at", y="댓글 수", markers=True,
        title=f"{label} 댓글 작성 추이",
        labels={"published_at": "시간"},
    )
    st.plotly_chart(fig_trend, use_container_width=True)

    # 시간대(0~23시)별 댓글 분포
    df["hour"] = df["published_at"].dt.hour
    hour_dist = df.groupby("hour").size().reindex(range(24), fill_value=0).reset_index(name="댓글 수")
    fig_hour = px.bar(
        hour_dist, x="hour", y="댓글 수",
        title="시(0~23시)별 댓글 작성 분포",
        labels={"hour": "시(hour)"},
    )
    st.plotly_chart(fig_hour, use_container_width=True)

# ──────────────────────────────────────────────────────────────
# 탭 2. 댓글 반응도
# ──────────────────────────────────────────────────────────────
with tab2:
    st.subheader("댓글 반응도")

    r1, r2, r3 = st.columns(3)
    r1.metric("평균 좋아요", f"{df['like_count'].mean():.1f}")
    r2.metric("평균 답글 수", f"{df['reply_count'].mean():.1f}")
    r3.metric("최다 좋아요", f"{df['like_count'].max():,}")

    fig_scatter = px.scatter(
        df, x="published_at", y="like_count",
        size="reply_count", hover_data=["author"],
        title="작성 시간 대비 좋아요 수",
        labels={"published_at": "작성 시간", "like_count": "좋아요 수"},
    )
    st.plotly_chart(fig_scatter, use_container_width=True)

    st.markdown("**좋아요 Top 10 댓글**")
    top10 = df.sort_values("like_count", ascending=False).head(10)[
        ["author", "text", "like_count", "reply_count", "published_at"]
    ]
    st.dataframe(top10, use_container_width=True, hide_index=True)

# ──────────────────────────────────────────────────────────────
# 탭 3. 워드클라우드
# ──────────────────────────────────────────────────────────────
with tab3:
    st.subheader("댓글 워드클라우드")

    words = extract_korean_words(df["text"].tolist())
    if not words:
        st.warning("워드클라우드를 만들 만한 한글 단어가 부족해요.")
    else:
        word_freq = Counter(words)
        wc, err = build_wordcloud(word_freq)
        if err:
            st.error(err)
        else:
            st.image(wc.to_array(), use_container_width=True)

            st.markdown("**자주 등장한 단어 Top 20**")
            top_words = pd.DataFrame(word_freq.most_common(20), columns=["단어", "빈도"])
            fig_words = px.bar(
                top_words.sort_values("빈도"), x="빈도", y="단어",
                orientation="h", title="자주 등장한 단어",
            )
            st.plotly_chart(fig_words, use_container_width=True)

# ──────────────────────────────────────────────────────────────
# 탭 4. 댓글 목록
# ──────────────────────────────────────────────────────────────
with tab4:
    st.subheader("댓글 목록")
    show_df = df[["author", "text", "like_count", "reply_count", "published_at"]].sort_values(
        "published_at", ascending=False
    )
    st.dataframe(show_df, use_container_width=True, hide_index=True)
