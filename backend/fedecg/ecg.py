from __future__ import annotations

import numpy as np

CLASSES = ["Normal", "Anomalia"]

# Médias e desvios usados para padronizar as features. São fixos (conhecimento a priori),
# porque num sistema federado não existe um conjunto central onde ajustar o scaler.
FEATURE_NAMES = ["rr_media", "rr_dp", "rmssd", "cv", "pnn50", "sd_diff_rel"]
_MU = np.array([0.80, 0.06, 0.08, 0.08, 0.30, 0.10])
_SD = np.array([0.18, 0.06, 0.08, 0.07, 0.30, 0.10])

DEVICE = {
    "watch": {"duration": 30.0, "jitter": 0.035, "artefact": 0.02},
}


def rr_sequence(rng: np.random.Generator, af: bool, device: str) -> np.ndarray:
    """Gera os intervalos RR (em segundos) de um registo."""
    cfg = DEVICE[device]
    base = 60.0 / rng.uniform(55, 95)
    rr, t = [], 0.0
    while t < cfg["duration"]:
        if af:
            # Anomalia: ritmo irregularmente irregular (tipo FA), frequência mais alta
            r = base * 0.78 * rng.lognormal(0.0, 0.11)
        else:
            # Ritmo sinusal com arritmia respiratória e, por vezes, uma extrassístole
            r = base * (1 + 0.04 * np.sin(2 * np.pi * t / 4.5)) + rng.normal(0, 0.012)
            if rng.random() < 0.07:
                r *= 0.65
                rr.append(max(0.25, r))
                t += r
                r = base * 1.3
        r = max(0.25, r + rng.normal(0, cfg["jitter"]))
        if rng.random() < cfg["artefact"]:
            # artefacto de movimento: um pico falso parte o intervalo em dois
            a = rng.uniform(0.3, 0.7)
            rr.extend([r * a, r * (1 - a)])
        else:
            rr.append(r)
        t += r
    return np.asarray(rr)


def features(rr: np.ndarray) -> np.ndarray:
    d = np.diff(rr)
    f = np.array([
        rr.mean(),
        rr.std(),
        np.sqrt(np.mean(d ** 2)),
        rr.std() / rr.mean(),
        np.mean(np.abs(d) > 0.05),
        np.std(d) / rr.mean(),
    ])
    return (f - _MU) / _SD


def make_dataset(rng: np.random.Generator, n: int, af_rate: float, device: str):
    y = (rng.random(n) < af_rate).astype(int)
    X = np.stack([features(rr_sequence(rng, bool(lbl), device)) for lbl in y])
    return X, y


def make_unlabelled(rng: np.random.Generator, n: int) -> np.ndarray:
    """Conjunto de referência público e sem labels, partilhado por todos os clientes."""
    devices = ["watch"] * n
    af = rng.random(n) < 0.3
    return np.stack([features(rr_sequence(rng, bool(a), d)) for a, d in zip(af, devices)])


def waveform(rng: np.random.Generator, af: bool, device: str, seconds: float = 4.0, fs: int = 100) -> list[float]:
    """Sinal de ECG para pré-visualização no frontend (só para mostrar; não é usado no treino)."""
    rr = rr_sequence(rng, af, device)
    beats = np.concatenate([[0.0], np.cumsum(rr)])
    t = np.arange(0, seconds, 1 / fs)
    g = lambda x, mu, s: np.exp(-(((x - mu) / s) ** 2))
    sig = np.zeros_like(t)
    for b in beats[beats < seconds + 1]:
        x = t - b
        m = (x >= 0) & (x < 0.8)
        xm = x[m]
        sig[m] += (0 if af else 0.12 * g(xm, 0.1, 0.025)) - 0.12 * g(xm, 0.2, 0.009) \
            + 1.0 * g(xm, 0.22, 0.011) - 0.28 * g(xm, 0.245, 0.011) + 0.3 * g(xm, 0.43, 0.05)
    if af:
        sig += 0.05 * np.sin(2 * np.pi * 6.3 * t)
    sig += rng.normal(0, 0.015, size=t.shape)
    return [round(float(v), 3) for v in sig]
