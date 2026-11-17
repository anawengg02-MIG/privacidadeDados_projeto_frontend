import numpy as np

from fedecg import privacy, secagg
from fedecg.simulation import Config, Simulation


def test_secagg_masks_cancel():
    rng = np.random.default_rng(0)
    clients = [secagg.SecAggClient(c) for c in "ABCD"]
    pks = {c.cid: c.public_key for c in clients}
    values = [rng.normal(size=(5, 2)) for _ in clients]
    masked = [c.mask(v, pks, round_no=3) for c, v in zip(clients, values)]
    # cada contribuição mascarada não se parece com o valor original
    assert not np.allclose(secagg.decode(masked[0]), values[0], atol=1.0)
    # mas a soma é recuperada (a menos do erro de vírgula fixa)
    assert np.allclose(secagg.aggregate(masked), sum(values), atol=1e-4)


def test_masks_change_each_round():
    a, b = secagg.SecAggClient("A"), secagg.SecAggClient("B")
    pks = {"A": a.public_key, "B": b.public_key}
    v = np.zeros(4)
    assert not np.array_equal(a.mask(v, pks, 1), a.mask(v, pks, 2))


def test_laplace_scale():
    rng = np.random.default_rng(1)
    P = np.full((20000, 2), 0.5)
    noisy = privacy.laplace_soft_labels(P, eps=2.0, rng=rng)
    # Laplace(b) tem desvio-padrão b·√2; aqui b = 2/ε = 1
    assert abs((noisy - P).std() - np.sqrt(2)) < 0.05


def test_simulation_runs_and_learns():
    sim = Simulation(Config(rounds=4, ldp=False, secagg=True))
    events = list(sim.run())
    assert events[0]["type"] == "setup" and events[-1]["type"] == "done"
    assert sim.history[-1]["prauc_medio"] > 0.7


def test_secagg_does_not_change_result():
    a = Simulation(Config(rounds=2, ldp=False, secagg=False, seed=7))
    b = Simulation(Config(rounds=2, ldp=False, secagg=True, seed=7))
    list(a.run()), list(b.run())
    assert np.allclose(a.q_global, b.q_global, atol=1e-3)
