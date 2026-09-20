"""数据集管理：登记目录、扫描类别与样本数量。

数据布局与原项目 Keras_Code/data 一致：
    <root>/<Palm_ID>/<image files>
"""
from __future__ import annotations

import pathlib

from sqlalchemy.orm import Session

from ..config import IMAGE_EXTENSIONS, resolve_path
from ..models import Dataset


def normalize_extension(ext: str) -> str:
    """数据集识别用的后缀。

    与原项目一致，匹配方式是 rglob('*' + extension)，所以既可以是 '.png'，
    也可以是 '_roi.png'（用于只挑出 ROI 结果、忽略 _binary/_crop 调试图）。
    """
    ext = (ext or ".png").strip()
    if not ext.startswith(".") and "." not in ext:
        ext = "." + ext
    return ext


def scan_dataset(root: str | pathlib.Path, extension: str = ".png", sample_limit: int = 8) -> dict:
    """按 Palm_ID 目录名排序扫描数据集，返回类别与样本统计。"""
    root = resolve_path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"数据集目录不存在：{root}")

    extension = normalize_extension(extension)
    classes: list[dict] = []
    total = 0

    for class_dir in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name):
        files = sorted(p for p in class_dir.rglob("*" + extension) if p.is_file())
        if not files:
            continue
        total += len(files)
        classes.append(
            {
                "label": class_dir.name,
                "count": len(files),
                "samples": [str(p) for p in files[:sample_limit]],
            }
        )

    return {"n_classes": len(classes), "n_images": total, "classes": classes}


def create_dataset(
    db: Session, name: str, path: str, image_extension: str = ".png", description: str = ""
) -> Dataset:
    resolved = resolve_path(path)
    stats = scan_dataset(resolved, image_extension)
    dataset = Dataset(
        name=name,
        path=str(resolved),
        image_extension=normalize_extension(image_extension),
        description=description,
        n_classes=stats["n_classes"],
        n_images=stats["n_images"],
        class_stats=stats,
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


def refresh_dataset(db: Session, dataset: Dataset) -> Dataset:
    stats = scan_dataset(dataset.path, dataset.image_extension)
    dataset.n_classes = stats["n_classes"]
    dataset.n_images = stats["n_images"]
    dataset.class_stats = stats
    db.commit()
    db.refresh(dataset)
    return dataset


def dataset_classes(dataset: Dataset, sample_limit: int = 0) -> list[dict]:
    stats = dataset.class_stats or {}
    classes = stats.get("classes", [])
    if sample_limit:
        return [dict(c, samples=c.get("samples", [])[:sample_limit]) for c in classes]
    return classes


def discover_subfolders(root: str | pathlib.Path) -> list[str]:
    """列出目录下的一级子目录（用于选择测试集）。"""
    root = resolve_path(root)
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def supported_extensions() -> list[str]:
    return IMAGE_EXTENSIONS
