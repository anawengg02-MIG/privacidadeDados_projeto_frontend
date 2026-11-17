// Ecrã do telemóvel: a app do paciente. Mostra o estado do wearable, as notificações e o histórico.
// O ECG, o treino e as proteções acontecem no wearable; o telemóvel não recebe o ECG.
(() => {
  const { STEPS, clientId, setClient, connect, statusPill, pt, fmt } = FedECG;
  const id = clientId();
  const $ = (x) => document.getElementById(x);
  $("cli").value = id;
  $("cli").addEventListener("change", () => setClient($("cli").value));
  setInterval(() => { $("clock").textContent = new Date().toTimeString().slice(0, 5); }, 1000);

  const st = { setup: null, cfg: null, me: null, ev: null, local: null, hist: [] };

  const bars = (vals, color, classes) => vals.map((v, j) => `
    <div class="bar"><span>${classes[j]}</span>
      <div class="track"><div class="fill" style="width:${Math.max(0, Math.min(1, v)) * 100}%;background:${color}"></div></div>
      <span class="v" style="color:${color}">${fmt(v)}</span></div>`).join("");

  function card(e) {
    const soft = st.cfg.mode !== "fedavg", cls = st.setup.classes, me = st.me;
    const info = e.info?.[me.id];
    switch (e.step) {
      case "collect": return `<b>Wearable a medir o ECG</b><span class="muted">${me.n_registos} registos guardados só no wearable, ${me.n_anomalia} com anomalia. O telemóvel não recebe o ECG.</span>`;
      case "train": return `<b>Treino no wearable · ${me.model}</b><span class="muted">O wearable treina só com os dados deste utilizador${st.cfg.mode !== "fedavg" && e.round > 1 ? ", mais o conhecimento global da ronda anterior" : ""}.</span><span class="big" style="color:var(--ecg)">${Math.round(info.acc_local * 100)}%</span><span class="muted">exatidão nos dados locais</span>`;
      case "share": return soft
        ? `<b>Soft labels</b><span class="muted">Probabilidades no exemplo #${st.setup.ref_show} do conjunto público de referência.</span>${bars(info, "var(--ecg)", cls)}`
        : `<b>Pesos do modelo</b><span class="muted">${me.n_params} parâmetros a enviar.</span><span class="mono">${info.map((v) => fmt(v, 3)).join("  ")}</span>`;
      case "ldp": return soft
        ? `<b>Ruído LDP (ε = ${st.cfg.eps})</b><span class="muted">Laplace com escala 2/ε, aplicado no wearable antes de enviar.</span>${bars(info, "var(--noise)", cls)}`
        : `<b>Ruído LDP (ε = ${st.cfg.eps})</b><span class="muted">Pesos cortados (clip) e com ruído de Laplace.</span><span class="mono" style="color:var(--noise)">${info.map((v) => fmt(v, 2)).join("  ")}</span>`;
      case "secagg": return `<b>Secure Aggregation</b><span class="muted">Chave pública X25519 desta ronda:</span><span class="mono" style="color:var(--mask)">${info.chave_publica}</span><span class="muted">O wearable combinou uma máscara com cada um dos outros ${st.setup.clients.length - 1} clientes. Sozinho, o que envia parece aleatório.</span>`;
      case "aggregate": {
        const seen = e.server_sees[me.id];
        return `<b>Enviado ao servidor</b><span class="big">${(e.bytes_por_cliente / 1024).toFixed(1).replace(".", ",")} KB</span>
          <span class="muted">O servidor recebeu do meu wearable:</span>
          <span class="mono" style="color:${st.cfg.secagg ? "var(--mask)" : st.cfg.ldp ? "var(--noise)" : "var(--fg)"}">${seen.map((v) => st.cfg.secagg ? v : fmt(v, 3)).join("  ")}</span>`;
      }
      case "broadcast": return `<b>Modelo atualizado</b><span class="muted">${soft ? "O wearable recebeu as soft labels médias de todos os clientes e vai destilá-las no seu modelo." : "Recebeu o modelo global (média dos pesos)."}</span>`;
      case "evaluate": {
        const a = e.alerts[me.id], pr = e.eval.prauc_por_cliente[me.id];
        return `<b>${a.alerta ? "Alerta: possível anomalia" : "Ritmo normal"}</b>
          <span class="muted">Probabilidade de anomalia no último registo</span><span class="big" style="color:${a.alerta ? "var(--alert)" : "var(--ecg)"}">${pt(a.p_anomalia)}</span>
          <span class="muted">PR-AUC no teste: <b style="color:var(--fg)">${pt(pr)}</b> · sozinho: ${pt(st.local)}</span>
          ${a.alerta ? '<span class="muted">Alerta informativo. Consulte um médico.</span>' : ""}`;
      }
    }
    return "";
  }

  function render() {
    const e = st.ev, cfg = st.cfg;
    const idx = e ? STEPS.findIndex((s) => s.key === e.step) : -1;
    const skip = (k) => (k === "ldp" && !cfg.ldp) || (k === "secagg" && !cfg.secagg);
    $("steps").innerHTML = STEPS.map((s, i) => {
      const t = s.key === "share" && cfg.mode === "fedavg" ? "Pesos do modelo" : s.t;
      return `<li class="${skip(s.key) ? "skip" : i === idx ? "now" : i < idx ? "done" : ""}">${t}</li>`;
    }).join("");
    $("badges").innerHTML = [
      `<span class="pill ok">ECG fica no wearable</span>`,
      cfg.ldp ? `<span class="pill warn">LDP ε = ${cfg.eps}</span>` : `<span class="pill bad">sem LDP</span>`,
      cfg.secagg ? `<span class="pill mask">Secure Aggregation</span>` : `<span class="pill bad">sem SA</span>`,
    ].join("");
    if (!e) return;
    const s = STEPS[idx], alert = e.step === "evaluate" && e.alerts[st.me.id].alerta;
    $("round").textContent = `ronda ${e.round} de ${cfg.rounds}`;
    $("phaseT").textContent = alert ? "Possível anomalia detetada" : (s.key === "share" && cfg.mode === "fedavg" ? "Pesos do modelo" : s.t);
    $("phase").classList.toggle("alert", alert);
    $("card").innerHTML = card(e);
    $("hist").innerHTML = st.hist.length
      ? "<b>Histórico</b>" + st.hist.slice().reverse().map((h) => `<div class="${h.alerta ? "a" : ""}">${h.hora} · ronda ${h.round} · ${h.alerta ? "Alerta: possível anomalia" : "Ritmo normal"} (${pt(h.p)})</div>`).join("")
      : "";
  }

  connect((e) => {
    if (e.type === "setup") {
      st.setup = e; st.cfg = e.config; st.ev = null; st.hist = [];
      st.me = e.clients.find((c) => c.id === id) || e.clients[0];
      st.local = e.local_only[st.me.id];
      $("who").textContent = `App de ${st.me.name}`;
      $("whoSub").textContent = `ligada ao smartwatch por Bluetooth (recebe o estado e os alertas, não o ECG)`;
      document.title = `FedECG · Telefone · ${st.me.name}`;
      $("card").innerHTML = '<span class="muted">À espera da primeira ronda…</span>';
      render();
    } else if (e.type === "step" && st.me) {
      st.ev = e;
      if (e.step === "evaluate") { const a = e.alerts[st.me.id]; st.hist.push({ round: e.round, alerta: a.alerta, p: a.p_anomalia, hora: new Date().toTimeString().slice(0, 5) }); }
      render();
    } else if (e.type === "done") {
      $("phaseT").textContent = "Treino federado concluído";
    }
  }, statusPill($("conn")));
})();
