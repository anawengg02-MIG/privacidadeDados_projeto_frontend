"""Backend do FedECG: corre a simulação e transmite cada passo a todos os ecrãs ligados.

Os três ecrãs do frontend (wearable, telefone e servidor) ligam-se ao mesmo WebSocket e
recebem os mesmos eventos. Qualquer ecrã que se ligue a meio recebe o estado atual.

Executar (a partir da pasta backend):
    uvicorn app:app --reload
e abrir http://127.0.0.1:8000
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fedecg.simulation import Config, Simulation

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="FedECG")


class Hub:
    """Guarda os ecrãs ligados e a simulação em curso."""

    def __init__(self):
        self.sockets: set[WebSocket] = set()
        self.task: asyncio.Task | None = None
        self.delay = 1.6
        self.snapshot: dict[str, dict] = {}  # último evento de cada tipo, para quem se liga a meio

    async def broadcast(self, event: dict):
        if event["type"] == "setup":
            self.snapshot = {"setup": event}
        elif event["type"] == "step":
            self.snapshot["step"] = event
            if event["step"] in ("aggregate", "evaluate"):
                self.snapshot[event["step"]] = event
        else:
            self.snapshot["fim"] = event
        for ws in list(self.sockets):
            try:
                await ws.send_json(event)
            except Exception:
                self.sockets.discard(ws)

    async def run(self, cfg: Config):
        try:
            sim = Simulation(cfg)
            for event in sim.run():
                await self.broadcast(event)
                await asyncio.sleep(self.delay if event["type"] == "step" else 0.3)
        except asyncio.CancelledError:
            await self.broadcast({"type": "stopped"})
            raise

    def start(self, cfg: Config):
        if self.task and not self.task.done():
            self.task.cancel()
        self.task = asyncio.create_task(self.run(cfg))

    def stop(self):
        if self.task and not self.task.done():
            self.task.cancel()


hub = Hub()


@app.get("/api/config")
def default_config() -> dict:
    return Config().__dict__


@app.post("/api/run")
def run_once(cfg: dict | None = None) -> dict:
    """Corre a simulação completa de uma vez e devolve o histórico (útil para testar o backend sozinho)."""
    sim = Simulation(Config.from_dict(cfg or {}))
    events = list(sim.run())
    return {"local_only": sim.local_only, "history": events[-1]["history"]}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    hub.sockets.add(ws)
    # sincroniza um ecrã que se liga a meio
    for key in ("setup", "aggregate", "evaluate", "step", "fim"):
        if key in hub.snapshot:
            await ws.send_json({**hub.snapshot[key], "replay": True})
    await ws.send_json({"type": "hello", "running": bool(hub.task and not hub.task.done()), "delay": hub.delay})
    try:
        while True:
            msg = await ws.receive_json()
            cmd = msg.get("cmd")
            if cmd == "start":
                hub.delay = float(msg.get("step_delay", hub.delay))
                hub.start(Config.from_dict(msg.get("config", {})))
            elif cmd == "stop":
                hub.stop()
            elif cmd == "speed":
                hub.delay = float(msg.get("step_delay", hub.delay))
    except WebSocketDisconnect:
        hub.sockets.discard(ws)


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


def page(name: str):
    return lambda: FileResponse(FRONTEND / name)


app.get("/")(page("tudo.html"))
app.get("/wearable")(page("wearable.html"))
app.get("/telefone")(page("telefone.html"))
app.get("/servidor")(page("servidor.html"))
app.get("/tudo")(page("tudo.html"))
