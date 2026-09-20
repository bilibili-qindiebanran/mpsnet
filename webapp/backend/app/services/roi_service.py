"""掌脉 ROI 提取：封装项目自带的 ROI_Extraction_Code/palmlib 可执行文件。

对应原项目 palmlib.cpp 的全部能力：
  - 单张图片 / 整个目录（递归，保留 Palm_ID 子目录结构）
  - --roi-size 指定 ROI 边长
  - --save-debug 额外输出二值掩膜与裁剪手部图
"""
from __future__ import annotations

import pathlib
import subprocess
import threading

from ..config import (
    IMAGE_EXTENSIONS,
    PALMLIB_BINARY,
    PALMLIB_BUILD_SCRIPT,
    WORKSPACE_DIRS,
    ensure_workspace,
)
from ..database import SessionLocal
from ..models import RoiJob

_build_lock = threading.Lock()


class RoiError(RuntimeError):
    pass


def binary_ready() -> bool:
    return PALMLIB_BINARY.exists() and PALMLIB_BINARY.is_file()


def ensure_binary() -> None:
    """palmlib 不存在时尝试按项目自带脚本编译一次。"""
    if binary_ready():
        return
    with _build_lock:
        if binary_ready():
            return
        if not PALMLIB_BUILD_SCRIPT.exists():
            raise RoiError("未找到 palmlib 可执行文件与 build.sh，请先编译 ROI_Extraction_Code")
        proc = subprocess.run(
            ["bash", str(PALMLIB_BUILD_SCRIPT)],
            cwd=str(PALMLIB_BUILD_SCRIPT.parent),
            capture_output=True,
            text=True,
        )
        if not binary_ready():
            raise RoiError(f"palmlib 编译失败：{(proc.stderr or proc.stdout).strip()}")
    PALMLIB_BINARY.chmod(0o755)


def is_image(path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def list_images(root) -> list:
    if root.is_file():
        return [root] if is_image(root) else []
    return sorted(p for p in root.rglob("*") if p.is_file() and is_image(p))


def _run_cli(source: str, output_dir: str, roi_size: int, save_debug: bool):
    cmd = [str(PALMLIB_BINARY), source, output_dir, "--roi-size", str(roi_size)]
    if save_debug:
        cmd.append("--save-debug")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _collect_results(output_root, source_root, single: bool, debug_root=None) -> list[dict]:
    """把输出目录里的 *_roi.png 汇总成前端可直接展示的结果列表。"""
    items: list[dict] = []
    for roi in sorted(output_root.rglob("*_roi.png")):
        stem = roi.name[: -len("_roi.png")]
        parent = roi.parent
        rel = parent.relative_to(output_root)
        debug_parent = (debug_root / rel) if debug_root is not None else parent
        binary = debug_parent / f"{stem}_binary.png"
        crop = debug_parent / f"{stem}_crop.png"
        label = rel.as_posix() if rel.as_posix() != "." else (source_root.stem if single else "")
        original = None
        if single:
            original = str(source_root)
        else:
            for ext in IMAGE_EXTENSIONS:
                candidate = source_root / rel / f"{stem}{ext}"
                if candidate.exists():
                    original = str(candidate)
                    break
        items.append(
            {
                "label": label,
                "stem": stem,
                "original": original,
                "roi": str(roi),
                "binary": str(binary) if binary.exists() else None,
                "crop": str(crop) if crop.exists() else None,
            }
        )
    return items


def _separate_debug_files(output_root: pathlib.Path) -> pathlib.Path:
    """把调试图搬到同级目录 <output>__debug/。

    palmlib 默认把 *_binary.png / *_crop.png 和 *_roi.png 放在一起，
    这样输出目录无法直接当训练数据集用（会被 rglob('*.png') 一起扫进去）。
    """
    output_root = pathlib.Path(output_root)
    debug_root = output_root.parent / f"{output_root.name}__debug"
    debug_root.mkdir(parents=True, exist_ok=True)

    for path in list(output_root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.endswith(("_binary.png", "_crop.png")):
            relative = path.relative_to(output_root)
            destination = debug_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                destination.unlink()
            path.replace(destination)
    return debug_root


def run_job(job_id: int) -> None:
    """在后台线程中执行一次 ROI 提取任务并写回数据库。"""
    from pathlib import Path

    db = SessionLocal()
    try:
        job = db.get(RoiJob, job_id)
        if job is None:
            return
        job.status = "running"
        db.commit()

        try:
            ensure_binary()
            source = Path(job.source_path)
            if not source.exists():
                raise RoiError(f"源路径不存在：{source}")

            output_root = Path(job.output_dir)
            output_root.mkdir(parents=True, exist_ok=True)

            single = source.is_file()
            images = list_images(source)
            if not images:
                raise RoiError("源路径下没有可处理的图片")

            code, stdout, stderr = _run_cli(
                str(source), str(output_root), job.roi_size, job.save_debug
            )

            debug_root = _separate_debug_files(output_root) if job.save_debug else None
            items = _collect_results(output_root, source, single, debug_root)

            skipped = [ln for ln in (stderr or "").splitlines() if "[skip]" in ln]
            job.total = len(items) + len(skipped)
            job.succeeded = len(items)
            job.failed = len(skipped)
            job.results = items
            job.log = (stdout or "").strip() + ("\n" + "\n".join(skipped) if skipped else "")
            if code != 0 and not items:
                job.status = "failed"
                job.error = (stderr or stdout or "palmlib 执行失败").strip()
            else:
                job.status = "success"
                job.error = "" if items else "没有成功提取到 ROI"
        except RoiError as exc:
            job.status = "failed"
            job.error = str(exc)
        except Exception as exc:  # 兜底，避免任务卡在 running
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
        finally:
            from datetime import datetime

            job.finished_at = datetime.now()
            db.commit()
    finally:
        db.close()


def start_job(job_id: int) -> None:
    ensure_workspace()
    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()


def job_output_dir(job_id: int):
    path = WORKSPACE_DIRS["roi"] / str(job_id)
    path.mkdir(parents=True, exist_ok=True)
    return path
