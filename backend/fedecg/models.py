"""Modelos locais em NumPy: regressão logística (softmax) e uma MLP de uma camada escondida.

Os dois suportam treino com destilação: além da perda nas labels locais, aproximam as
previsões no conjunto de referência das soft labels globais recebidas do servidor.
"""
from __future__ import annotations

import numpy as np


def softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


class _Base:
    name = "base"

    def fit(self, X, y, epochs=60, lr=0.3, l2=1e-3, class_weight=None,
            X_ref=None, q_ref=None, alpha=0.0):
        n_cls = self.n_classes
        Y = np.eye(n_cls)[y]
        w = np.ones(len(y)) if class_weight is None else np.array([class_weight[c] for c in y])
        w = w / w.sum()
        for _ in range(epochs):
            grads = self._grads(X, (self._forward(X) - Y) * w[:, None], l2)
            if alpha > 0 and X_ref is not None and q_ref is not None:
                g_ref = self._grads(X_ref, alpha * (self._forward(X_ref) - q_ref) / len(X_ref), 0.0)
                grads = [a + b for a, b in zip(grads, g_ref)]
            for p, g in zip(self.params, grads):
                p -= lr * g
        return self

    def predict_proba(self, X):
        return self._forward(X)

    def predict(self, X):
        return self.predict_proba(X).argmax(axis=1)

    @property
    def n_params(self) -> int:
        return int(sum(p.size for p in self.params))

    def get_flat(self) -> np.ndarray:
        return np.concatenate([p.ravel() for p in self.params])

    def set_flat(self, flat: np.ndarray) -> None:
        i = 0
        for p in self.params:
            p[...] = flat[i:i + p.size].reshape(p.shape)
            i += p.size


class SoftmaxRegression(_Base):
    name = "Regressão logística"

    def __init__(self, n_features, n_classes, rng):
        self.n_classes = n_classes
        self.W = rng.normal(0, 0.01, (n_features, n_classes))
        self.b = np.zeros(n_classes)
        self.params = [self.W, self.b]

    def _forward(self, X):
        return softmax(X @ self.W + self.b)

    def _grads(self, X, dZ, l2):
        return [X.T @ dZ + l2 * self.W, dZ.sum(axis=0)]


class MLP(_Base):
    name = "MLP (16 neurónios)"

    def __init__(self, n_features, n_classes, rng, hidden=16):
        self.n_classes = n_classes
        self.W1 = rng.normal(0, np.sqrt(2 / n_features), (n_features, hidden))
        self.b1 = np.zeros(hidden)
        self.W2 = rng.normal(0, np.sqrt(2 / hidden), (hidden, n_classes))
        self.b2 = np.zeros(n_classes)
        self.params = [self.W1, self.b1, self.W2, self.b2]

    def _hidden(self, X):
        return np.maximum(0, X @ self.W1 + self.b1)

    def _forward(self, X):
        return softmax(self._hidden(X) @ self.W2 + self.b2)

    def _grads(self, X, dZ, l2):
        H = self._hidden(X)
        dH = (dZ @ self.W2.T) * (H > 0)
        return [X.T @ dH + l2 * self.W1, dH.sum(axis=0), H.T @ dZ + l2 * self.W2, dZ.sum(axis=0)]


def pr_auc(y_true, scores) -> float:
    """PR-AUC (average precision) da classe anomalia (1), a partir da probabilidade de anomalia."""
    y_true = np.asarray(y_true)
    pos = int(y_true.sum())
    if pos == 0:
        return 0.0
    order = np.argsort(-np.asarray(scores), kind="mergesort")
    y = y_true[order]
    tp = np.cumsum(y)
    precision = tp / np.arange(1, len(y) + 1)
    return float(np.sum(precision[y == 1]) / pos)


def f1_anomalia(y_true, y_pred) -> float:
    tp = int(np.sum((y_pred == 1) & (y_true == 1)))
    fp = int(np.sum((y_pred == 1) & (y_true == 0)))
    fn = int(np.sum((y_pred == 0) & (y_true == 1)))
    return 0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn)
