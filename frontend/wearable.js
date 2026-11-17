// Ecrã do wearable: smartwatch no pulso (todos os clientes).
(() => {
  const { svg, clientId, setClient, connect, statusPill, pt } = FedECG;
  const id = clientId();
  const root = document.getElementById("dev");
  const sel = document.getElementById("cli");
  sel.value = id;
  sel.addEventListener("change", () => setClient(sel.value));

  const st = { client: null, step: null, alert: null, signal: null };
  let ui = null;

  function build(c) {
    root.innerHTML = "";
    const g = svg("g", {}, root);
    svg("rect", { x: 0, y: 170, width: 330, height: 100, rx: 50, fill: "var(--skin)" }, g);
    svg("ellipse", { cx: 350, cy: 220, rx: 62, ry: 56, fill: "var(--skin)" }, g);
    svg("ellipse", { cx: 340, cy: 168, rx: 26, ry: 14, fill: "var(--skin-2)", transform: "rotate(-20 340 168)" }, g);
    svg("rect", { x: 140, y: 60, width: 100, height: 320, rx: 22, fill: "#2b3640" }, g);
    svg("rect", { x: 100, y: 110, width: 180, height: 220, rx: 44, fill: "var(--device)", stroke: "var(--device-edge)", "stroke-width": 4 }, g);
    svg("rect", { x: 280, y: 180, width: 10, height: 40, rx: 4, fill: "var(--device-edge)" }, g);
    ui = {
      screen: svg("rect", { x: 114, y: 124, width: 152, height: 192, rx: 34, fill: "var(--screen)" }, g),
      box: { x: 124, y: 214, w: 132, amp: 38 },
      title: svg("text", { x: 190, y: 160, "text-anchor": "middle", fill: "var(--fg)", "font-size": 15, "font-weight": 600 }, g),
      bpm: svg("text", { x: 190, y: 284, "text-anchor": "middle", fill: "var(--ecg)", "font-size": 22, "font-family": "var(--mono)" }, g),
      foot: svg("text", { x: 190, y: 304, "text-anchor": "middle", fill: "var(--muted)", "font-size": 11 }, g),
      ble: svg("text", { x: 236, y: 160, fill: "var(--muted)", "font-size": 13 }, g),
    };
    ui.ecg = svg("polyline", { fill: "none", stroke: "var(--ecg)", "stroke-width": 2.4, "stroke-linejoin": "round" }, g);
    ui.ble.textContent = "ᛒ";
    st.bpm = estimateBpm(c.ecg);
    render();
  }

  // Frequência cardíaca a partir dos picos R do sinal enviado pelo backend (100 Hz).
  function estimateBpm(sig) {
    let n = 0;
    for (let i = 1; i < sig.length - 1; i++) if (sig[i] > 0.6 && sig[i] >= sig[i - 1] && sig[i] > sig[i + 1]) n++;
    return Math.round((n * 60) / (sig.length / 100));
  }

  function render() {
    if (!ui) return;
    const c = st.client, alert = st.step === "evaluate" && st.alert?.alerta;
    ui.screen.setAttribute("fill", alert ? "#3a0f12" : "var(--screen)");
    ui.ecg.setAttribute("stroke", alert ? "var(--alert)" : "var(--ecg)");
    ui.title.textContent = alert ? "Anomalia" : st.step === "collect" ? "A medir" : "ECG";
    ui.title.setAttribute("fill", alert ? "var(--alert)" : "var(--fg)");
    ui.bpm.textContent = `${st.bpm} bpm`;
    ui.bpm.setAttribute("fill", alert ? "var(--alert)" : "var(--ecg)");
    ui.foot.textContent = alert ? "Consulte um médico" : "registo de 30 s";
    ui.ble.classList.toggle("ble-on", st.step === "evaluate");
    ui.ble.setAttribute("fill", st.step === "evaluate" ? "var(--ecg)" : "var(--muted)");

    const S = document.getElementById("state"), sub = document.getElementById("sub");
    S.style.color = alert ? "var(--alert)" : "";
    if (!st.step) { S.textContent = `${c.name} · à espera de uma ronda`; return; }
    if (st.step === "collect") { S.textContent = "A medir o ECG e a guardá-lo no wearable"; sub.textContent = "O ECG em bruto nunca sai do wearable."; }
    else if (st.step === "evaluate") {
      S.textContent = alert ? `Alerta: possível anomalia do ritmo (p = ${pt(st.alert.p_anomalia)})` : `Ritmo normal (p(anomalia) = ${pt(st.alert.p_anomalia)})`;
      sub.textContent = alert ? "Alerta informativo. Não substitui a avaliação médica." : "O modelo, melhorado pela federação, corre no wearable. O alerta também é enviado para o telemóvel.";
    } else { S.textContent = `${c.name} · ronda ${st.round} em curso no wearable`; sub.textContent = "O ECG em bruto nunca sai do wearable. Só sai a contribuição protegida."; }
  }

  function frame(now) {
    if (ui && st.client) {
      const sig = st.client.ecg, n = sig.length, off = Math.floor(now / 10) % n, b = ui.box, W = 240, pts = [];
      for (let i = 0; i < W; i += 2) pts.push(`${(b.x + (i * b.w) / W).toFixed(1)},${(b.y - sig[(off + i) % n] * b.amp).toFixed(1)}`);
      ui.ecg.setAttribute("points", pts.join(" "));
    }
    requestAnimationFrame(frame);
  }

  connect((e) => {
    if (e.type === "setup") {
      st.client = e.clients.find((c) => c.id === id) || e.clients[0];
      st.step = null;
      document.title = `FedECG · Wearable · ${st.client.name}`;
      build(st.client);
    } else if (e.type === "step" && st.client) {
      st.step = e.step; st.round = e.round;
      if (e.step === "evaluate") st.alert = e.alerts[st.client.id];
      render();
    }
  }, statusPill(document.getElementById("conn")));
  requestAnimationFrame(frame);
})();
