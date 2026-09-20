"""MPSNet Web 后端入口。

启动:  .venv/bin/python -m uvicorn app.main:app --reload --port 8000
（工作目录：webapp/backend）
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIST, WORKSPACE, ensure_workspace
from .database import SessionLocal, init_db
from .models import Gallery, RoiJob, TrainJob
from .routers import datasets, presets, recognition, roi, system, training


def _reset_stale_jobs() -> None:
    """服务重启后，上一次残留的“运行中”任务实际已不存在。"""
    db = SessionLocal()
    try:
        for model, final in ((TrainJob, "stopped"), (Gallery, "failed"), (RoiJob, "failed")):
            stale = db.query(model).filter(model.status.in_(["running", "pending"])).all()
            for row in stale:
                row.status = final
                if final != "stopped":
                    row.error = row.error or "服务重启，任务被中断"
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_workspace()
    init_db()
    _reset_stale_jobs()
    yield


app = FastAPI(
    title="MPSNet 掌静脉识别平台",
    description="掌脉 ROI 提取 · 数据集管理 · 深度学习训练 · 性能评估 · 掌脉识别",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (system.router, roi.router, datasets.router, training.router,
               presets.router, recognition.router):
    app.include_router(router)


@app.get("/api/health")
def health():
    return {"status": "ok", "workspace": str(WORKSPACE)}


if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        index = FRONTEND_DIST / "index.html"
        if not index.exists():
            return JSONResponse({"detail": "前端尚未构建，请先执行 npm run build"}, status_code=404)
        return FileResponse(index)

else:

    @app.get("/", include_in_schema=False)
    def dev_hint():
        return {
            "message": "前端未构建。开发模式请访问 Vite 服务 (默认 http://localhost:5173)，"
                       "生产模式请先在 webapp/frontend 执行 npm run build",
            "api_docs": "/docs",
        }
