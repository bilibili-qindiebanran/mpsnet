"""数据集管理接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..config import PROJECT_ROOT, resolve_path
from ..database import get_db
from ..models import Dataset, TrainJob
from ..schemas import DatasetCreate, DatasetOut, DatasetScanResult, DatasetUpdate
from ..services import dataset_service

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

SAMPLE_ROOTS = [
    PROJECT_ROOT / "Images" / "200_samples" / "ntust-hp",
    PROJECT_ROOT / "Images" / "200_samples" / "ntust-ip",
]


@router.get("")
def list_datasets(db: Session = Depends(get_db)):
    items = db.query(Dataset).order_by(Dataset.id.desc()).all()
    return {"total": len(items), "items": [DatasetOut.model_validate(i).model_dump() for i in items]}


@router.get("/suggestions")
def suggestions(db: Session = Depends(get_db)):
    """仓库自带的参考样本，可一键登记。"""
    existing = {item.path for item in db.query(Dataset).all()}
    result = []
    for root in SAMPLE_ROOTS:
        if not root.is_dir():
            continue
        try:
            stats = dataset_service.scan_dataset(root, ".png", sample_limit=4)
        except FileNotFoundError:
            continue
        result.append(
            {
                "name": root.name,
                "path": str(root),
                "n_classes": stats["n_classes"],
                "n_images": stats["n_images"],
                "registered": str(root) in existing,
                "samples": [s for cls in stats["classes"][:2] for s in cls["samples"][:2]],
            }
        )
    return {"items": result}


@router.get("/scan", response_model=DatasetScanResult)
def scan(path: str = Query(...), image_extension: str = Query(".png")):
    source = resolve_path(path)
    if not source.is_dir():
        raise HTTPException(400, f"目录不存在：{source}")
    try:
        stats = dataset_service.scan_dataset(source, image_extension)
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc
    if stats["n_images"] == 0:
        raise HTTPException(400, "该目录下没有找到符合格式的样本（结构应为 <目录>/<Palm_ID>/<图片>）")
    return stats


@router.get("/discover")
def discover(path: str = Query("")):
    target = resolve_path(path) if path else PROJECT_ROOT
    if not target.is_dir():
        raise HTTPException(400, f"目录不存在：{target}")
    return {
        "path": str(target),
        "subfolders": dataset_service.discover_subfolders(target),
    }


@router.post("", response_model=DatasetOut)
def create_dataset(payload: DatasetCreate, db: Session = Depends(get_db)):
    if db.query(Dataset).filter(Dataset.name == payload.name).first():
        raise HTTPException(400, f"数据集名称已存在：{payload.name}")
    try:
        return dataset_service.create_dataset(
            db, payload.name, payload.path, payload.image_extension, payload.description
        )
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(404, "数据集不存在")
    return dataset


@router.patch("/{dataset_id}", response_model=DatasetOut)
def update_dataset(dataset_id: int, payload: DatasetUpdate, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(404, "数据集不存在")
    if payload.name and payload.name != dataset.name:
        if db.query(Dataset).filter(Dataset.name == payload.name).first():
            raise HTTPException(400, f"数据集名称已存在：{payload.name}")
        dataset.name = payload.name
    if payload.description is not None:
        dataset.description = payload.description
    if payload.image_extension:
        dataset.image_extension = dataset_service.normalize_extension(payload.image_extension)
    db.commit()
    db.refresh(dataset)
    try:
        return dataset_service.refresh_dataset(db, dataset)
    except FileNotFoundError:
        return dataset


@router.post("/{dataset_id}/refresh", response_model=DatasetOut)
def refresh_dataset(dataset_id: int, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(404, "数据集不存在")
    try:
        return dataset_service.refresh_dataset(db, dataset)
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{dataset_id}/classes")
def dataset_classes(
    dataset_id: int,
    sample_limit: int = Query(6, ge=0, le=50),
    db: Session = Depends(get_db),
):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(404, "数据集不存在")
    classes = dataset_service.dataset_classes(dataset, sample_limit)
    return {"total": len(classes), "items": classes}


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: int, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(404, "数据集不存在")
    used = db.query(TrainJob).filter(TrainJob.dataset_id == dataset_id).count()
    if used:
        raise HTTPException(400, f"该数据集已被 {used} 个训练任务引用，无法删除")
    db.delete(dataset)
    db.commit()
    return {"ok": True}
