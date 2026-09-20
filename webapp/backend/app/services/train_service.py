"""训练任务编排：准备数据目录、启动子进程、采集进度、回收结果。"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..config import KERAS_CODE_DIR, PYTHON_BIN, WEBAPP_DIR, WORKSPACE_DIRS
from ..database import SessionLocal
from ..models import Artifact, Dataset, FoldResult, TrainJob
from .runtime import BackgroundProcess, manager

RUNNER = WEBAPP_DIR / "backend" / "run_training.py"
EVENT_PREFIX = "@@EVENT@@"
MAX_HISTORY = 800

MODEL_NAMES = ["mpsnet", "mobilenet_v1", "mobilenet_v2", "mobilenet_v3", "mobilefacenet"]

# 与 Keras_Code/options.py 一一对应，前端据此渲染超参数表单
OPTION_SPEC: list[dict[str, Any]] = [
    # 基础
    {"name": "image_extension", "label": "图像扩展名", "type": "str", "default": ".png", "group": "基础"},
    {"name": "train_session", "label": "训练会话", "type": "int", "default": 1, "choices": [1, 2], "group": "基础",
     "help": "1 = 闭集测试（测试集包含在训练集中），2 = 开集测试"},
    {"name": "n_folds", "label": "交叉验证折数", "type": "int", "default": 5, "min": 2, "max": 10, "group": "基础"},
    {"name": "random_state", "label": "随机种子", "type": "int", "default": 42, "group": "基础"},
    {"name": "distance_metric", "label": "距离度量", "type": "str", "default": "cosine",
     "choices": ["cosine", "euclidean", "manhattan", "correlation"], "group": "基础"},

    # 训练轮次与批量
    {"name": "warmup_epochs", "label": "预热轮数 (Softmax)", "type": "int", "default": 50, "min": 1, "group": "训练轮次"},
    {"name": "fine_tune_epochs", "label": "微调轮数 (AdaCos)", "type": "int", "default": 50, "min": 1, "group": "训练轮次"},
    {"name": "warmup_batch_size", "label": "预热批量大小", "type": "int", "default": 24, "min": 1, "group": "训练轮次"},
    {"name": "fine_tune_batch_size", "label": "微调批量大小", "type": "int", "default": 24, "min": 1, "group": "训练轮次"},

    # 优化器
    {"name": "warmup_optimizer", "label": "预热优化器", "type": "str", "default": "rmsprop",
     "choices": ["rmsprop", "adam", "adadelta", "sgd"], "group": "优化器"},
    {"name": "warmup_lr", "label": "预热学习率", "type": "float", "default": 0.001, "group": "优化器"},
    {"name": "fine_tune_optimizer", "label": "微调优化器", "type": "str", "default": "adam",
     "choices": ["rmsprop", "adam", "adadelta", "sgd"], "group": "优化器"},
    {"name": "fine_tune_lr", "label": "微调学习率", "type": "float", "default": 0.0001, "group": "优化器"},

    # 模型结构
    {"name": "embedding_dim", "label": "特征维度", "type": "int", "default": 128, "min": 16, "group": "模型结构"},
    {"name": "embedding_layer_name", "label": "特征层名称", "type": "str", "default": "embeddings", "group": "模型结构"},
    {"name": "dropout", "label": "Dropout 比例", "type": "float", "default": 0.0, "min": 0, "max": 0.9, "group": "模型结构"},
    {"name": "weight_decay", "label": "权重衰减", "type": "float", "default": 0.0005, "group": "模型结构"},
    {"name": "use_bias", "label": "卷积使用偏置", "type": "int", "default": 0, "choices": [0, 1], "group": "模型结构"},
    {"name": "kernel_initializer", "label": "权重初始化", "type": "str", "default": "he_uniform",
     "choices": ["he_uniform", "he_normal", "glorot_uniform", "glorot_normal"], "group": "模型结构"},
    {"name": "start_fine_tune_layer_id", "label": "微调起始层索引", "type": "int", "default": -5, "group": "模型结构"},
    {"name": "end_fine_tune_layer_id", "label": "微调结束层索引", "type": "int", "default": -4, "group": "模型结构"},
]

DEFAULT_PARAMS = {item["name"]: item["default"] for item in OPTION_SPEC}


def default_params() -> dict[str, Any]:
    return dict(DEFAULT_PARAMS)


def option_spec() -> list[dict]:
    return OPTION_SPEC


def sanitize_params(params: dict | None) -> dict[str, Any]:
    """只保留 options.py 认识的选项，并按声明类型做转换与范围收敛。"""
    clean: dict[str, Any] = {}
    incoming = params or {}
    for item in OPTION_SPEC:
        name = item["name"]
        value = incoming.get(name, item["default"])
        try:
            if item["type"] == "int":
                value = int(value)
            elif item["type"] == "float":
                value = float(value)
            else:
                value = str(value)
        except (TypeError, ValueError):
            value = item["default"]
        if isinstance(value, (int, float)):
            if "min" in item:
                value = max(item["min"], value)
            if "max" in item:
                value = min(item["max"], value)
        if "choices" in item and value not in item["choices"]:
            value = item["default"]
        clean[name] = value
    return clean


# ---------------------------------------------------------------- 目录准备
def safe_alias(name: str) -> str:
    """数据集名 -> 可用作目录名的别名（测试集名称会进入结果文件名）。"""
    alias = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")
    return alias or "dataset"


def job_dir(job_id: int) -> pathlib.Path:
    path = WORKSPACE_DIRS["jobs"] / str(job_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _link_dataset(data_dir: pathlib.Path, dataset: Dataset, used: set[str]) -> str:
    """在任务的 data 目录下建立指向数据集的符号链接，返回别名。"""
    alias = safe_alias(dataset.name)
    suffix = 1
    while alias in used:
        suffix += 1
        alias = f"{safe_alias(dataset.name)}_{suffix}"
    used.add(alias)

    link = data_dir / alias
    if link.is_symlink() or link.exists():
        if link.is_symlink():
            link.unlink()
        else:
            shutil.rmtree(link, ignore_errors=True)
    link.symlink_to(pathlib.Path(dataset.path), target_is_directory=True)
    return alias


def prepare_job_files(job: TrainJob, train_datasets: list[Dataset], test_dataset: Dataset) -> dict:
    """生成 data 软链接目录、train/test 列表文件与运行配置。"""
    base = job_dir(job.id)
    data_dir = base / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    used: set[str] = set()
    train_aliases = [_link_dataset(data_dir, ds, used) for ds in train_datasets]
    test_alias = _link_dataset(data_dir, test_dataset, used)

    train_file = base / "train_folders.txt"
    train_file.write_text("\n".join(train_aliases) + "\n", encoding="utf-8")

    test_file = base / "test_folders.txt"
    test_file.write_text(f"{test_alias} {job.n_sessions}\n", encoding="utf-8")

    output_dir = base / "results"
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg = {
        "data_folder": str(data_dir),
        "train_folder_file": str(train_file),
        "test_folder_file": str(test_file),
        "output_folder": str(output_dir),
        "params": {**sanitize_params(job.params), "model_name": job.model_name},
        "retrain_softmax": job.retrain_softmax,
        "retrain_fine_tune": job.retrain_fine_tune,
        "convert_to_tflite": job.convert_to_tflite,
    }
    cfg_path = base / "job_config.json"
    cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"config_path": cfg_path, "output_dir": output_dir, "test_alias": test_alias}


# ---------------------------------------------------------------- 启动任务
def start_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(TrainJob, job_id)
        if job is None:
            return

        key = f"train:{job_id}"
        if manager.get(key) and manager.get(key).running:
            return

        try:
            if job.dataset_id is None:
                raise ValueError("未指定数据集")
            if job.model_name not in MODEL_NAMES:
                raise ValueError(f"不支持的模型：{job.model_name}")
            test_dataset = db.get(Dataset, job.dataset_id)
            if test_dataset is None:
                raise ValueError("数据集不存在")

            train_datasets = [test_dataset]
            extra_ids = (job.params or {}).get("extra_train_dataset_ids") or []
            for ds_id in extra_ids:
                ds = db.get(Dataset, int(ds_id))
                if ds is not None and ds.id != test_dataset.id:
                    train_datasets.append(ds)

            files = prepare_job_files(job, train_datasets, test_dataset)
        except Exception as exc:
            job.status = "failed"
            job.error = f"准备训练数据失败：{exc}"
            job.finished_at = datetime.now()
            db.commit()
            return

        job.output_dir = str(files["output_dir"])
        job.log_path = str(job_dir(job.id) / "train.log")
        job.status = "running"
        job.started_at = datetime.now()
        job.finished_at = None
        job.error = ""
        job.progress = {
            "stage": "starting",
            "phase": None,
            "fold": 0,
            "n_folds": int((job.params or {}).get("n_folds", 5)),
            "epoch": 0,
            "total_epochs": 0,
            "history": [],
            "folds": {},
            "test_folder": files["test_alias"],
            "model_name": job.model_name,
        }
        db.commit()

        proc = BackgroundProcess(
            cmd=[PYTHON_BIN, str(RUNNER), str(files["config_path"])],
            cwd=KERAS_CODE_DIR,
            log_path=pathlib.Path(job.log_path),
            on_line=lambda line, jid=job_id: _on_event(jid, line),
        )
        # 用闭包把 proc 自身传进回调，避免“已删除任务的残留线程”写到新任务上
        proc.on_finish = lambda code, err, jid=job_id, p=proc: _on_finish(jid, code, err, p)
        manager.register(key, proc)
        proc.start()
    finally:
        db.close()


def stop_job(job_id: int) -> bool:
    return manager.stop(f"train:{job_id}")


def is_running(job_id: int) -> bool:
    proc = manager.get(f"train:{job_id}")
    return bool(proc and proc.running)


# ---------------------------------------------------------------- 事件处理
def _on_event(job_id: int, line: str) -> None:
    if not line.startswith(EVENT_PREFIX):
        return
    try:
        event = json.loads(line[len(EVENT_PREFIX):])
    except json.JSONDecodeError:
        return

    db = SessionLocal()
    try:
        job = db.get(TrainJob, job_id)
        if job is None:
            return
        progress = dict(job.progress or {})
        history = list(progress.get("history") or [])
        etype = event.get("type")

        if etype == "stage":
            progress["stage"] = event.get("stage")
        elif etype == "config":
            progress["model_name"] = event.get("model_name")
            progress["n_folds"] = event.get("n_folds")
        elif etype == "train_data":
            progress["train_data"] = {
                k: event.get(k) for k in ("n_images", "n_classes", "sample_shape", "min_class", "max_class")
            }
        elif etype == "test_data":
            progress["test_data"] = {
                k: event.get(k) for k in ("test_folder", "n_samples", "n_classes", "n_sessions", "class_size")
            }
        elif etype == "fold_start":
            progress["fold"] = event.get("fold")
            progress["stage"] = "training"
            progress["phase"] = "softmax"
            progress["epoch"] = 0
        elif etype == "phase":
            progress["stage"] = "training"
            progress["phase"] = event.get("phase")
            progress["fold"] = event.get("fold")
            progress["total_epochs"] = event.get("total_epochs", 0)
            progress["epoch"] = 0
        elif etype == "epoch":
            progress["stage"] = "training"
            progress["phase"] = event.get("phase")
            progress["fold"] = event.get("fold")
            progress["epoch"] = event.get("epoch")
            progress["total_epochs"] = event.get("total_epochs")
            history.append({k: event.get(k) for k in
                            ("phase", "fold", "epoch", "loss", "accuracy", "val_loss", "val_accuracy")})
            if len(history) > MAX_HISTORY:
                history = history[-MAX_HISTORY:]
        elif etype == "fold_result":
            folds = dict(progress.get("folds") or {})
            folds[str(event.get("fold"))] = {"eer": event.get("eer")}
            progress["folds"] = folds
        elif etype == "done":
            progress["stage"] = "finished"

        progress["history"] = history
        job.progress = progress
        db.commit()
    finally:
        db.close()


def _on_finish(job_id: int, code: int, error: str, proc: BackgroundProcess | None = None) -> None:
    key = f"train:{job_id}"
    current = manager.get(key)
    if proc is not None and current is not None and current is not proc:
        return  # 已有更新的进程接管了同一个任务号，忽略这次迟到回调

    db = SessionLocal()
    try:
        job = db.get(TrainJob, job_id)
        if job is None:
            return
        progress = dict(job.progress or {})
        progress["history"] = list(progress.get("history") or [])

        if code == 0:
            job.status = "success"
        elif job.status == "running" and "中断" in (error or ""):
            job.status = "stopped"
        else:
            job.status = "failed"
            job.error = error or f"训练进程退出码 {code}"

        if job.output_dir:
            summary = parse_output(pathlib.Path(job.output_dir), job)
            job.best_eer = summary.get("best_eer")
            job.avg_eer = summary.get("avg_eer")
            progress["folds"] = summary.get("folds", {})
            persist_results(db, job, summary)

        progress["stage"] = "finished"
        job.progress = progress
        job.finished_at = datetime.now()
        db.commit()
    finally:
        db.close()
        manager.pop(key)


# ---------------------------------------------------------------- 结果解析
FOLD_SCORE_RE = re.compile(
    r"Threshold:\s*([-\d.]+),\s*FRR:\s*([-\d.]+),\s*FAR:\s*([-\d.]+),\s*EER:\s*([-\d.]+)"
)
SUMMARY_RE = {
    "best_fold": re.compile(r"Best fold:\s*(\d+)"),
    "best_eer": re.compile(r"Best EER:\s*([\d.]+)"),
    "avg_eer": re.compile(r"Average EER:\s*([\d.]+)"),
}


def parse_output(output_dir: pathlib.Path, job: TrainJob) -> dict:
    """把 train.py 写在 results 目录里的产物解析成结构化结果。

    train.py 的命名规则（fpath = output_folder + test_name + '_fold' + N）：
        {test}_fold{N}_scores.txt / {test}_fold{N}_DET.png / {test}_fold{N}MDD.png
        {test}_fold{N}.hdf5 / adacos_fold{N}.keras / adacos_fold{N}.tflite
        {test}_scores.txt（汇总，含 Best/Average EER）
    """
    summary: dict[str, Any] = {"folds": {}, "artifacts": [], "best_eer": None, "avg_eer": None}
    if not output_dir.is_dir():
        return summary

    progress = job.progress or {}
    test_info = progress.get("test_data") or {}
    n_genuine, n_impostor = _pair_counts(test_info.get("n_samples"), test_info.get("n_classes"))

    test_names: set[str] = set()

    for scores in sorted(output_dir.glob("*_fold*_scores.txt")):
        match = re.match(r"^(?P<test>.+)_fold(?P<fold>\d+)_scores\.txt$", scores.name)
        if not match:
            continue
        test_name = match.group("test")
        fold = int(match.group("fold"))
        test_names.add(test_name)
        base = output_dir / f"{test_name}_fold{fold}"

        entry: dict[str, Any] = {
            "eer": None,
            "threshold": None,
            "frr": None,
            "far": None,
            "n_genuine": n_genuine,
            "n_impostor": n_impostor,
            "scores_path": str(scores),
        }
        try:
            head = scores.read_text(encoding="utf-8", errors="ignore").splitlines()
            found = FOLD_SCORE_RE.search(" ".join(head[:4]))
            if found:
                entry["threshold"] = float(found.group(1))
                entry["frr"] = float(found.group(2))
                entry["far"] = float(found.group(3))
                entry["eer"] = float(found.group(4))
        except Exception:
            pass

        for prefix in ("adacos", "softmax"):
            keras_file = output_dir / f"{prefix}_fold{fold}.keras"
            if keras_file.exists():
                entry["keras_path"] = str(keras_file)
                break

        tflite = output_dir / f"adacos_fold{fold}.tflite"
        if tflite.exists():
            entry["tflite_path"] = str(tflite)

        features = base.with_suffix(".hdf5")
        if features.exists():
            entry["features_path"] = str(features)

        det = output_dir / f"{base.name}_DET.png"
        mdd = output_dir / f"{base.name}MDD.png"
        if det.exists():
            entry["det_path"] = str(det)
        if mdd.exists():
            entry["mdd_path"] = str(mdd)

        summary["folds"][str(fold)] = entry

    for test_name in sorted(test_names):
        summary_file = output_dir / f"{test_name}_scores.txt"
        if not summary_file.exists():
            continue
        text = summary_file.read_text(encoding="utf-8", errors="ignore")
        best = SUMMARY_RE["best_eer"].search(text)
        average = SUMMARY_RE["avg_eer"].search(text)
        if best:
            summary["best_eer"] = float(best.group(1))
        if average:
            summary["avg_eer"] = float(average.group(1))

    kind_by_suffix = {
        ".keras": "keras",
        ".tflite": "tflite",
        ".hdf5": "features",
        ".pkl": "history",
        ".png": "plot",
        ".txt": "scores",
    }
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file():
            continue
        kind = kind_by_suffix.get(path.suffix.lower(), "other")
        if "_DET" in path.name or "MDD" in path.name:
            kind = "plot"
        summary["artifacts"].append(
            {
                "kind": kind,
                "name": str(path.relative_to(output_dir)),
                "path": str(path),
                "size": path.stat().st_size,
            }
        )

    return summary


def _pair_counts(n_samples, n_classes) -> tuple[int, int]:
    """按类内/类间配对估算 genuine / impostor 数量（与 test() 的口径一致）。"""
    try:
        n_samples = int(n_samples or 0)
        n_classes = int(n_classes or 0)
    except (TypeError, ValueError):
        return 0, 0
    if n_samples <= 1 or n_classes <= 0:
        return 0, 0
    class_size = n_samples // n_classes
    genuine = n_classes * (class_size * (class_size - 1) // 2)
    total = n_samples * (n_samples - 1) // 2
    return genuine, max(0, total - genuine)


def persist_results(db: Session, job: TrainJob, summary: dict) -> None:
    for row in db.query(FoldResult).filter(FoldResult.job_id == job.id).all():
        db.delete(row)
    for row in db.query(Artifact).filter(Artifact.job_id == job.id).all():
        db.delete(row)
    db.flush()

    for fold_key, entry in sorted(summary.get("folds", {}).items(), key=lambda kv: int(kv[0])):
        db.add(
            FoldResult(
                job_id=job.id,
                fold=int(fold_key),
                eer=entry.get("eer"),
                threshold=entry.get("threshold"),
                frr=entry.get("frr"),
                far=entry.get("far"),
                n_genuine=int(entry.get("n_genuine") or 0),
                n_impostor=int(entry.get("n_impostor") or 0),
                scores_path=entry.get("scores_path", ""),
                det_path=entry.get("det_path", ""),
                mdd_path=entry.get("mdd_path", ""),
                features_path=entry.get("features_path", ""),
                keras_path=entry.get("keras_path", ""),
                tflite_path=entry.get("tflite_path", ""),
            )
        )

    for item in summary.get("artifacts", []):
        db.add(
            Artifact(
                job_id=job.id,
                kind=item["kind"],
                name=item["name"],
                path=item["path"],
                size=item["size"],
            )
        )


def best_model_path(job: TrainJob) -> str | None:
    """返回该任务表现最好那一折的 .tflite / .keras 路径。"""
    folds = [f for f in job.folds if f.eer is not None]
    if not folds:
        folds = list(job.folds)
    if not folds:
        return None
    folds.sort(key=lambda f: f.eer if f.eer is not None else 1e9)
    best = folds[0]
    return best.tflite_path or best.keras_path or None
