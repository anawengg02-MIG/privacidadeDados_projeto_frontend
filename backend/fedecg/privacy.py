"""Local Differential Privacy: mecanismo de Laplace aplicado no cliente, antes do envio.

Soft labels: cada linha é uma distribuição de probabilidade, por isso a sensibilidade L1
de uma linha é 2. Com escala 2/ε, cada linha cumpre ε-LDP. Para as N linhas de uma ronda,
a composição básica dá N·ε (limite pessimista), e ao longo de T rondas dá T·N·ε.

FedAvg: os pesos são cortados para norma L1 ≤ C (clipping), o que dá sensibilidade 2C.

Nota: aqui a Secure Aggregation não reduz o ruído. Com LDP pura, cada contribuição tem de
ser privada sozinha. Reduzir o ruído graças à SA seria DP distribuída, que é outro regime.
"""
from __future__ import annotations

import numpy as np


def laplace_soft_labels(P: np.ndarray, eps: float, rng: np.random.Generator) -> np.ndarray:
    return P + rng.laplace(0.0, 2.0 / eps, size=P.shape)


def clip_l1(v: np.ndarray, C: float) -> np.ndarray:
    n = np.abs(v).sum()
    return v if n <= C else v * (C / n)


def laplace_weights(v: np.ndarray, eps: float, C: float, rng: np.random.Generator) -> np.ndarray:
    return clip_l1(v, C) + rng.laplace(0.0, 2.0 * C / eps, size=v.shape)


def budget(eps: float, n_rows: int, rounds: int, mode: str) -> dict:
    per_round = eps * n_rows if mode == "soft" else eps
    return {"eps_por_valor": eps, "eps_por_ronda": per_round, "eps_acumulado": per_round * rounds}
