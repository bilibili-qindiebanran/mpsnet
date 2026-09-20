"""训练任务接口：创建、启动、实时进度、结果查询。"""
from __future__ import annotations

import pathlib
import shutil
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..config import WORKSPACE_DIRS
from ..database import SessionLocal, get_db
from ..models import Artifact, Dataset, FoldResult, TrainJob
from ..schemas import ArtifactOut, FoldResultOut, TrainJobCreate, TrainJobDetail, TrainJobOut
from ..services import train_service
from ..services.events import event_stream

router = APIRouter(prefix="/api/train", tags=["training"])


@router.get("/options")
def train_options():
    return {
        "models": train_service.MODEL_NAMES,
        "option_spec": train_service.option_spec(),
        "default_params": train_service.default_params(),
        "presets_example": {
            "快速验证": {"warmup_epochs": 3, "fine_tune_epochs": 3, "n_folds": 2, "warmup_batch_size": 8,
                     "fine_tune_batch_size": 8},
        },
    }


def _snapshot(job_id: int) -> dict | None:
    db = SessionLocal()
    try:
        job = db.get(TrainJob, job_id)
        if job is None:
            return None
        proc = train_service.manager.get(f"train:{job_id}")
        return {
            "status": job.status,
            "progress": job.progress or {},
            "error": job.error,
            "best_eer": job.best_eer,
            "avg_eer": job.avg_eer,
            "log": proc.tail(200) if proc else "",
        }
    finally:
        db.close()


@router.post("/jobs", response_model=TrainJobOut)
def create_job(payload: TrainJobCreate, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, payload.dataset_id)
    if dataset is None:
        raise HTTPException(400, "数据集不存在")
    if dataset.n_classes < 2:
        raise HTTPException(400, "数据集至少需要 2 个类别才能训练")

    subfolders = [p.name for p in pathlib.Path(dataset.path).iterdir() if p.is_dir()]
    if not subfolders:
        raise HTTPException(400, "数据集目录下没有 Palm_ID 子目录，请检查数据布局")

    params = dict(payload.params or {})
    extra_ids = params.pop("extra_train_dataset_ids", []) or []
    clean = train_service.sanitize_params(params)
    if "image_extension" not in params:
        # 默认跟随数据集自身的识别后缀（ROI 结果可能是 '_roi.png'）
        clean["image_extension"] = dataset.image_extension
    if extra_ids:
        clean["extra_train_dataset_ids"] = extra_ids

    if payload.n_sessions == 2 and len(subfolders) and (dataset.n_images // len(subfolders)) % 2 != 0:
        raise HTTPException(
            400,
            "会话数为 2 时每个类别的样本数必须是偶数（每个会话取一半样本）",
        )

    job = TrainJob(
        name=payload.name or f"{payload.model_name} @ {dataset.name}",
        dataset_id=payload.dataset_id,
        test_folder=train_service.safe_alias(dataset.name),
        n_sessions=payload.n_sessions,
        model_name=payload.model_name,
        params=clean,
        retrain_softmax=payload.retrain_softmax,
        retrain_fine_tune=payload.retrain_fine_tune,
        convert_to_tflite=payload.convert_to_tflite,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.post("/jobs/{job_id}/start", response_model=TrainJobOut)
def start_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(TrainJob, job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    if train_service.is_running(job_id):
        raise HTTPException(400, "任务已在运行中")
    train_service.start_job(job_id)
    db.refresh(job)
    return job


@router.post("/run", response_model=TrainJobOut)
def create_and_run(payload: TrainJobCreate, db: Session = Depends(get_db)):
    """一步创建并立即启动训练任务。"""
    job = create_job(payload, db)
    train_service.start_job(job.id)
    db.refresh(job)
    return job


@router.post("/jobs/{job_id}/stop")
def stop_job(job_id: int):
    if not train_service.stop_job(job_id):
        raise HTTPException(400, "任务未在运行")
    return {"ok": True}


@router.get("/jobs")
def list_jobs(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(TrainJob)
    if status:
        query = query.filter(TrainJob.status == status)
    query = query.order_by(TrainJob.id.desc())
    total = query.count()
    items = query.offset(offset).limit(limit).all()
    result = []
    for job in items:
        data = TrainJobOut.model_validate(job).model_dump()
        dataset = db.get(Dataset, job.dataset_id) if job.dataset_id else None
        data["dataset_name"] = dataset.name if dataset else None
        data["n_folds_done"] = len([f for f in job.folds if f.eer is not None])
        result.append(data)
    return {"total": total, "items": result}


@router.get("/jobs/{job_id}", response_model=TrainJobDetail)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(TrainJob, job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    return job


@router.get("/jobs/{job_id}/events")
def job_events(job_id: int):
    return event_stream(lambda: _snapshot(job_id))


@router.post("/jobs/{job_id}/reparse", response_model=TrainJobDetail)
def reparse_job(job_id: int, db: Session = Depends(get_db)):
    """重新解析 results 目录，用于刷新产物索引 / 兼容旧版本解析结果。"""
    job = db.get(TrainJob, job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    if not job.output_dir or not pathlib.Path(job.output_dir).is_dir():
        raise HTTPException(400, "该任务还没有结果目录")

    summary = train_service.parse_output(pathlib.Path(job.output_dir), job)
    job.best_eer = summary.get("best_eer")
    job.avg_eer = summary.get("avg_eer")
    progress = dict(job.progress or {})
    progress["folds"] = summary.get("folds", {})
    job.progress = progress
    train_service.persist_results(db, job, summary)
    db.commit()
    db.refresh(job)
    return job


@router.get("/jobs/{job_id}/log")
def job_log(job_id: int, db: Session = Depends(get_db)):
    job = db.get(TrainJob, job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    proc = train_service.manager.get(f"train:{job_id}")
    log = proc.tail(500) if proc else ""
    if not log and job.log_path and pathlib.Path(job.log_path).exists():
        lines = pathlib.Path(job.log_path).read_text(encoding="utf-8", errors="ignore").splitlines()
        log = "\n".join(lines[-500:])
    return {"status": job.status, "log": log, "progress": job.progress or {}, "error": job.error}


@router.get("/jobs/{job_id}/folds")
def job_folds(job_id: int, db: Session = Depends(get_db)):
    job = db.get(TrainJob, job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    folds = sorted(job.folds, key=lambda f: f.fold)
    return {
        "total": len(folds),
        "items": [FoldResultOut.model_validate(f).model_dump() for f in folds],
        "best_eer": job.best_eer,
        "avg_eer": job.avg_eer,
    }


@router.get("/jobs/{job_id}/artifacts")
def job_artifacts(job_id: int, db: Session = Depends(get_db)):
    job = db.get(TrainJob, job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    items = sorted(job.artifacts, key=lambda a: (a.kind, a.name))
    return {
        "total": len(items),
        "items": [ArtifactOut.model_validate(a).model_dump() for a in items],
        "output_dir": job.output_dir,
    }


@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, remove_files: bool = Query(False), db: Session = Depends(get_db)):
    job = db.get(TrainJob, job_id)
    if job is None:
        raise HTTPException(404, "任务不存在")
    if train_service.is_running(job_id):
        raise HTTPException(400, "任务正在运行，请先停止")

    base = WORKSPACE_DIRS["jobs"] / str(job_id)
    db.query(FoldResult).filter(FoldResult.job_id == job_id).delete()
    db.query(Artifact).filter(Artifact.job_id == job_id).delete()
    db.delete(job)
    db.commit()
    if remove_files:
        shutil.rmtree(base, ignore_errors=True)
    return {"ok": True, "deleted_files": remove_files, "deleted_at": datetime.now().isoformat()}
