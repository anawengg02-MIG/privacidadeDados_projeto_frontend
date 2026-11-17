"""Secure Aggregation com máscaras par-a-par (ideia do protocolo de Bonawitz et al., 2017).

1. Cada cliente gera um par de chaves X25519 e publica a chave pública.
2. Cada par de clientes (i, j) calcula o mesmo segredo partilhado por Diffie-Hellman,
   sem que o servidor o conheça.
3. Desse segredo deriva-se uma máscara pseudoaleatória. O cliente com id menor soma-a e o
   outro subtrai-a. Na soma de todos os clientes as máscaras anulam-se.
4. Os valores são codificados em vírgula fixa módulo 2^32, para o cancelamento ser exato.

Simplificação: não trata desistências de clientes a meio da ronda (no protocolo completo
isso resolve-se com secret sharing das chaves). Fica descrito no README como limitação.
"""
from __future__ import annotations

import hashlib

import numpy as np
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

MOD = 2 ** 32
SCALE = 2 ** 16


def encode(v: np.ndarray) -> np.ndarray:
    return np.mod(np.round(v * SCALE).astype(np.int64), MOD).astype(np.uint64)


def decode(u: np.ndarray) -> np.ndarray:
    s = u.astype(np.int64)
    s = np.where(s >= MOD // 2, s - MOD, s)
    return s / SCALE


class SecAggClient:
    def __init__(self, cid: str):
        self.cid = cid
        self._sk = X25519PrivateKey.generate()
        self.public_key = self._sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    def fingerprint(self) -> str:
        return hashlib.sha256(self.public_key).hexdigest()[:12]

    def _mask(self, peer_pk: bytes, round_no: int, size: int) -> np.ndarray:
        shared = self._sk.exchange(X25519PublicKey.from_public_bytes(peer_pk))
        seed = hashlib.sha256(shared + round_no.to_bytes(4, "big")).digest()
        gen = np.random.Generator(np.random.PCG64(int.from_bytes(seed[:16], "big")))
        return gen.integers(0, MOD, size=size, dtype=np.uint64)

    def mask(self, values: np.ndarray, peers: dict[str, bytes], round_no: int) -> np.ndarray:
        flat = encode(values.ravel())
        for pid, pk in peers.items():
            if pid == self.cid:
                continue
            m = self._mask(pk, round_no, flat.size)
            flat = (flat + m) % MOD if self.cid < pid else (flat + MOD - m) % MOD
        return flat.reshape(values.shape)


def aggregate(masked: list[np.ndarray]) -> np.ndarray:
    """O servidor só consegue somar. As máscaras anulam-se e obtém-se a soma das contribuições."""
    total = np.zeros_like(masked[0], dtype=np.uint64)
    for m in masked:
        total = (total + m) % MOD
    return decode(total)
