"""SQLite 数据模型。"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> datetime:
    return datetime.now()


class Dataset(Base):
    """已登记的数据集（形如 <root>/<Palm_ID>/xxx.png 的目录）。"""

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    path: Mapped[str] = mapped_column(String(1024))
    image_extension: Mapped[str] = mapped_column(String(16), default=".png")
    description: Mapped[str] = mapped_column(Text, default="")
    n_classes: Mapped[int] = mapped_column(Integer, default=0)
    n_images: Mapped[int] = mapped_column(Integer, default=0)
    class_stats: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class RoiJob(Base):
    """一次 ROI 提取任务。"""

    __tablename__ = "roi_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="ROI 提取")
    source_type: Mapped[str] = mapped_column(String(20), default="upload")  # upload | directory
    source_path: Mapped[str] = mapped_column(String(1024), default="")
    output_dir: Mapped[str] = mapped_column(String(1024), default="")
    roi_size: Mapped[int] = mapped_column(Integer, default=128)
    save_debug: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    total: Mapped[int] = mapped_column(Integer, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    results: Mapped[list] = mapped_column(JSON, default=list)
    log: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Preset(Base):
    """训练超参数预设。"""

    __tablename__ = "presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TrainJob(Base):
    """一次训练任务（softmax 预热 + AdaCos 微调 + K 折验证）。"""

    __tablename__ = "train_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id"), nullable=True)
    test_folder: Mapped[str] = mapped_column(String(200))
    n_sessions: Mapped[int] = mapped_column(Integer, default=1)
    model_name: Mapped[str] = mapped_column(String(60), default="mpsnet")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    retrain_softmax: Mapped[bool] = mapped_column(Boolean, default=True)
    retrain_fine_tune: Mapped[bool] = mapped_column(Boolean, default=True)
    convert_to_tflite: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    output_dir: Mapped[str] = mapped_column(String(1024), default="")
    log_path: Mapped[str] = mapped_column(String(1024), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    best_eer: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_eer: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    folds: Mapped[list["FoldResult"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class FoldResult(Base):
    """某个折的验证结果。"""

    __tablename__ = "fold_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("train_jobs.id"), index=True)
    fold: Mapped[int] = mapped_column(Integer)
    eer: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    frr: Mapped[float | None] = mapped_column(Float, nullable=True)
    far: Mapped[float | None] = mapped_column(Float, nullable=True)
    n_genuine: Mapped[int] = mapped_column(Integer, default=0)
    n_impostor: Mapped[int] = mapped_column(Integer, default=0)
    scores_path: Mapped[str] = mapped_column(String(1024), default="")
    det_path: Mapped[str] = mapped_column(String(1024), default="")
    mdd_path: Mapped[str] = mapped_column(String(1024), default="")
    features_path: Mapped[str] = mapped_column(String(1024), default="")
    keras_path: Mapped[str] = mapped_column(String(1024), default="")
    tflite_path: Mapped[str] = mapped_column(String(1024), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    job: Mapped[TrainJob] = relationship(back_populates="folds")


class Artifact(Base):
    """训练产出的文件（模型 / 特征 / 图表 / 文本）。"""

    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("train_jobs.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30), default="other")
    name: Mapped[str] = mapped_column(String(300))
    path: Mapped[str] = mapped_column(String(1024))
    size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    job: Mapped[TrainJob] = relationship(back_populates="artifacts")


class Gallery(Base):
    """识别库：由某个训练任务的模型对某数据集提特征得到。"""

    __tablename__ = "galleries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("train_jobs.id"), nullable=True)
    dataset_id: Mapped[int | None] = mapped_column(ForeignKey("datasets.id"), nullable=True)
    model_name: Mapped[str] = mapped_column(String(60), default="")
    n_classes: Mapped[int] = mapped_column(Integer, default=0)
    n_samples: Mapped[int] = mapped_column(Integer, default=0)
    embedding_dim: Mapped[int] = mapped_column(Integer, default=0)
    path: Mapped[str] = mapped_column(String(1024), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RecognitionLog(Base):
    """识别 / 验证记录。"""

    __tablename__ = "recognition_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gallery_id: Mapped[int | None] = mapped_column(ForeignKey("galleries.id"), nullable=True)
    mode: Mapped[str] = mapped_column(String(20))  # identify | verify
    probe_path: Mapped[str] = mapped_column(String(1024), default="")
    roi_path: Mapped[str] = mapped_column(String(1024), default="")
    predicted_label: Mapped[str] = mapped_column(String(120), default="")
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    matched: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    topk: Mapped[list] = mapped_column(JSON, default=list)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
