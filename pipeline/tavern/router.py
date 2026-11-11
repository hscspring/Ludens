from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pipeline.tavern.api import TavernService, TavernSession
from pipeline.tavern.data_model import Action, Playback, SceneCreate


class TavernApp:
    def __init__(self, service: TavernService):
        self.service = service
        self.static = Path(__file__).parent / "static"
        self.app = FastAPI(title="Ludens · Roleplay")
        self.app.middleware("http")(self.guard_play)
        self.app.add_api_route("/api/play/{ticket}", service.play_queue.touch, methods=["POST"])
        self.app.add_api_route("/api/play/{ticket}/leave", service.play_queue.leave, methods=["POST"])
        self.app.mount("/static", StaticFiles(directory=self.static), name="static")
        self.app.add_api_route("/", self.index, methods=["GET"])
        self.app.add_api_route("/api/stories", self.service.stories, methods=["GET"])
        self.app.add_api_route("/create", self.creation_page, methods=["GET"])
        self.app.add_api_route("/api/stories/create", self.create_story, methods=["POST"])
        self.app.add_api_route("/api/stories/creation/{identifier}", self.creation_status, methods=["GET"])
        self.app.add_api_route("/api/session", self.create, methods=["POST"])
        self.app.add_api_route("/api/session/{session_id}", self.state, methods=["GET"])
        self.app.add_api_route("/api/session/{session_id}/act", self.act, methods=["POST"])
        self.app.add_api_route("/api/session/{session_id}/replay", self.replay, methods=["POST"])
        self.app.add_api_route("/api/session/{session_id}/replay/video", self.video, methods=["GET"])
        self.app.add_api_route("/api/session/{session_id}/speech/{seq}", self.speech, methods=["GET"])
        self.app.add_api_route("/api/session/{session_id}/playback", self.playback, methods=["POST"])
        self.app.add_api_route("/api/session/{session_id}/events/{seq}/video", self.event_video, methods=["POST"])
        self.app.add_api_route("/api/session/{session_id}/events/{seq}/image", self.event_image, methods=["GET"])
        if service.video:
            self.app.mount("/live-assets", StaticFiles(directory=service.video.root / "media"), name="live-assets")

    async def guard_play(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        path = request.url.path
        if (self.service.story and request.method == "POST"
                and (path == "/api/session" or path.startswith("/api/session/"))
                and not self.service.play_queue.admitted(request.headers.get("X-Play-Ticket", ""))):
            return JSONResponse({"detail": "请等待游玩名额，轮到你后即可继续。"}, status_code=429)
        return await call_next(request)

    def index(self) -> FileResponse:
        page = self.static / "roleplay/index.html" if self.service.story else self.static / "index.html"
        return FileResponse(page, headers={"Cache-Control": "no-store"})

    def creation_page(self) -> FileResponse:
        return FileResponse(self.static / "roleplay/create.html", headers={"Cache-Control": "no-store"})

    def create_story(self, source: SceneCreate) -> dict:
        if not self.service.creator:
            raise HTTPException(503, "场景创建服务尚未启用。")
        try:
            return self.service.creator.submit(source)
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc

    def creation_status(self, identifier: str) -> dict:
        if not self.service.creator:
            raise HTTPException(503, "场景创建服务尚未启用。")
        try:
            return self.service.creator.status(identifier)
        except KeyError as exc:
            raise HTTPException(404, "找不到这次创建记录。") from exc

    def create(self, scene: Literal["tavern", "crate", "crate_minimax", "roleplay"] = "tavern",
               story_id: str = "hozumi_car") -> dict:
        try:
            return self.service.create(scene, story_id).snapshot()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    def playback(self, session_id: str, playback: Playback) -> dict:
        try:
            return self.session(session_id).playback(playback)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    def event_video(self, session_id: str, seq: int) -> dict:
        try:
            return self.session(session_id).request_video(seq)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    def event_image(self, session_id: str, seq: int, rendered: bool = True) -> FileResponse:
        try:
            return FileResponse(self.session(session_id).event_image(seq, rendered=rendered), media_type="image/png")
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    def speech(self, session_id: str, seq: int) -> FileResponse:
        event = next((e for e in self.session(session_id).snapshot()["events"] if e["seq"] == seq), None)
        if not event or event.get("speech", {}).get("status") != "ready":
            raise HTTPException(404, "这句语音尚未准备好。")
        return FileResponse(event["speech"]["path"], media_type="audio/wav")

    def session(self, session_id: str) -> TavernSession:
        try:
            return self.service.get(session_id)
        except KeyError as exc:
            raise HTTPException(404, "这次经历已不在服务中，请重新进入故事。") from exc

    def state(self, session_id: str) -> dict:
        return self.session(session_id).snapshot()

    def act(self, session_id: str, action: Action) -> dict:
        try:
            return self.session(session_id).act(action)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    def replay(self, session_id: str) -> dict:
        try:
            return self.session(session_id).start_replay()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    def video(self, session_id: str) -> FileResponse:
        replay = self.session(session_id).snapshot()["replay"]
        if replay["status"] != "ready" or replay.get("format") == "events":
            raise HTTPException(409, "短片还没有准备好。")
        return FileResponse(replay["path"], media_type="video/mp4")
