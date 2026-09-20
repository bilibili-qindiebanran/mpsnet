"""在独立进程中运行原项目的训练/测试流程（Keras_Code/train.py）。

不改动原算法代码，只做三件事：
  1. 按 Web 端下发的 JSON 配置组装命令行参数；
  2. 复用 options.Options / data.DataLoader / train.train；
  3. 通过 @@EVENT@@ 前缀的 JSON 行向父进程汇报实时进度与结果。

用法: python run_training.py <job_config.json>
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parents[1]
KERAS_CODE_DIR = PROJECT_ROOT / "Keras_Code"

sys.path.insert(0, str(KERAS_CODE_DIR))

EVENT_PREFIX = "@@EVENT@@"


def emit(event: dict) -> None:
    try:
        print(EVENT_PREFIX + json.dumps(event, ensure_ascii=False), flush=True)
    except Exception:
        pass


def build_argv(cfg: dict) -> list[str]:
    argv = ["train.py"]
    for key, value in cfg.get("params", {}).items():
        if value is None or value == "":
            continue
        argv += [f"--{key}", str(value)]
    argv += [
        "--data_folder", cfg["data_folder"],
        "--train_folder_file", cfg["train_folder_file"],
        "--test_folder_file", cfg["test_folder_file"],
        "--output_folder", cfg["output_folder"],
    ]
    return argv


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: run_training.py <job_config.json>", file=sys.stderr)
        return 2

    cfg = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    sys.argv = build_argv(cfg)

    import keras
    import numpy as np

    from data.dataloader import DataLoader
    from options import Options

    import train as train_module

    # ---------- 覆写 ModelCheckpoint，拿到逐 epoch 训练曲线 ----------
    OriginalCheckpoint = keras.callbacks.ModelCheckpoint

    class ProgressCheckpoint(OriginalCheckpoint):
        def on_train_begin(self, logs=None):
            super().on_train_begin(logs)
            name = str(self.filepath)
            fold_match = re.search(r"fold(\d+)", name)
            emit(
                {
                    "type": "phase",
                    "phase": "softmax" if "softmax_fold" in name else "adacos",
                    "fold": int(fold_match.group(1)) if fold_match else 0,
                    "total_epochs": int((self.params or {}).get("epochs", 0)),
                }
            )

        def on_epoch_end(self, epoch, logs=None):
            super().on_epoch_end(epoch, logs)
            name = str(self.filepath)
            fold_match = re.search(r"fold(\d+)", name)
            logs = logs or {}
            emit(
                {
                    "type": "epoch",
                    "phase": "softmax" if "softmax_fold" in name else "adacos",
                    "fold": int(fold_match.group(1)) if fold_match else 0,
                    "epoch": epoch + 1,
                    "total_epochs": int((self.params or {}).get("epochs", 0)),
                    "loss": _f(logs.get("loss")),
                    "accuracy": _f(logs.get("accuracy")),
                    "val_loss": _f(logs.get("val_loss")),
                    "val_accuracy": _f(logs.get("val_accuracy")),
                }
            )

    train_module.ModelCheckpoint = ProgressCheckpoint

    # ---------- 覆写 test，拿到每折 EER ----------
    original_test = train_module.test

    def test_with_event(model, fold, n_sessions=1):
        emit({"type": "stage", "stage": "verification", "fold": fold})
        eer = original_test(model, fold, n_sessions=n_sessions)
        emit({"type": "fold_result", "fold": fold, "eer": _f(eer)})
        return eer

    train_module.test = test_with_event

    # ---------- 解析配置 ----------
    config = Options().parse()
    emit(
        {
            "type": "config",
            "model_name": config.model_name,
            "output_folder": config.output_folder,
            "n_folds": config.n_folds,
            "distance_metric": config.distance_metric,
            "warmup_epochs": config.warmup_epochs,
            "fine_tune_epochs": config.fine_tune_epochs,
        }
    )

    emit({"type": "stage", "stage": "loading_train_data"})
    dataloader = DataLoader(config)
    class_counts = np.bincount(dataloader.train_labels) if len(dataloader.train_labels) else []
    emit(
        {
            "type": "train_data",
            "n_images": int(dataloader.train_data.shape[0]),
            "n_classes": int(dataloader.n_train_classes),
            "sample_shape": [int(x) for x in dataloader.sample_shape],
            "min_class": int(class_counts.min()) if len(class_counts) else 0,
            "max_class": int(class_counts.max()) if len(class_counts) else 0,
        }
    )

    # 记录折的开始，便于前端展示
    original_get_fold_data = dataloader.get_fold_data

    def get_fold_data(fold_id):
        emit({"type": "fold_start", "fold": int(fold_id) + 1})
        return original_get_fold_data(fold_id)

    dataloader.get_fold_data = get_fold_data

    train_module.config = config
    train_module.dataloader = dataloader

    retrain_softmax = bool(cfg.get("retrain_softmax", True))
    retrain_fine_tune = bool(cfg.get("retrain_fine_tune", True))
    convert_to_tflite = bool(cfg.get("convert_to_tflite", True))

    for line in config.test_folders:
        parts = line.strip().split(" ")
        if len(parts) < 2:
            continue
        test_folder, n_sessions = parts[0], int(parts[1])
        emit({"type": "stage", "stage": "loading_test_data", "test_folder": test_folder})
        dataloader.load_test_data(test_folder=test_folder)
        emit(
            {
                "type": "test_data",
                "test_folder": test_folder,
                "n_samples": int(dataloader.n_test_samples),
                "n_classes": int(dataloader.n_test_classes),
                "n_sessions": n_sessions,
                "class_size": int(dataloader.test_class_size),
            }
        )
        train_module.train(
            retrain_softmax,
            retrain_fine_tune,
            convert_to_tflite,
            n_sessions=n_sessions,
        )
        retrain_softmax = False
        convert_to_tflite = False

    emit({"type": "done"})
    return 0


def _f(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    sys.exit(main())
