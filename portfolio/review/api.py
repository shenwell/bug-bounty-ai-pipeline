"""Kanban board API (Phase 1 — portfolio only)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from portfolio.common.config import AppConfig

templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


class MoveCardRequest(BaseModel):
    slug: str
    column_id: str
    position: int = -1
    platform: str | None = None
    card_id: str | None = None


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(title="Portfolio Kanban", version="0.1.0")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/board", response_class=HTMLResponse)
    async def board_page(request: Request):
        from portfolio.kanban import load_board_state

        state = load_board_state(config)
        response = templates.TemplateResponse(
            request,
            "board.html",
            {
                "total": state["total"],
                "new_count": state.get("new_count", 0),
                "initial_state_json": json.dumps(state, ensure_ascii=False),
            },
        )
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        return response

    @app.get("/api/board")
    async def board_api():
        from portfolio.kanban import load_board_state

        return JSONResponse(load_board_state(config), headers={"Cache-Control": "no-store"})

    @app.post("/api/board/move")
    async def board_move(req: MoveCardRequest):
        from portfolio.kanban import move_card

        try:
            return move_card(
                config,
                slug=req.slug,
                column_id=req.column_id,
                position=req.position,
                platform=req.platform,
                card_id_override=req.card_id,
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/board/sync")
    async def board_sync():
        from portfolio.kanban import sync_board_from_dossiers

        return sync_board_from_dossiers(config)

    return app
