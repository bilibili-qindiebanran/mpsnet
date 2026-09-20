"""掌脉 ROI 提取相关接口。"""
from __future__ import annotations

import json
import pathlib
import shutil
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from ..config import WORKSPACE_DIRS, resolve_path
from ..database import get_db
from ..models import RoiJob
from ..schemas import RoiExtractRequest, RoiJobOut
from ..services import roi_service

router = APIRouter(prefix="/api/roi", tags=["roi"])


@router.get("/status")
def roi_status():
    """palmlib 是否就绪。"""
    ready = roi_service.binary_ready()
    message = "ROI 提取模块已就绪" if ready else "未找到 palmlib，可点击“编译模块”自动构建"
    return {"ready": ready, "message": message}


@router.post("/build")
def build_palmlib():
    try:
        roi_service.ensure_binary()
        return {"ready": True, "message": "编译成功"}
    except roi_service.RoiError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/extract", response_model=RoiJobOut)
def extract_from_path(payload: RoiExtractRequest, db: Session = Depends(get_db)):
    source = resolve_path(payload.source_path)
    if not source.exists():
        raise HTTPException(400, f"源路径不存在：{source}")

    job = RoiJob(
        name=payload.name or source.name,
        source_type="directory" if source.is_dir() else "file",
        source_path=str(source),
        roi_size=payload.roi_size,
        save_debug=payload.save_debug,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    job.output_dir = str(roi_service.job_output_dir(job.id))
    db.commit()
    db.refresh(job)

    roi_service.start_job(job.id)
    return job


@router.post("/upload", response_model=RoiJobOut)
async def extract_from_upload(
    files: list[UploadFile] = File(...),
    name: str = Form("上传图片提取"),
    roi_size: int = Form(128),
    save_debug: bool = Form(False),
    relative_paths: str = Form("[]"),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(400, "没有收到文件")

    try:
        relatives = json.loads(relative_paths) if relative_paths else []
    except json.JSONDecodeError:
        relatives = []

    token = uuid.uuid4().hex[:12]
    upload_dir = WORKSPACE_DIRS["uploads"] / token
    upload_dir.mkdir(parents=True, exist_ok=True)

    for index, upload in enumerate(files):
        relative = ""
        if index < len(relatives) and relatives[index]:
            relative = str(relatives[index])
        target = pathlib.Path(relative) if relative else pathlib.Path(upload.filename or f"image_{index}.png")
        target = target if target.is_absolute() is False else pathlib.Path(target.name)
        # 防止越界写入
        safe_parts = [part for part in target.parts if part not in ("..", ".", "/")]
        destination = upload_dir.joinpath(*safe_parts) if safe_parts else upload_dir / f"image_{index}.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)

    job = RoiJob(
        name=name,
        source_type="upload",
        source_path=str(upload_dir),
        roi_size=roi_size,
        save_debug=save_debug,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    job.output_dir = str(roi_service.job_output_dir(job.id))
    db.commit()
    db.refresh(job)

    roi_service.start_job(job.id)
    return job


@router.get("/jobs")
def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(RoiJob).order_by(RoiJob.id.desc())
    total = query.count()
    items = query.offset(offset).limit(limit).all()
    return {
        "total": total,
        "items": [RoiJobOut.model_validate(item).model_dump() for item in items],
    }


@router.get("/jobs/{job_id}", response_model=RoiJobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(RoiJob, job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    return job


@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(RoiJob, job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    output = pathlib.Path(job.output_dir) if job.output_dir else None
    db.delete(job)
    db.commit()
    if output and output.exists() and WORKSPACE_DIRS["roi"] in output.parents:
        shutil.rmtree(output, ignore_errors=True)
    return {"ok": True, "deleted_at": datetime.now().isoformat()}
