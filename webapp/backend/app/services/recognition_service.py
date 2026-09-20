"""掌脉识别 / 验证：构建特征库 + 上传图片比对（1:N 识别、1:1 验证）。"""
from __future__ import annotations

import json
import pathlib
import threading
import uuid
from datetime import datetime

import numpy as np
from sqlalchemy.orm import Session

from ..config import PYTHON_BIN, WEBAPP_DIR, WORKSPACE_DIRS
from ..database import SessionLocal
from ..models import Dataset, Gallery, RecognitionLog, TrainJob
from . import roi_service
from .inference import cosine_distances, get_embedder, load_image_gray
from .runtime import BackgroundProcess, manager

RUNNER = WEBAPP_DIR / "backend" / "run_gallery.py"
EVENT_PREFIX = "@@EVENT@@"

_data_cache: dict[int, dict] = {}
_data_lock = threading.Lock()


class RecognitionError(RuntimeError):
    pass


# ---------------------------------------------------------------- 模型选择
def resolve_model_path(db: Session, job: TrainJob) -> tuple[str, str]:
    """挑出该任务最优一折的模型文件，返回 (路径, embedding 层名)。"""
    folds = list(job.folds)
    ranked = sorted(folds, key=lambda f: f.eer if f.eer is not None else 1e9)
    for fold in ranked:
        if fold.tflite_path and pathlib.Path(fold.tflite_path).exists():
            return fold.tflite_path, (job.params or {}).get("embedding_layer_name", "embeddings")
    for fold in ranked:
        if fold.keras_path and pathlib.Path(fold.keras_path).exists():
            return fold.keras_path, (job.params or {}).get("embedding_layer_name", "embeddings")
    raise RecognitionError("该任务还没有可用的模型文件（.tflite / .keras）")


def default_threshold(db: Session, job: TrainJob) -> float | None:
    folds = [f for f in job.folds if f.threshold is not None]
    if not folds:
        return None
    folds.sort(key=lambda f: f.eer if f.eer is not None else 1e9)
    return float(folds[0].threshold)


# ---------------------------------------------------------------- 建库任务
def gallery_dir(gallery_id: int) -> pathlib.Path:
    path = WORKSPACE_DIRS["galleries"] / str(gallery_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def start_gallery(gallery_id: int) -> None:
    db = SessionLocal()
    try:
        gallery = db.get(Gallery, gallery_id)
        if gallery is None:
            return

        key = f"gallery:{gallery_id}"
        if manager.get(key) and manager.get(key).running:
            return

        try:
            job = db.get(TrainJob, gallery.job_id) if gallery.job_id else None
            dataset = db.get(Dataset, gallery.dataset_id) if gallery.dataset_id else None
            if job is None or dataset is None:
                raise RecognitionError("识别库缺少训练任务或数据集")
            model_path, embedding_layer = resolve_model_path(db, job)
        except Exception as exc:
            gallery.status = "failed"
            gallery.error = str(exc)
            gallery.finished_at = datetime.now()
            db.commit()
            return

        base = gallery_dir(gallery_id)
        config_path = base / "gallery_config.json"
        config_path.write_text(
            json.dumps(
                {
                    "model_path": model_path,
                    "embedding_layer": embedding_layer,
                    "dataset_path": dataset.path,
                    "image_extension": dataset.image_extension,
                    "output_path": str(base / "gallery.npz"),
                    "batch_size": 32,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        gallery.status = "running"
        gallery.error = ""
        gallery.model_name = job.model_name
        gallery.path = ""
        gallery.finished_at = None
        db.commit()

        proc = BackgroundProcess(
            cmd=[PYTHON_BIN, str(RUNNER), str(config_path)],
            cwd=pathlib.Path(WEBAPP_DIR / "backend"),
            log_path=base / "gallery.log",
            on_line=lambda line, gid=gallery_id: _on_event(gid, line),
        )
        proc.on_finish = lambda code, err, gid=gallery_id, p=proc: _on_finish(gid, code, err, p)
        manager.register(key, proc)
        proc.start()
    finally:
        db.close()


def stop_gallery(gallery_id: int) -> bool:
    return manager.stop(f"gallery:{gallery_id}")


def _on_event(gallery_id: int, line: str) -> None:
    if not line.startswith(EVENT_PREFIX):
        return
    try:
        event = json.loads(line[len(EVENT_PREFIX):])
    except json.JSONDecodeError:
        return

    db = SessionLocal()
    try:
        gallery = db.get(Gallery, gallery_id)
        if gallery is None:
            return
        if event.get("type") == "model":
            gallery.embedding_dim = int(event.get("embedding_dim") or 0)
        elif event.get("type") == "progress":
            done, total = event.get("done", 0), event.get("total", 0)
            gallery.error = ""
            gallery.path = f"progress:{done}/{total}"
        elif event.get("type") == "error":
            gallery.error = event.get("message", "")
        db.commit()
    finally:
        db.close()


def _on_finish(gallery_id: int, code: int, error: str, proc: BackgroundProcess | None = None) -> None:
    key = f"gallery:{gallery_id}"
    current = manager.get(key)
    if proc is not None and current is not None and current is not proc:
        return  # 已有更新的进程接管了同一个识别库号，忽略这次迟到回调

    db = SessionLocal()
    try:
        gallery = db.get(Gallery, gallery_id)
        if gallery is None:
            return
        base = gallery_dir(gallery_id)
        npz = base / "gallery.npz"
        if code == 0 and npz.exists():
            with np.load(npz, allow_pickle=True) as data:
                gallery.n_samples = int(data["features"].shape[0])
                gallery.n_classes = int(len(data["label_names"]))
                gallery.embedding_dim = int(data["features"].shape[1])
            gallery.path = str(npz)
            gallery.status = "success"
            gallery.error = ""
            with _data_lock:
                _data_cache.pop(gallery_id, None)
        else:
            gallery.status = "failed"
            gallery.error = error or gallery.error or "特征库构建失败"
            gallery.path = ""
        gallery.finished_at = datetime.now()
        db.commit()
    finally:
        db.close()
        manager.pop(key)


# ---------------------------------------------------------------- 特征库读取
def load_gallery(gallery_id: int) -> dict:
    with _data_lock:
        cached = _data_cache.get(gallery_id)
    if cached is not None:
        return cached

    db = SessionLocal()
    try:
        gallery = db.get(Gallery, gallery_id)
        if gallery is None:
            raise RecognitionError("识别库不存在")
        if gallery.status != "success" or not gallery.path:
            raise RecognitionError("识别库尚未构建完成")
        npz = pathlib.Path(gallery.path)
        job = db.get(TrainJob, gallery.job_id) if gallery.job_id else None
        threshold = default_threshold(db, job) if job else None
        model_path, embedding_layer = (None, "embeddings")
        if job is not None:
            model_path, embedding_layer = resolve_model_path(db, job)
    finally:
        db.close()

    if not npz.exists():
        raise RecognitionError("识别库文件已丢失，请重新构建")

    with np.load(npz, allow_pickle=True) as data:
        payload = {
            "features": np.asarray(data["features"], dtype=np.float32),
            "labels": np.asarray(data["labels"], dtype=np.int64),
            "label_names": [str(x) for x in data["label_names"]],
            "paths": [str(x) for x in data["paths"]],
            "threshold": threshold,
            "model_path": model_path,
            "embedding_layer": embedding_layer,
        }
    with _data_lock:
        _data_cache[gallery_id] = payload
    return payload


def gallery_identities(gallery_id: int, limit: int = 200) -> list[dict]:
    payload = load_gallery(gallery_id)
    identities: dict[str, dict] = {}
    for label, path in zip(payload["labels"], payload["paths"]):
        name = payload["label_names"][int(label)]
        entry = identities.setdefault(name, {"label": name, "count": 0, "preview": path})
        entry["count"] += 1
    result = sorted(identities.values(), key=lambda item: item["label"])
    return result[:limit]


# ---------------------------------------------------------------- 探针处理
def probe_dir() -> pathlib.Path:
    path = WORKSPACE_DIRS["predict"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def extract_roi_for_probe(upload_path: pathlib.Path, roi_size: int) -> tuple[pathlib.Path, bool]:
    """上传图片先走一遍原项目的 ROI 提取，失败则退回原图。"""
    token = uuid.uuid4().hex[:12]
    out = probe_dir() / token
    out.mkdir(parents=True, exist_ok=True)
    try:
        roi_service.ensure_binary()
        roi_service._run_cli(str(upload_path), str(out), roi_size, False)
        roi = out / f"{upload_path.stem}_roi.png"
        if roi.exists():
            return roi, True
    except Exception:
        pass
    return upload_path, False


def _embed_probe(payload: dict, roi_path: pathlib.Path):
    embedder = get_embedder(payload["model_path"], payload["embedding_layer"])
    image = load_image_gray(roi_path, embedder.input_size)
    return embedder.embed_one(image)


def identify(db: Session, gallery_id: int, probe_path: pathlib.Path, topk: int = 5,
             roi_size: int = 128) -> dict:
    import time

    started = time.time()
    payload = load_gallery(gallery_id)
    roi_path, roi_ok = extract_roi_for_probe(probe_path, roi_size)
    probe = _embed_probe(payload, roi_path)

    distances = cosine_distances(payload["features"], probe)
    per_label: dict[int, float] = {}
    for index, label in enumerate(payload["labels"]):
        label = int(label)
        value = float(distances[index])
        if label not in per_label or value < per_label[label]:
            per_label[label] = value

    ranking = sorted(per_label.items(), key=lambda kv: kv[1])[: max(1, topk)]
    results = [
        {
            "label": payload["label_names"][label],
            "distance": round(distance, 6),
            "similarity": round(1.0 - distance, 6),
        }
        for label, distance in ranking
    ]
    threshold = payload.get("threshold")
    best = results[0] if results else None

    record = RecognitionLog(
        gallery_id=gallery_id,
        mode="identify",
        probe_path=str(probe_path),
        roi_path=str(roi_path),
        predicted_label=best["label"] if best else "",
        distance=best["distance"] if best else None,
        threshold=threshold,
        matched=(best["distance"] <= threshold) if (best and threshold is not None) else None,
        topk=results,
        elapsed_ms=int((time.time() - started) * 1000),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "roi_extracted": roi_ok,
        "roi_path": str(roi_path),
        "predicted_label": record.predicted_label,
        "distance": record.distance,
        "threshold": threshold,
        "matched": record.matched,
        "candidates": results,
        "elapsed_ms": record.elapsed_ms,
        "record_id": record.id,
    }


def verify(db: Session, gallery_id: int, probe_path: pathlib.Path, claim: str,
           threshold: float | None = None, roi_size: int = 128) -> dict:
    import time

    started = time.time()
    payload = load_gallery(gallery_id)
    roi_path, roi_ok = extract_roi_for_probe(probe_path, roi_size)
    probe = _embed_probe(payload, roi_path)

    threshold = float(threshold) if threshold is not None else payload.get("threshold")
    if threshold is None:
        raise RecognitionError("该识别库没有可用的 EER 阈值，请手动指定")

    indexes = [i for i, label in enumerate(payload["labels"])
               if payload["label_names"][int(label)] == claim]
    if not indexes:
        raise RecognitionError(f"识别库中不存在身份：{claim}")

    distances = cosine_distances(payload["features"][indexes], probe)
    best_index = int(np.argmin(distances))
    best_distance = float(distances[best_index])
    matched = best_distance <= threshold

    record = RecognitionLog(
        gallery_id=gallery_id,
        mode="verify",
        probe_path=str(probe_path),
        roi_path=str(roi_path),
        predicted_label=claim,
        distance=round(best_distance, 6),
        threshold=threshold,
        matched=matched,
        topk=[{"label": claim, "distance": round(best_distance, 6), "samples": len(indexes)}],
        elapsed_ms=int((time.time() - started) * 1000),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "roi_extracted": roi_ok,
        "roi_path": str(roi_path),
        "claim": claim,
        "distance": record.distance,
        "threshold": threshold,
        "matched": matched,
        "n_gallery_samples": len(indexes),
        "elapsed_ms": record.elapsed_ms,
        "record_id": record.id,
    }
