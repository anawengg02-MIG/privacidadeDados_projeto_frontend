// Código partilhado pelos três ecrãs: ligação ao backend e pequenas funções de apoio.
const FedECG = (() => {
  const NS = "http://www.w3.org/2000/svg";

  const STEPS = [
    { key: "collect", t: "Recolha do ECG" },
    { key: "train", t: "Treino local" },
    { key: "share", t: "Soft labels" },
    { key: "ldp", t: "Ruído LDP" },
    { key: "secagg", t: "Secure Aggregation" },
    { key: "aggregate", t: "Envio e agregação" },
    { key: "broadcast", t: "Atualização do modelo" },
    { key: "evaluate", t: "Avaliação e alerta" },
  ];

  function svg(tag, attrs = {}, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  const fmt = (x, d = 2) => (x < 0 ? "−" : "+") + Math.abs(x).toFixed(d);
  const pt = (x, d = 2) => Number(x).toFixed(d).replace(".", ",");

  // Cliente escolhido no URL: /wearable?cliente=B
  function clientId() {
    return (new URLSearchParams(location.search).get("cliente") || "B").toUpperCase();
  }
  function setClient(id) {
    const u = new URL(location.href);
    u.searchParams.set("cliente", id);
    location.href = u.toString();
  }

  // Liga ao backend e volta a ligar se a ligação cair.
  function connect(onEvent, onStatus = () => {}) {
    let ws;
    const open = () => {
      ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
      ws.onopen = () => onStatus(true);
      ws.onclose = () => { onStatus(false); setTimeout(open, 2000); };
      ws.onmessage = (m) => onEvent(JSON.parse(m.data));
    };
    open();
    return { send: (obj) => ws && ws.readyState === 1 && ws.send(JSON.stringify(obj)) };
  }

  function statusPill(el) {
    return (ok) => {
      el.className = `pill ${ok ? "ok" : "bad"}`;
      el.textContent = ok ? "ligado ao backend" : "sem ligação ao backend";
    };
  }

  return { STEPS, svg, fmt, pt, clientId, setClient, connect, statusPill };
})();
