"""文件访问白名单：只允许读取项目目录、工作区与已登记数据集内的文件。"""
from __future__ import annotations

import mimetypes
import pathlib

from sqlalchemy.orm import Session

from ..config import ALLOWED_FILE_ROOTS
from ..models import Dataset


def allowed_roots(db: Session | None = None) -> list[pathlib.Path]:
    roots = [pathlib.Path(p).resolve() for p in ALLOWED_FILE_ROOTS]
    if db is not None:
        for dataset in db.query(Dataset).all():
            try:
                roots.append(pathlib.Path(dataset.path).resolve())
            except OSError:
                continue
    return roots


def is_allowed(path: pathlib.Path, db: Session | None = None) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in allowed_roots(db):
        if resolved == root or root in resolved.parents:
            return True
    return False


def media_type(path: pathlib.Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"
