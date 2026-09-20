"""掌脉识别 / 验证接口。"""
from __future__ import annotations

import pathlib
import shutil
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from ..config import WORKSPACE_DIRS
from ..database import SessionLocal, get_db
from ..models import Artifact, Dataset, Gallery, RecognitionLog, TrainJob
from ..schemas import GalleryCreate, GalleryOut, RecognitionLogOut
from ..services import recognition_service, train_service
from ..services.events import event_stream

router = APIRouter(prefix="/api/recognition", tags=["recognition"])


def _snapshot(gallery_id: int) -> dict | None:
    db = SessionLocal()
    try:
        gallery = db.get(Gallery, gallery_id)
        if gallery is None:
            return None
        proc = train_service.manager.get(f"gallery:{gallery_id}")
        return {
            "status": gallery.status,
            "progress": gallery.path if str(gallery.path).startswith("progress:") else "",
            "n_samples": gallery.n_samples,
            "n_classes": gallery.n_classes,
            "embedding_dim": gallery.embedding_dim,
            "error": gallery.error,
            "log": proc.tail(120) if proc else "",
        }
    finally:
        db.close()


@router.get("/galleries")
def list_galleries(db: Session = Depends(get_db)):
    items = db.query(Gallery).order_by(Gallery.id.desc()).all()
    result = []
    for item in items:
        data = GalleryOut.model_validate(item).model_dump()
        job = db.get(TrainJob, item.job_id) if item.job_id else None
        dataset = db.get(Dataset, item.dataset_id) if item.dataset_id else None
        data["job_name"] = job.name if job else None
        data["dataset_name"] = dataset.name if dataset else None
        data["threshold"] = recognition_service.default_threshold(db, job) if job else None
        result.append(data)
    return {"total": len(result), "items": result}


@router.post("/galleries", response_model=GalleryOut)
def create_gallery(payload: GalleryCreate, db: Session = Depends(get_db)):
    job = db.get(TrainJob, payload.job_id)
    if job is None:
        raise HTTPException(400, "训练任务不存在")
    dataset = db.get(Dataset, payload.dataset_id)
    if dataset is None:
        raise HTTPException(400, "数据集不存在")
    try:
        recognition_service.resolve_model_path(db, job)
    except recognition_service.RecognitionError as exc:
        raise HTTPException(400, str(exc)) from exc

    gallery = Gallery(
        name=payload.name or f"{job.model_name} · {dataset.name}",
        job_id=payload.job_id,
        dataset_id=payload.dataset_id,
        model_name=job.model_name,
        status="pending",
    )
    db.add(gallery)
    db.commit()
    db.refresh(gallery)
    return gallery


@router.post("/galleries/{gallery_id}/start", response_model=GalleryOut)
def start_gallery(gallery_id: int, db: Session = Depends(get_db)):
    gallery = db.get(Gallery, gallery_id)
    if gallery is None:
        raise HTTPException(404, "识别库不存在")
    recognition_service.start_gallery(gallery_id)
    db.refresh(gallery)
    return gallery


@router.post("/galleries/run", response_model=GalleryOut)
def create_and_run(payload: GalleryCreate, db: Session = Depends(get_db)):
    gallery = create_gallery(payload, db)
    recognition_service.start_gallery(gallery.id)
    db.refresh(gallery)
    return gallery


@router.get("/galleries/{gallery_id}")
def get_gallery(gallery_id: int, db: Session = Depends(get_db)):
    gallery = db.get(Gallery, gallery_id)
    if gallery is None:
        raise HTTPException(404, "识别库不存在")
    data = GalleryOut.model_validate(gallery).model_dump()
    job = db.get(TrainJob, gallery.job_id) if gallery.job_id else None
    data["threshold"] = recognition_service.default_threshold(db, job) if job else None
    data["job_name"] = job.name if job else None
    return data


@router.get("/galleries/{gallery_id}/events")
def gallery_events(gallery_id: int):
    return event_stream(lambda: _snapshot(gallery_id))


@router.get("/galleries/{gallery_id}/identities")
def gallery_identities(gallery_id: int, limit: int = Query(200, ge=1, le=2000)):
    try:
        items = recognition_service.gallery_identities(gallery_id, limit)
    except recognition_service.RecognitionError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"total": len(items), "items": items}


def _save_probe(upload: UploadFile) -> pathlib.Path:
    token = uuid.uuid4().hex[:12]
    directory = WORKSPACE_DIRS["uploads"] / f"probe_{token}"
    directory.mkdir(parents=True, exist_ok=True)
    suffix = pathlib.Path(upload.filename or "probe.png").suffix or ".png"
    target = directory / f"probe{suffix}"
    with target.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle)
    return target


@router.post("/galleries/{gallery_id}/identify")
def identify(
    gallery_id: int,
    file: UploadFile = File(...),
    topk: int = Form(5),
    roi_size: int = Form(128),
    db: Session = Depends(get_db),
):
    if db.get(Gallery, gallery_id) is None:
        raise HTTPException(404, "识别库不存在")
    probe = _save_probe(file)
    try:
        result = recognition_service.identify(db, gallery_id, probe, topk=topk, roi_size=roi_size)
    except recognition_service.RecognitionError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"识别失败：{exc}") from exc
    result["probe_path"] = str(probe)
    return result


@router.post("/galleries/{gallery_id}/verify")
def verify(
    gallery_id: int,
    file: UploadFile = File(...),
    claim: str = Form(...),
    threshold: float | None = Form(None),
    roi_size: int = Form(128),
    db: Session = Depends(get_db),
):
    if db.get(Gallery, gallery_id) is None:
        raise HTTPException(404, "识别库不存在")
    probe = _save_probe(file)
    try:
        result = recognition_service.verify(
            db, gallery_id, probe, claim=claim, threshold=threshold, roi_size=roi_size
        )
    except recognition_service.RecognitionError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"验证失败：{exc}") from exc
    result["probe_path"] = str(probe)
    return result


@router.delete("/galleries/{gallery_id}")
def delete_gallery(gallery_id: int, db: Session = Depends(get_db)):
    gallery = db.get(Gallery, gallery_id)
    if gallery is None:
        raise HTTPException(404, "识别库不存在")
    base = WORKSPACE_DIRS["galleries"] / str(gallery_id)
    db.query(RecognitionLog).filter(RecognitionLog.gallery_id == gallery_id).delete()
    db.delete(gallery)
    db.commit()
    shutil.rmtree(base, ignore_errors=True)
    return {"ok": True}


@router.get("/logs")
def list_logs(
    gallery_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(RecognitionLog)
    if gallery_id:
        query = query.filter(RecognitionLog.gallery_id == gallery_id)
    items = query.order_by(RecognitionLog.id.desc()).limit(limit).all()
    return {
        "total": len(items),
        "items": [RecognitionLogOut.model_validate(i).model_dump() for i in items],
    }


@router.get("/candidates")
def candidates(db: Session = Depends(get_db)):
    """可用于建库的 (训练任务, 数据集) 组合。"""
    jobs = db.query(TrainJob).filter(TrainJob.status == "success").order_by(TrainJob.id.desc()).all()
    result = []
    for job in jobs:
        artifacts = db.query(Artifact).filter(
            Artifact.job_id == job.id, Artifact.kind.in_(["tflite", "keras"])
        ).count()
        result.append(
            {
                "job_id": job.id,
                "job_name": job.name,
                "model_name": job.model_name,
                "best_eer": job.best_eer,
                "avg_eer": job.avg_eer,
                "dataset_id": job.dataset_id,
                "models": artifacts,
            }
        )
    datasets = db.query(Dataset).order_by(Dataset.id.desc()).all()
    return {
        "jobs": result,
        "datasets": [
            {"id": d.id, "name": d.name, "n_classes": d.n_classes, "n_images": d.n_images}
            for d in datasets
        ],
    }
