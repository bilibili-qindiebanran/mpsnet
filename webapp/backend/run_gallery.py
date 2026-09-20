"""在独立进程中为某个数据集构建识别库（提取全部样本的特征向量）。

用法: python run_gallery.py <gallery_config.json>
产物: 一个 .npz，包含 features / labels / label_names / paths
"""
from __future__ import annotations

import json
import pathlib
import sys

BACKEND_DIR = pathlib.Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import numpy as np  # noqa: E402

from app.config import IMAGE_EXTENSIONS  # noqa: E402
from app.services.inference import get_embedder, load_image_gray  # noqa: E402

EVENT_PREFIX = "@@EVENT@@"


def emit(event: dict) -> None:
    print(EVENT_PREFIX + json.dumps(event, ensure_ascii=False), flush=True)


def collect_samples(root: pathlib.Path, extension: str):
    """返回 (paths, labels, label_names)，标签按目录名排序，与训练时的编号方式一致。"""
    paths: list[pathlib.Path] = []
    labels: list[int] = []
    label_names: list[str] = []

    for class_dir in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name):
        files = sorted(
            p
            for p in class_dir.rglob("*" + extension)
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        )
        if not files:
            continue
        index = len(label_names)
        label_names.append(class_dir.name)
        for file in files:
            paths.append(file)
            labels.append(index)

    return paths, labels, label_names


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: run_gallery.py <gallery_config.json>", file=sys.stderr)
        return 2

    cfg = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    root = pathlib.Path(cfg["dataset_path"])
    if not root.is_dir():
        emit({"type": "error", "message": f"数据集目录不存在：{root}"})
        return 1

    paths, labels, label_names = collect_samples(root, cfg.get("image_extension", ".png"))
    total = len(paths)
    emit({"type": "start", "total": total, "n_classes": len(label_names)})
    if total == 0:
        emit({"type": "error", "message": "数据集里没有可用的样本"})
        return 1

    embedder = get_embedder(cfg["model_path"], cfg.get("embedding_layer", "embeddings"))
    emit(
        {
            "type": "model",
            "input_size": embedder.input_size,
            "embedding_dim": embedder.embedding_dim,
            "model_path": embedder.model_path,
        }
    )

    batch_size = int(cfg.get("batch_size", 32))
    features: list[np.ndarray] = []

    for start in range(0, total, batch_size):
        chunk = paths[start:start + batch_size]
        batch = np.stack([load_image_gray(p, embedder.input_size) for p in chunk])
        features.append(embedder.embed(batch))
        emit({"type": "progress", "done": min(start + batch_size, total), "total": total})

    matrix = np.vstack(features).astype(np.float32)
    output = pathlib.Path(cfg["output_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        features=matrix,
        labels=np.asarray(labels, dtype=np.int64),
        label_names=np.asarray(label_names, dtype=object),
        paths=np.asarray([str(p) for p in paths], dtype=object),
    )

    emit(
        {
            "type": "done",
            "n_samples": int(matrix.shape[0]),
            "n_classes": len(label_names),
            "embedding_dim": int(matrix.shape[1]),
        }
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
