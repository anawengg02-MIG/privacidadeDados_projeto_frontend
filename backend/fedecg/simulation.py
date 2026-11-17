from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import ecg, privacy, secagg
from .models import MLP, SoftmaxRegression, pr_auc

N_CLASSES = len(ecg.CLASSES)
N_FEATURES = len(ecg.FEATURE_NAMES)
REF_SHOW = 17  # linha do conjunto de referência mostrada na interface


@dataclass
class Config:
    mode: str = "soft"          # "soft" ou "fedavg"
    ldp: bool = True
    eps: float = 4.0
    secagg: bool = True
    rounds: int = 3
    n_ref: int = 100
    local_epochs: int = 30
    alpha: float = 1.0          # peso da destilação
    clip: float = 5.0           # norma L1 máxima dos pesos (FedAvg com LDP)
    seed: int = 2029

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        c = cls()
        for k, v in (d or {}).items():
            if hasattr(c, k):
                setattr(c, k, type(getattr(c, k))(v))
        c.mode = "fedavg" if c.mode == "fedavg" else "soft"
        c.eps = float(min(max(c.eps, 0.1), 50.0))
        c.rounds = int(min(max(c.rounds, 1), 50))
        return c


CLIENT_SPECS = [
    # id, nome, dispositivo, nº registos, prevalência de anomalia, último registo é anomalia?
    ("A", "Cliente A", "watch", 160, 0.35, False),
    ("B", "Cliente B", "watch", 80, 0.04, True),
    ("C", "Cliente C", "watch", 200, 0.15, False),
    ("D", "Cliente D", "watch", 100, 0.03, False),
]


@dataclass
class Client:
    cid: str
    name: str
    device: str
    X: np.ndarray
    y: np.ndarray
    model: object
    latest: np.ndarray
    latest_is_af: bool
    preview: list
    sa: secagg.SecAggClient = field(default_factory=lambda: None)

    def class_weight(self):
        counts = np.bincount(self.y, minlength=N_CLASSES).astype(float)
        present = counts > 0
        w = np.zeros(N_CLASSES)
        w[present] = len(self.y) / (present.sum() * counts[present])
        return w


class Simulation:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.seed)
        rng = self.rng
        self.X_ref = ecg.make_unlabelled(rng, cfg.n_ref)
        Xa, ya = ecg.make_dataset(rng, 200, 0.25, "watch")
        Xb, yb = ecg.make_dataset(rng, 200, 0.25, "watch")
        self.X_test, self.y_test = np.vstack([Xa, Xb]), np.concatenate([ya, yb])

        self.clients: list[Client] = []
        for cid, name, dev, n, af, latest_af in CLIENT_SPECS:
            X, y = ecg.make_dataset(rng, n, af, dev)
            if cfg.mode == "soft" and cid in ("C", "D"):  # modelos locais diferentes entre clientes
                model = MLP(N_FEATURES, N_CLASSES, rng)
            else:
                model = SoftmaxRegression(N_FEATURES, N_CLASSES, rng)
            latest = ecg.features(ecg.rr_sequence(rng, latest_af, dev))[None, :]
            preview = ecg.waveform(rng, latest_af, dev)
            self.clients.append(Client(cid, name, dev, X, y, model, latest, latest_af, preview))

        if cfg.mode == "fedavg":
            self.global_w = self.clients[0].model.get_flat().copy()
            for c in self.clients:
                c.model.set_flat(self.global_w)
        self.q_global = None
        self.history: list[dict] = []
        self.local_only = self._local_only_baseline()

    # ---------- utilitários ----------
    def _local_only_baseline(self) -> dict:
        """PR-AUC de cada cliente treinado só com os seus dados (sem federação), para comparação."""
        out = {}
        for c in self.clients:
            m = type(c.model)(N_FEATURES, N_CLASSES, np.random.default_rng(1))
            m.fit(c.X, c.y, epochs=self.cfg.local_epochs * self.cfg.rounds, class_weight=c.class_weight())
            out[c.cid] = round(pr_auc(self.y_test, m.predict_proba(self.X_test)[:, 1]), 3)
        return out

    def _evaluate(self) -> dict:
        per = {c.cid: round(pr_auc(self.y_test, c.model.predict_proba(self.X_test)[:, 1]), 3) for c in self.clients}
        return {"prauc_por_cliente": per, "prauc_medio": round(float(np.mean(list(per.values()))), 3)}

    def _bytes(self) -> int:
        if self.cfg.mode == "soft":
            return self.cfg.n_ref * N_CLASSES * 4
        return self.clients[0].model.n_params * 4

    # ---------- eventos ----------
    def setup_event(self) -> dict:
        return {
            "type": "setup",
            "config": self.cfg.__dict__,
            "classes": ecg.CLASSES,
            "n_ref": self.cfg.n_ref,
            "ref_show": REF_SHOW,
            "bytes_por_cliente": self._bytes(),
            "local_only": self.local_only,
            "clients": [{
                "id": c.cid, "name": c.name, "device": c.device, "model": c.model.name,
                "n_params": c.model.n_params, "n_registos": int(len(c.y)),
                "n_anomalia": int(c.y.sum()), "ecg": c.preview,
            } for c in self.clients],
        }

    def run(self):
        yield self.setup_event()
        for r in range(1, self.cfg.rounds + 1):
            yield from self.round(r)
        yield {"type": "done", "history": self.history}

    def round(self, r: int):
        cfg, soft = self.cfg, self.cfg.mode == "soft"
        yield {"type": "step", "step": "collect", "round": r,
               "info": {c.cid: {"registos": int(len(c.y))} for c in self.clients}}

        # 1. treino local
        for c in self.clients:
            if soft:
                c.model.fit(c.X, c.y, epochs=cfg.local_epochs, class_weight=c.class_weight(),
                            X_ref=self.X_ref, q_ref=self.q_global, alpha=cfg.alpha if self.q_global is not None else 0.0)
            else:
                c.model.set_flat(self.global_w)
                c.model.fit(c.X, c.y, epochs=cfg.local_epochs, class_weight=c.class_weight())
        yield {"type": "step", "step": "train", "round": r,
               "info": {c.cid: {"acc_local": round(float(np.mean(c.model.predict(c.X) == c.y)), 3)} for c in self.clients}}

        # 2. o que cada cliente vai partilhar
        payload = {}
        for c in self.clients:
            payload[c.cid] = c.model.predict_proba(self.X_ref) if soft else c.model.get_flat().copy()
        yield {"type": "step", "step": "share", "round": r, "info": {k: self._show(v) for k, v in payload.items()}}

        # 3. LDP no cliente
        if cfg.ldp:
            for c in self.clients:
                v = payload[c.cid]
                payload[c.cid] = privacy.laplace_soft_labels(v, cfg.eps, self.rng) if soft \
                    else privacy.laplace_weights(v, cfg.eps, cfg.clip, self.rng)
            yield {"type": "step", "step": "ldp", "round": r, "info": {k: self._show(v) for k, v in payload.items()},
                   "budget": privacy.budget(cfg.eps, cfg.n_ref, r, cfg.mode)}

        # 4. Secure Aggregation
        if cfg.secagg:
            for c in self.clients:
                c.sa = secagg.SecAggClient(c.cid)
            pks = {c.cid: c.sa.public_key for c in self.clients}
            sent = {c.cid: c.sa.mask(payload[c.cid], pks, r) for c in self.clients}
            yield {"type": "step", "step": "secagg", "round": r,
                   "info": {c.cid: {"chave_publica": c.sa.fingerprint()} for c in self.clients}}
        else:
            sent = payload

        # 5. envio e agregação: o servidor só tem acesso a `sent`
        seen = {k: self._show(v, masked=cfg.secagg) for k, v in sent.items()}
        total = secagg.aggregate(list(sent.values())) if cfg.secagg else sum(sent.values())
        avg = total / len(self.clients)
        if soft:
            q = np.clip(avg, 1e-3, None)
            self.q_global = q / q.sum(axis=1, keepdims=True)
        else:
            self.global_w = avg
        yield {"type": "step", "step": "aggregate", "round": r, "server_sees": seen,
               "soma": self._show(total), "media": self._show(self.q_global if soft else avg),
               "bytes_por_cliente": self._bytes()}

        # 6. redistribuição
        if not soft:
            for c in self.clients:
                c.model.set_flat(self.global_w)
        yield {"type": "step", "step": "broadcast", "round": r}

        # 7. avaliação e alerta local
        ev = self._evaluate()
        alerts = {}
        for c in self.clients:
            p_an = float(c.model.predict_proba(c.latest)[0, 1])
            alerts[c.cid] = {"p_anomalia": round(p_an, 3), "alerta": p_an >= 0.5, "real_anomalia": c.latest_is_af}
        rec = {"round": r, **ev}
        if cfg.ldp:
            rec["budget"] = privacy.budget(cfg.eps, cfg.n_ref, r, cfg.mode)
        self.history.append(rec)
        yield {"type": "step", "step": "evaluate", "round": r, "eval": ev, "alerts": alerts,
               "local_only": self.local_only, "history": self.history}

    def _show(self, v: np.ndarray, masked: bool = False) -> list:
        """Excerto pequeno para a interface: a linha REF_SHOW (soft labels) ou os 4 primeiros pesos."""
        row = v[REF_SHOW] if v.ndim == 2 else v[:4]
        if masked:
            return [int(x) for x in row]
        return [round(float(x), 4) for x in row]
