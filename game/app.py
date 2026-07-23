"""
기묘한 물건 x 외계인 협상 x 행성 카페 타이쿤
--------------------------------------------
인스크립션 스타일의 기묘한 물건을 외계 종족에게 팔아 갤럭틱 크레딧을 벌고,
그 돈으로 행성에 카페를 지어 운영하는 Streamlit 게임 프로토타입.

실행 방법:
    pip install streamlit
    streamlit run alien_negotiation_cafe.py
"""

import random
import time
import uuid

import streamlit as st

# ------------------------------------------------------------------
# 게임 데이터
# ------------------------------------------------------------------

ALIENS = [
    {
        "name": "블롭족 자그닉스",
        "emoji": "🟣",
        "likes": ["축축함", "소리"],
        "dislikes": ["건조함"],
        "greed": 1.1,
        "patience": 4,
        "greeting": "츄릅... 이 물건, 촉감이 궁금하군...",
        "happy_line": "오오, 이건 내 촉수가 다 떨릴 정도야!",
        "meh_line": "흐음... 나쁘진 않지만... 그저 그런데.",
        "angry_line": "이런 건조한 쓰레기를 나한테 팔려는 건가?!",
    },
    {
        "name": "크리스탈족 벤조르",
        "emoji": "🔷",
        "likes": ["반짝임", "신비함"],
        "dislikes": ["섬뜩함"],
        "greed": 1.3,
        "patience": 3,
        "greeting": "빛나는 것... 내 결정체가 공명하고 있다.",
        "happy_line": "완벽해! 내 몸 전체가 진동하고 있어!",
        "meh_line": "그럭저럭 빛나긴 하는군. 나쁘지 않아.",
        "angry_line": "섬뜩해! 저리 치워라!",
    },
    {
        "name": "심연족 그르쿨",
        "emoji": "🖤",
        "likes": ["섬뜩함", "건조함"],
        "dislikes": ["반짝임"],
        "greed": 0.9,
        "patience": 5,
        "greeting": "...어둠 속에서 무언가 속삭인다... 팔 텐가?",
        "happy_line": "훌륭해... 심연이 만족하는군...",
        "meh_line": "나쁘진 않다만... 더 어두운 걸 원했는데.",
        "angry_line": "너무 밝다! 눈이... 눈이 아파!",
    },
    {
        "name": "울음소리족 미아릴",
        "emoji": "🎐",
        "likes": ["소리", "신비함"],
        "dislikes": ["건조함"],
        "greed": 1.0,
        "patience": 4,
        "greeting": "쉿... 들어보아라, 저것이 노래하는 소리를...",
        "happy_line": "아름다운 화음이야! 우리 종족 전설에 나올 법해!",
        "meh_line": "소리가... 조금 단조롭군.",
        "angry_line": "조용해! 이건 소음일 뿐이야!",
    },
]

ITEM_POOL = [
    {"name": "울음소리를 내는 조약돌", "emoji": "🪨", "traits": ["소리", "축축함"], "base_value": 40},
    {"name": "시간이 거꾸로 가는 손목시계", "emoji": "⌚", "traits": ["신비함", "반짝임"], "base_value": 90},
    {"name": "영원히 녹지 않는 얼음 조각", "emoji": "🧊", "traits": ["반짝임", "축축함"], "base_value": 60},
    {"name": "거울에 비치지 않는 단추", "emoji": "🔘", "traits": ["신비함", "건조함"], "base_value": 35},
    {"name": "미소짓는 해골 모형", "emoji": "💀", "traits": ["섬뜩함", "건조함"], "base_value": 55},
    {"name": "저절로 움직이는 실타래", "emoji": "🧵", "traits": ["신비함", "소리"], "base_value": 45},
    {"name": "피 흘리는 것처럼 보이는 과일", "emoji": "🍎", "traits": ["섬뜩함", "축축함"], "base_value": 50},
    {"name": "부서지지 않는 유리구슬", "emoji": "🔮", "traits": ["반짝임", "신비함"], "base_value": 80},
]

CAFE_MENU = [
    {"name": "블롭 슬라임 라떼", "emoji": "🥤", "cost": 100, "income": 2, "tags": ["축축함"]},
    {"name": "반짝이 크리스탈 쿠키", "emoji": "🍪", "cost": 150, "income": 3, "tags": ["반짝임"]},
    {"name": "저주파 사운드 스무디", "emoji": "🥣", "cost": 200, "income": 4, "tags": ["소리"]},
    {"name": "섬뜩한 해골 파르페", "emoji": "🍨", "cost": 250, "income": 5, "tags": ["섬뜩함"]},
    {"name": "미스터리 안개 티", "emoji": "🍵", "cost": 300, "income": 6, "tags": ["신비함"]},
]

SCAVENGE_COOLDOWN_SEC = 8


# ------------------------------------------------------------------
# 상태 초기화
# ------------------------------------------------------------------

def init_state():
    if "initialized" in st.session_state:
        return
    st.session_state.initialized = True
    st.session_state.credits = 80
    st.session_state.inventory = [
        {**random.choice(ITEM_POOL), "id": str(uuid.uuid4())} for _ in range(2)
    ]
    st.session_state.neg = None  # 현재 진행 중인 협상
    st.session_state.owned_menu = []  # 카페에 보유한 메뉴 이름 목록
    st.session_state.last_update = time.time()
    st.session_state.last_scavenge = 0.0
    st.session_state.log = []


def add_log(msg: str):
    st.session_state.log.insert(0, msg)
    st.session_state.log = st.session_state.log[:6]


def match_score(item_traits, alien):
    score = 0
    for t in item_traits:
        if t in alien["likes"]:
            score += 1
        if t in alien["dislikes"]:
            score -= 1
    return score


def start_negotiation(item):
    alien = random.choice(ALIENS)
    score = match_score(item["traits"], alien)
    secret_max = item["base_value"] * (1 + 0.35 * score) * alien["greed"]
    secret_max = max(secret_max, item["base_value"] * 0.25)
    opening_offer = secret_max * random.uniform(0.45, 0.65)
    st.session_state.neg = {
        "alien": alien,
        "item": item,
        "score": score,
        "secret_max": secret_max,
        "offer": opening_offer,
        "patience": alien["patience"],
        "max_patience": alien["patience"],
        "turns": 0,
    }


def resolve_offer(ask_price):
    neg = st.session_state.neg
    alien = neg["alien"]
    if ask_price <= neg["secret_max"]:
        # 성사!
        st.session_state.credits += round(ask_price)
        st.session_state.inventory = [
            i for i in st.session_state.inventory if i["id"] != neg["item"]["id"]
        ]
        add_log(
            f"✅ {alien['emoji']} {alien['name']}에게 '{neg['item']['name']}'을(를) "
            f"{round(ask_price)} 크레딧에 판매!"
        )
        st.session_state.neg = None
        return

    # 거절 -> 카운터 오퍼
    neg["patience"] -= 1
    neg["turns"] += 1
    if neg["patience"] <= 0:
        add_log(f"❌ {alien['emoji']} {alien['name']}이(가) 인내심을 잃고 떠나버렸다...")
        st.session_state.neg = None
        return

    neg["offer"] += (neg["secret_max"] - neg["offer"]) * random.uniform(0.25, 0.55)
    if neg["score"] >= 1:
        add_log(f"💬 {alien['name']}: \"{alien['happy_line']}\" (가격을 올려 제안했다)")
    elif neg["score"] <= -1:
        add_log(f"💬 {alien['name']}: \"{alien['angry_line']}\"")
    else:
        add_log(f"💬 {alien['name']}: \"{alien['meh_line']}\"")


def accept_current_offer():
    neg = st.session_state.neg
    alien = neg["alien"]
    st.session_state.credits += round(neg["offer"])
    st.session_state.inventory = [
        i for i in st.session_state.inventory if i["id"] != neg["item"]["id"]
    ]
    add_log(
        f"🤝 {alien['emoji']} {alien['name']}의 제안({round(neg['offer'])} 크레딧)을 수락했다."
    )
    st.session_state.neg = None


def cafe_income_per_sec():
    total = 0
    for name in st.session_state.owned_menu:
        item = next(m for m in CAFE_MENU if m["name"] == name)
        total += item["income"]
    return total


def apply_passive_income():
    now = time.time()
    elapsed = now - st.session_state.last_update
    income = cafe_income_per_sec() * elapsed
    if income > 0:
        st.session_state.credits += income
    st.session_state.last_update = now


# ------------------------------------------------------------------
# UI
# ------------------------------------------------------------------

st.set_page_config(page_title="외계인 협상 카페", page_icon="👽", layout="centered")
init_state()
apply_passive_income()

st.title("👽☕ 외계인 협상 & 행성 카페")
st.caption("기묘한 물건을 외계 종족에게 팔고, 번 돈으로 행성에 카페를 지어보세요.")

col1, col2 = st.columns(2)
col1.metric("💰 크레딧", f"{st.session_state.credits:,.0f}")
col2.metric("☕ 카페 초당 수입", f"{cafe_income_per_sec()} / 초")

tab_neg, tab_cafe, tab_inv = st.tabs(["🛸 협상", "🏪 카페 경영", "🎒 창고"])

# ---------------- 협상 탭 ----------------
with tab_neg:
    if st.session_state.neg is None:
        st.subheader("협상할 물건을 고르세요")
        if not st.session_state.inventory:
            st.info("보유한 물건이 없습니다. '창고' 탭에서 물건을 주워오세요.")
        else:
            for item in st.session_state.inventory:
                c1, c2, c3 = st.columns([1, 3, 1])
                c1.markdown(f"### {item['emoji']}")
                c2.markdown(f"**{item['name']}**  \n태그: {', '.join(item['traits'])}")
                if c3.button("협상 시작", key=f"start_{item['id']}"):
                    start_negotiation(item)
                    st.rerun()
    else:
        neg = st.session_state.neg
        alien = neg["alien"]
        item = neg["item"]

        st.subheader(f"{alien['emoji']} {alien['name']}")
        st.write(f"_{alien['greeting']}_")
        st.write(f"판매 물건: **{item['emoji']} {item['name']}** (태그: {', '.join(item['traits'])})")

        st.progress(
            neg["patience"] / neg["max_patience"],
            text=f"외계인 인내심: {neg['patience']} / {neg['max_patience']}",
        )
        st.metric("현재 외계인 제안가", f"{neg['offer']:.0f} 크레딧")

        if neg["score"] >= 1:
            st.success("이 외계인은 당신의 물건에 꽤 관심이 있어 보입니다. 👀")
        elif neg["score"] <= -1:
            st.warning("이 외계인은 물건이 별로 마음에 들지 않는 눈치입니다. 😬")

        ask = st.number_input(
            "요구할 가격 (크레딧)",
            min_value=1,
            value=int(neg["offer"] * 1.2),
            step=5,
        )

        b1, b2, b3 = st.columns(3)
        if b1.button("💰 이 가격에 제안하기"):
            resolve_offer(ask)
            st.rerun()
        if b2.button("🤝 현재 제안 수락"):
            accept_current_offer()
            st.rerun()
        if b3.button("🚪 협상 포기"):
            add_log(f"🚪 {alien['name']}과의 협상을 포기했다.")
            st.session_state.neg = None
            st.rerun()

    if st.session_state.log:
        st.divider()
        st.caption("최근 기록")
        for line in st.session_state.log:
            st.write(line)

# ---------------- 카페 탭 ----------------
with tab_cafe:
    st.subheader("행성 카페 메뉴 확장")
    st.caption("외계 종족의 취향(태그)에 맞는 메뉴를 갖추면 손님이 더 좋아합니다.")
    for m in CAFE_MENU:
        owned = m["name"] in st.session_state.owned_menu
        c1, c2, c3 = st.columns([3, 2, 2])
        c1.markdown(f"**{m['emoji']} {m['name']}**  \n태그: {', '.join(m['tags'])}")
        c2.write(f"수입 +{m['income']}/초")
        if owned:
            c3.success("보유 중")
        else:
            if c3.button(f"{m['cost']} 크레딧에 구매", key=f"buy_{m['name']}"):
                if st.session_state.credits >= m["cost"]:
                    st.session_state.credits -= m["cost"]
                    st.session_state.owned_menu.append(m["name"])
                    add_log(f"☕ 카페에 '{m['name']}' 메뉴를 추가했다!")
                    st.rerun()
                else:
                    st.error("크레딧이 부족합니다.")

# ---------------- 창고 탭 ----------------
with tab_inv:
    st.subheader("창고 & 물건 수집")
    now = time.time()
    cooldown_left = SCAVENGE_COOLDOWN_SEC - (now - st.session_state.last_scavenge)
    if cooldown_left <= 0:
        if st.button("🔍 폐품 뒤지기 (새 물건 찾기)"):
            new_item = {**random.choice(ITEM_POOL), "id": str(uuid.uuid4())}
            st.session_state.inventory.append(new_item)
            st.session_state.last_scavenge = now
            add_log(f"🔍 새 물건을 발견했다: {new_item['emoji']} {new_item['name']}")
            st.rerun()
    else:
        st.button(f"🔍 폐품 뒤지기 ({cooldown_left:.0f}초 후 가능)", disabled=True)

    st.divider()
    if not st.session_state.inventory:
        st.info("보유한 물건이 없습니다.")
    else:
        for item in st.session_state.inventory:
            st.write(f"{item['emoji']} **{item['name']}** — 태그: {', '.join(item['traits'])} (기본가치 {item['base_value']})")

# 자동 갱신 (카페 수입 반영용, 너무 잦으면 부담되므로 버튼 새로고침 위주로 두어도 무방)
