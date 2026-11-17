// Ecrã do servidor de coordenação: controla a simulação e mostra apenas resultados agregados.
(() => {
  const { STEPS, svg, connect, statusPill, pt, fmt } = FedECG;
  const $ = (x) => document.getElementById(x);
  const st = { setup: null, cfg: null, agg: null, history: [], step: null };

  // ---------- máquina ----------
  const rack = $("rack"), leds = [];
  svg("rect", { x: 30, y: 6, width: 160, height: 288, rx: 12, fill: "var(--device)", stroke: "var(--device-edge)", "stroke-width": 2 }, rack);
  for (let i = 0; i < 5; i++) {
    const y = 20 + i * 36;
    svg("rect", { x: 42, y, width: 136, height: 28, rx: 4, fill: "#141c22", stroke: "#2b3843" }, rack);
    for (let k = 0; k < 7; k++) svg("rect", { x: 52 + k * 9, y: y + 12, width: 5, height: 5, rx: 1, fill: "#2b3843" }, rack);
    leds.push(svg("circle", { cx: 164, cy: y + 14, r: 4, fill: "var(--ecg)", class: "led" }, rack));
  }
  svg("rect", { x: 42, y: 206, width: 136, height: 76, rx: 6, fill: "var(--screen)" }, rack);
  const scr = [0, 1, 2, 3].map((i) => svg("text", { x: 52, y: 226 + i * 15, fill: "var(--muted)", "font-size": 10, "font-family": "var(--mono)" }, rack));
  const setScreen = (lines, color = "var(--muted)") => scr.forEach((t, i) => { t.textContent = lines[i] || ""; t.setAttribute("fill", i === 0 ? "var(--fg)" : color); });
  setScreen(["à espera", "de clientes…"]);

  // ---------- controlos ----------
  const ws = connect(onEvent, statusPill($("conn")));
  $("eps").addEventListener("input", (e) => { $("epsOut").textContent = Number(e.target.value).toFixed(1); });
  $("speed").addEventListener("input", (e) => ws.send({ cmd: "speed", step_delay: Number(e.target.value) }));
  $("cfg").addEventListener("submit", (e) => {
    e.preventDefault();
    ws.send({
      cmd: "start", step_delay: Number($("speed").value),
      config: {
        mode: document.querySelector('input[name="mode"]:checked').value,
        ldp: $("ldp").checked, eps: Number($("eps").value), secagg: $("secagg").checked, rounds: Number($("rounds").value),
      },
    });
  });
  $("stop").addEventListener("click", () => ws.send({ cmd: "stop" }));
  const running = (r) => { $("start").textContent = r ? "Reiniciar" : "Iniciar"; $("stop").disabled = !r; };
  running(false);

  // ---------- consola ----------
  function log(msg) {
    const t = new Date().toTimeString().slice(0, 8);
    const d = document.createElement("div");
    d.innerHTML = `<b>${t}</b>  ${msg}`;
    $("term").prepend(d);
    while ($("term").children.length > 200) $("term").lastChild.remove();
  }

  // ---------- tabela ----------
  function table() {
    const a = st.agg, cfg = st.cfg, soft = cfg.mode !== "fedavg";
    const heads = soft ? st.setup.classes : ["w₁", "w₂", "w₃", "w₄"];
    $("recvSub").textContent = soft ? `Linha #${st.setup.ref_show} das ${st.setup.n_ref} do conjunto de referência${a ? ` · ronda ${a.round}` : ""}` : "4 primeiros pesos do modelo";
    let h = `<thead><tr><th></th>${heads.map((x) => `<th>${x}</th>`).join("")}</tr></thead><tbody>`;
    h += `<tr class="sum"><td>Soma</td>${heads.map((_, j) => `<td>${a ? fmt(a.soma[j], 3) : "—"}</td>`).join("")}</tr>`;
    h += `<tr class="sum"><td>Média (global)</td>${heads.map((_, j) => `<td>${a ? a.media[j].toFixed(3) : "—"}</td>`).join("")}</tr></tbody>`;
    $("tbl").innerHTML = h;
    $("tblNote").textContent = !a ? "" : cfg.secagg ? "Só a soma de todas as contribuições é conhecida: as máscaras anulam-se e nenhuma contribuição individual fica visível."
      : "Só são mostrados os valores agregados.";
  }

  // ---------- gráfico ----------
  function chart() {
    const c = $("chart"); c.innerHTML = "";
    const W = 320, H = 160, L = 30, R = 12, T = 10, B = 24, n = Math.max(st.cfg?.rounds || 8, 2);
    const lo = st.setup ? Object.values(st.setup.local_only) : [];
    const loMean = lo.length ? lo.reduce((a, b) => a + b, 0) / lo.length : null;
    const vals = st.history.map((r) => r.prauc_medio).concat(lo);
    const y0 = Math.max(0, Math.min(0.5, Math.floor((Math.min(...vals, 1) - 0.03) * 20) / 20));
    const X = (i) => L + ((i - 1) * (W - L - R)) / (n - 1), Y = (v) => T + ((1 - v) / (1 - y0)) * (H - T - B);
    [y0, (y0 + 1) / 2, 1].forEach((v) => {
      svg("line", { x1: L, x2: W - R, y1: Y(v), y2: Y(v), class: "axis", "stroke-dasharray": v === y0 ? "" : "2 3" }, c);
      svg("text", { x: L - 6, y: Y(v) + 3, class: "axis-label", "text-anchor": "end" }, c).textContent = pt(v, 2);
    });
    svg("text", { x: L, y: H - 6, class: "axis-label" }, c).textContent = "ronda 1";
    svg("text", { x: W - R, y: H - 6, class: "axis-label", "text-anchor": "end" }, c).textContent = `ronda ${n}`;
    if (loMean != null) {
      svg("line", { x1: L, x2: W - R, y1: Y(loMean), y2: Y(loMean), stroke: "var(--muted)", "stroke-dasharray": "5 4" }, c);
      svg("text", { x: W - R, y: Y(loMean) - 4, class: "axis-label", "text-anchor": "end" }, c).textContent = "cada um sozinho";
    }
    const h = st.history;
    if (h.length) {
      svg("polyline", { points: h.map((r) => `${X(r.round)},${Y(r.prauc_medio)}`).join(" "), fill: "none", stroke: "var(--ecg)", "stroke-width": 2 }, c);
      h.forEach((r, i) => svg("circle", { cx: X(r.round), cy: Y(r.prauc_medio), r: i === h.length - 1 ? 4 : 2.5, fill: "var(--ecg)" }, c));
      const last = h[h.length - 1];
      $("chartNote").textContent = `Ronda ${last.round}: PR-AUC médio ${pt(last.prauc_medio, 3)} (referência, cada cliente sozinho: ${pt(loMean, 3)}).`;
    } else $("chartNote").textContent = loMean != null ? `Linha tracejada: PR-AUC médio se cada cliente treinasse sozinho (${pt(loMean, 3)}).` : "";
  }


  // ---------- eventos ----------
  // A consola só mostra o que diz respeito ao modelo agregado (nada individual de cada cliente).
  const MSG = {
    collect: () => "nova ronda iniciada",
    aggregate: () => st.cfg.secagg ? "soma das contribuições calculada (máscaras anuladas)" : "soma das contribuições calculada",
    broadcast: () => "modelo global atualizado e enviado aos clientes",
    evaluate: (e) => `PR-AUC médio do modelo agregado = ${pt(e.eval.prauc_medio, 3)}`,
  };

  function onEvent(e) {
    if (e.type === "hello") { running(e.running); return; }
    if (e.type === "setup") {
      st.setup = e; st.cfg = e.config; st.agg = null; st.history = [];
      table(); chart();
      if (!e.replay) { log(`simulação iniciada · ${st.cfg.mode === "fedavg" ? "FedAvg" : "soft labels"} · LDP ${st.cfg.ldp ? "ε=" + st.cfg.eps : "desligada"} · SA ${st.cfg.secagg ? "ligada" : "desligada"}`); running(true); }
      setScreen(["clientes", `${e.clients.length} ligados`]);
      $("from").innerHTML = e.clients.map((c) => `<li class="c">${c.name}</li>`).join("");
      return;
    }
    if (e.type === "done" || e.type === "stopped") { running(false); log(e.type === "done" ? "treino federado concluído" : "simulação parada"); setScreen(["terminado"]); return; }
    if (e.type !== "step" || !st.setup) return;
    st.step = e.step;
    $("roundTxt").textContent = `ronda ${e.round} de ${st.cfg.rounds}`;
    const busy = e.step === "aggregate" || e.step === "broadcast";
    leds.forEach((l) => l.classList.toggle("busy", busy));
    if (e.step === "aggregate") {
      st.agg = e; table();
      setScreen(["Σ recebido", ...e.media.slice(0, 2).map((v, j) => `${(st.setup.classes[j] || "w" + (j + 1)).padEnd(7)}${v.toFixed(3)}`)], "var(--ecg)");
    } else if (e.step === "evaluate") {
      st.history = e.history; chart();
      setScreen(["PR-AUC médio", pt(e.eval.prauc_medio, 3)], "var(--ecg)");
    } else if (e.step === "collect") {
      setScreen([`ronda ${e.round}`, "à espera das", "contribuições…"]);
    }
    if (!e.replay && MSG[e.step]) log(`ronda ${e.round} · ${MSG[e.step](e)}`);
  }
})();
