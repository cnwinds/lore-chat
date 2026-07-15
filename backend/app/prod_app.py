"""Production FastAPI app: API + built frontend SPA."""

from __future__ import annotations

from pathlib import Path

from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from app.main import create_app

app = create_app()

_root = Path(__file__).resolve().parents[2]
_dist = _root / "frontend" / "dist"
_index = _dist / "index.html"
_assets = _dist / "assets"
_BUILD_HINT = "Frontend build not found. Run: lorechat.bat setup && lorechat.bat start"

if _assets.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_assets)), name="spa_assets")


@app.get("/", response_model=None)
def index() -> Response:
    if _index.is_file():
        return FileResponse(_index, headers={"Cache-Control": "no-store"})
    return HTMLResponse(
        status_code=503,
        content=(
            "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"UTF-8\">"
            "<title>Lore Chat</title></head><body>"
            f"<p>{_BUILD_HINT}</p></body></html>"
        ),
        headers={"Cache-Control": "no-store"},
    )
