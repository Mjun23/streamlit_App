"""
Neural Network From Scratch — 밑바닥부터 구현한 신경망
--------------------------------------------------
numpy(행렬 연산)와 matplotlib(시각화)만 사용하고,
순전파/역전파/최적화를 전부 직접 구현한 다층 퍼셉트론(MLP)으로
나선형(spiral) 데이터셋을 분류하는 실시간 학습 시각화 앱.

실행 방법:
    pip install streamlit numpy matplotlib
    streamlit run neural_net_from_scratch.py
"""

import time

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st

rng = np.random.default_rng(42)


# ====================================================================
# 1. 데이터셋: 나선형(spiral) 분류 문제
#    - 선형 분류기로는 절대 못 푸는 고전적인 비선형 분류 문제
# ====================================================================

def generate_spiral_data(points_per_class, n_classes, noise=0.2):
    X = np.zeros((points_per_class * n_classes, 2))
    y = np.zeros(points_per_class * n_classes, dtype=int)
    for class_idx in range(n_classes):
        idx = range(points_per_class * class_idx, points_per_class * (class_idx + 1))
        r = np.linspace(0.05, 1, points_per_class)
        t = (
            np.linspace(class_idx * 4, (class_idx + 1) * 4, points_per_class)
            + rng.normal(0, noise, points_per_class)
        )
        X[idx] = np.c_[r * np.sin(t), r * np.cos(t)]
        y[idx] = class_idx
    return X, y


def one_hot(y, n_classes):
    out = np.zeros((y.shape[0], n_classes))
    out[np.arange(y.shape[0]), y] = 1
    return out


# ====================================================================
# 2. 활성화 함수와 그 도함수 (체인룰 역전파에 직접 사용)
# ====================================================================

def relu(z):
    return np.maximum(0, z)


def relu_deriv(z):
    return (z > 0).astype(float)


def tanh(z):
    return np.tanh(z)


def tanh_deriv(z):
    return 1 - np.tanh(z) ** 2


def sigmoid(z):
    z = np.clip(z, -500, 500)
    return 1 / (1 + np.exp(-z))


def sigmoid_deriv(z):
    s = sigmoid(z)
    return s * (1 - s)


def softmax(z):
    z_shift = z - np.max(z, axis=1, keepdims=True)
    exp_z = np.exp(z_shift)
    return exp_z / np.sum(exp_z, axis=1, keepdims=True)


ACTIVATIONS = {
    "relu": (relu, relu_deriv),
    "tanh": (tanh, tanh_deriv),
    "sigmoid": (sigmoid, sigmoid_deriv),
}


# ====================================================================
# 3. 신경망 본체: 순전파 / 역전파 / 파라미터 업데이트를 전부 수식으로 직접 구현
# ====================================================================

class NeuralNetworkFromScratch:
    def __init__(self, layer_sizes, activation="relu", l2=0.001):
        """
        layer_sizes: [입력차원, 은닉1, 은닉2, ..., 출력클래스수]
        가중치 W[l] shape: (layer_sizes[l], layer_sizes[l+1])
        """
        self.layer_sizes = layer_sizes
        self.act_fn, self.act_deriv = ACTIVATIONS[activation]
        self.l2 = l2
        self.n_layers = len(layer_sizes) - 1

        self.W, self.b = [], []
        for l in range(self.n_layers):
            fan_in, fan_out = layer_sizes[l], layer_sizes[l + 1]
            if activation == "relu":
                # He 초기화: ReLU에서 죽은 뉴런을 줄이기 위한 분산 스케일링
                scale = np.sqrt(2.0 / fan_in)
            else:
                # Xavier 초기화: tanh/sigmoid에 적합한 분산 스케일링
                scale = np.sqrt(1.0 / fan_in)
            self.W.append(rng.normal(0, scale, (fan_in, fan_out)))
            self.b.append(np.zeros((1, fan_out)))

        # 모멘텀을 위한 속도(velocity) 버퍼
        self.vW = [np.zeros_like(w) for w in self.W]
        self.vb = [np.zeros_like(bb) for bb in self.b]

    # ---------------- 순전파 ----------------
    def forward(self, X):
        A = X
        cache = {"A0": X, "Z": [], "A": [X]}
        for l in range(self.n_layers):
            Z = A @ self.W[l] + self.b[l]
            if l == self.n_layers - 1:
                A = softmax(Z)  # 출력층은 softmax (다중 클래스 확률)
            else:
                A = self.act_fn(Z)  # 은닉층은 선택한 활성화 함수
            cache["Z"].append(Z)
            cache["A"].append(A)
        return A, cache

    # ---------------- 손실 함수 ----------------
    def compute_loss(self, A_out, Y_onehot):
        m = Y_onehot.shape[0]
        eps = 1e-9
        cross_entropy = -np.sum(Y_onehot * np.log(A_out + eps)) / m
        l2_penalty = self.l2 / (2 * m) * sum(np.sum(w ** 2) for w in self.W)
        return cross_entropy + l2_penalty

    # ---------------- 역전파: 체인룰을 층마다 직접 전개 ----------------
    def backward(self, cache, Y_onehot):
        m = Y_onehot.shape[0]
        grads_W = [None] * self.n_layers
        grads_b = [None] * self.n_layers

        # 출력층: softmax + cross-entropy를 결합하면 dZ = A_out - Y 로 단순화됨
        dZ = cache["A"][-1] - Y_onehot

        for l in reversed(range(self.n_layers)):
            A_prev = cache["A"][l]  # 이전 층의 활성값 (l=0이면 입력 X)
            grads_W[l] = A_prev.T @ dZ / m + (self.l2 / m) * self.W[l]
            grads_b[l] = np.sum(dZ, axis=0, keepdims=True) / m

            if l > 0:
                dA_prev = dZ @ self.W[l].T
                dZ = dA_prev * self.act_deriv(cache["Z"][l - 1])

        return grads_W, grads_b

    # ---------------- 파라미터 업데이트 (모멘텀 SGD) ----------------
    def update(self, grads_W, grads_b, lr, momentum):
        for l in range(self.n_layers):
            self.vW[l] = momentum * self.vW[l] - lr * grads_W[l]
            self.vb[l] = momentum * self.vb[l] - lr * grads_b[l]
            self.W[l] += self.vW[l]
            self.b[l] += self.vb[l]

    # ---------------- 예측 ----------------
    def predict(self, X):
        A_out, _ = self.forward(X)
        return np.argmax(A_out, axis=1)

    def accuracy(self, X, y):
        return np.mean(self.predict(X) == y)


# ====================================================================
# 4. 시각화 유틸: 결정 경계 + 손실 곡선
# ====================================================================

def plot_decision_boundary(net, X, y, n_classes, loss_history, acc, epoch):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))

    # --- 결정 경계 ---
    x_min, x_max = X[:, 0].min() - 0.3, X[:, 0].max() + 0.3
    y_min, y_max = X[:, 1].min() - 0.3, X[:, 1].max() + 0.3
    xx, yy = np.meshgrid(np.linspace(x_min, x_max, 200), np.linspace(y_min, y_max, 200))
    grid = np.c_[xx.ravel(), yy.ravel()]
    preds = net.predict(grid).reshape(xx.shape)

    ax1.contourf(xx, yy, preds, alpha=0.35, cmap=plt.cm.rainbow, levels=n_classes - 1)
    ax1.scatter(X[:, 0], X[:, 1], c=y, cmap=plt.cm.rainbow, edgecolors="k", s=18)
    ax1.set_title(f"결정 경계 (에폭 {epoch}, 정확도 {acc*100:.1f}%)")
    ax1.set_xticks([])
    ax1.set_yticks([])

    # --- 손실 곡선 ---
    ax2.plot(loss_history, color="tab:red")
    ax2.set_title("학습 손실 (Cross-Entropy Loss)")
    ax2.set_xlabel("epoch")
    ax2.set_ylabel("loss")
    ax2.grid(alpha=0.3)

    fig.tight_layout()
    return fig


# ====================================================================
# 5. Streamlit UI
# ====================================================================

st.set_page_config(page_title="밑바닥부터 만드는 신경망", page_icon="🧠", layout="wide")
st.title("🧠 라이브러리 없이 밑바닥부터 만든 신경망")
st.caption("PyTorch/TensorFlow 없이 numpy 행렬 연산만으로 순전파·역전파를 직접 구현했습니다.")

with st.sidebar:
    st.header("⚙️ 데이터셋 설정")
    n_classes = st.selectbox("클래스 수 (나선 팔 개수)", [2, 3, 4, 5], index=1)
    points_per_class = st.slider("클래스당 데이터 수", 50, 300, 150, step=10)
    noise = st.slider("데이터 노이즈", 0.0, 1.0, 0.2, step=0.05)

    st.header("🏗️ 신경망 구조")
    hidden_str = st.text_input("은닉층 뉴런 수 (콤마로 구분)", "16,16")
    activation = st.selectbox("활성화 함수", ["relu", "tanh", "sigmoid"])

    st.header("🎯 학습 설정")
    lr = st.slider("학습률 (learning rate)", 0.001, 1.0, 0.3, step=0.001)
    momentum = st.slider("모멘텀", 0.0, 0.99, 0.9, step=0.01)
    l2 = st.slider("L2 정규화 강도", 0.0, 0.1, 0.001, step=0.001)
    epochs = st.slider("총 에폭 수", 50, 3000, 800, step=50)
    update_every = st.slider("몇 에폭마다 화면 갱신", 5, 100, 20, step=5)

    train_btn = st.button("🚀 학습 시작", type="primary", use_container_width=True)

try:
    hidden_layers = [int(x.strip()) for x in hidden_str.split(",") if x.strip()]
except ValueError:
    st.sidebar.error("은닉층 구조는 '16,16' 처럼 숫자와 콤마만 입력하세요.")
    hidden_layers = [16, 16]

st.write(
    f"**신경망 구조:** 입력(2) → "
    + " → ".join(f"은닉({h})" for h in hidden_layers)
    + f" → 출력({n_classes}, softmax)"
)

placeholder = st.empty()

if train_btn:
    X, y = generate_spiral_data(points_per_class, n_classes, noise)
    Y_onehot = one_hot(y, n_classes)
    layer_sizes = [2] + hidden_layers + [n_classes]
    net = NeuralNetworkFromScratch(layer_sizes, activation=activation, l2=l2)

    loss_history = []
    progress = st.progress(0, text="학습 준비 중...")

    for epoch in range(1, epochs + 1):
        A_out, cache = net.forward(X)
        loss = net.compute_loss(A_out, Y_onehot)
        grads_W, grads_b = net.backward(cache, Y_onehot)
        net.update(grads_W, grads_b, lr, momentum)
        loss_history.append(loss)

        if epoch % update_every == 0 or epoch == epochs:
            acc = net.accuracy(X, y)
            fig = plot_decision_boundary(net, X, y, n_classes, loss_history, acc, epoch)
            placeholder.pyplot(fig)
            plt.close(fig)
            progress.progress(epoch / epochs, text=f"에폭 {epoch}/{epochs} · 손실 {loss:.4f} · 정확도 {acc*100:.1f}%")

    st.success(f"학습 완료! 최종 정확도: {net.accuracy(X, y)*100:.1f}%")
else:
    X, y = generate_spiral_data(points_per_class, n_classes, noise)
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(X[:, 0], X[:, 1], c=y, cmap=plt.cm.rainbow, edgecolors="k", s=18)
    ax.set_title("학습 전 데이터셋 미리보기 — '학습 시작'을 눌러보세요")
    ax.set_xticks([])
    ax.set_yticks([])
    placeholder.pyplot(fig)
    plt.close(fig)
