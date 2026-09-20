"""系统信息、文件访问、目录浏览。"""
from __future__ import annotations

import pathlib
import platform
import shutil
from importlib import metadata

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import (
    IMAGE_EXTENSIONS,
    KERAS_CODE_DIR,
    PALMLIB_BINARY,
    PROJECT_ROOT,
    PYTHON_BIN,
    WORKSPACE,
    resolve_path,
)
from ..database import get_db
from ..models import Dataset, Gallery, RecognitionLog, RoiJob, TrainJob
from ..services import roi_service, train_service
from ..services.files import is_allowed, media_type
from ..services.runtime import manager

router = APIRouter(prefix="/api/system", tags=["system"])


def _pkg_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _dir_size(path: pathlib.Path, limit: int = 200000) -> int:
    total = 0
    count = 0
    if not path.exists():
        return 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
            count += 1
            if count > limit:
                break
    return total


@router.get("/info")
def system_info():
    return {
        "project_root": str(PROJECT_ROOT),
        "workspace": str(WORKSPACE),
        "keras_code_dir": str(KERAS_CODE_DIR),
        "python_bin": PYTHON_BIN,
        "platform": f"{platform.system()} {platform.machine()}",
        "python_version": platform.python_version(),
        "packages": {
            "tensorflow": _pkg_version("tensorflow"),
            "keras": _pkg_version("keras"),
            "opencv-python": _pkg_version("opencv-python"),
            "scikit-learn": _pkg_version("scikit-learn"),
            "numpy": _pkg_version("numpy"),
        },
        "palmlib": {
            "path": str(PALMLIB_BINARY),
            "ready": roi_service.binary_ready(),
        },
        "models": train_service.MODEL_NAMES,
        "option_spec": train_service.option_spec(),
        "default_params": train_service.default_params(),
        "image_extensions": IMAGE_EXTENSIONS,
        "workspace_size": _dir_size(WORKSPACE),
        "disk_free": shutil.disk_usage(str(WORKSPACE)).free,
    }


@router.get("/stats")
def system_stats(db: Session = Depends(get_db)):
    def job_status_counts(model):
        rows = db.query(model.status, func.count(model.id)).group_by(model.status).all()
        return {status: count for status, count in rows}

    best = (
        db.query(func.min(TrainJob.best_eer)).filter(TrainJob.best_eer.isnot(None)).scalar()
    )
    return {
        "datasets": db.query(func.count(Dataset.id)).scalar() or 0,
        "dataset_images": db.query(func.sum(Dataset.n_images)).scalar() or 0,
        "roi_jobs": db.query(func.count(RoiJob.id)).scalar() or 0,
        "roi_images": db.query(func.sum(RoiJob.succeeded)).scalar() or 0,
        "train_jobs": db.query(func.count(TrainJob.id)).scalar() or 0,
        "train_status": job_status_counts(TrainJob),
        "running_jobs": len([key for key in manager.running_keys() if key.startswith("train:")]),
        "galleries": db.query(func.count(Gallery.id)).scalar() or 0,
        "recognitions": db.query(func.count(RecognitionLog.id)).scalar() or 0,
        "best_eer": best,
        "roi_running": len([key for key in manager.running_keys() if key.startswith("gallery:")]),
    }


@router.get("/browse")
def browse(path: str = Query(default="")):
    """浏览服务器目录，便于登记数据集。"""
    target = resolve_path(path) if path else PROJECT_ROOT
    if not target.is_dir():
        raise HTTPException(400, f"目录不存在：{target}")
    try:
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError as exc:
        raise HTTPException(403, f"没有权限读取：{target}") from exc

    dirs = [{"name": p.name, "path": str(p)} for p in entries if p.is_dir() and not p.name.startswith(".")]
    files = [
        {"name": p.name, "path": str(p)}
        for p in entries
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
    ][:200]
    return {
        "path": str(target),
        "parent": str(target.parent) if target.parent != target else None,
        "dirs": dirs,
        "files": files,
    }


@router.get("/file")
def serve_file(path: str = Query(...), db: Session = Depends(get_db)):
    target = pathlib.Path(path).expanduser()
    if not target.is_file():
        raise HTTPException(404, "文件不存在")
    if not is_allowed(target, db):
        raise HTTPException(403, "该路径不在允许访问的范围内")
    return FileResponse(
        target,
        media_type=media_type(target),
        filename=target.name,
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/download")
def download_file(path: str = Query(...), db: Session = Depends(get_db)):
    target = pathlib.Path(path).expanduser()
    if not target.is_file():
        raise HTTPException(404, "文件不存在")
    if not is_allowed(target, db):
        raise HTTPException(403, "该路径不在允许访问的范围内")
    return FileResponse(target, media_type="application/octet-stream", filename=target.name)
