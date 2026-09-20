"""接口的请求 / 响应模型。"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


# ---------- 数据集 ----------
class DatasetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    path: str = Field(..., description="数据集根目录，结构为 <root>/<Palm_ID>/<image>")
    image_extension: str = ".png"
    description: str = ""


class DatasetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    image_extension: str | None = None


class DatasetOut(ORMBase):
    id: int
    name: str
    path: str
    image_extension: str
    description: str
    n_classes: int
    n_images: int
    class_stats: dict
    created_at: datetime
    updated_at: datetime


class DatasetClassStat(BaseModel):
    label: str
    count: int
    samples: list[str] = []


class DatasetScanResult(BaseModel):
    n_classes: int
    n_images: int
    classes: list[DatasetClassStat]


# ---------- ROI 提取 ----------
class RoiExtractRequest(BaseModel):
    name: str = "ROI 提取"
    source_path: str = Field(..., description="服务器上的图片文件或目录")
    roi_size: int = 128
    save_debug: bool = False


class RoiJobOut(ORMBase):
    id: int
    name: str
    source_type: str
    source_path: str
    output_dir: str
    roi_size: int
    save_debug: bool
    status: str
    total: int
    succeeded: int
    failed: int
    results: list
    log: str
    error: str
    created_at: datetime
    finished_at: datetime | None


# ---------- 预设 ----------
class PresetIn(BaseModel):
    name: str
    description: str = ""
    params: dict[str, Any]


class PresetOut(ORMBase):
    id: int
    name: str
    description: str
    params: dict
    created_at: datetime
    updated_at: datetime


# ---------- 训练 ----------
class TrainJobCreate(BaseModel):
    name: str = ""
    dataset_id: int = Field(..., description="测试集数据集；也是默认的训练集")
    n_sessions: int = Field(1, description="测试集会话数，与 test_folders.txt 第二列一致")
    model_name: str = "mpsnet"
    params: dict[str, Any] = {}
    retrain_softmax: bool = True
    retrain_fine_tune: bool = True
    convert_to_tflite: bool = True


class FoldResultOut(ORMBase):
    id: int
    job_id: int
    fold: int
    eer: float | None
    threshold: float | None
    frr: float | None
    far: float | None
    n_genuine: int
    n_impostor: int
    scores_path: str
    det_path: str
    mdd_path: str
    features_path: str
    keras_path: str
    tflite_path: str


class ArtifactOut(ORMBase):
    id: int
    kind: str
    name: str
    path: str
    size: int
    created_at: datetime


class TrainJobOut(ORMBase):
    id: int
    name: str
    dataset_id: int | None
    test_folder: str
    n_sessions: int
    model_name: str
    params: dict
    retrain_softmax: bool
    retrain_fine_tune: bool
    convert_to_tflite: bool
    status: str
    progress: dict
    output_dir: str
    error: str
    best_eer: float | None
    avg_eer: float | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class TrainJobDetail(TrainJobOut):
    folds: list[FoldResultOut] = []
    artifacts: list[ArtifactOut] = []


# ---------- 识别 / 验证 ----------
class GalleryCreate(BaseModel):
    name: str = ""
    job_id: int
    dataset_id: int


class GalleryOut(ORMBase):
    id: int
    name: str
    job_id: int | None
    dataset_id: int | None
    model_name: str
    n_classes: int
    n_samples: int
    embedding_dim: int
    path: str
    status: str
    error: str
    created_at: datetime
    finished_at: datetime | None


class GalleryIdentity(BaseModel):
    label: str
    count: int
    preview: str | None = None


class VerifyRequest(BaseModel):
    gallery_id: int
    claim: str = Field(..., description="待验证的身份标签 (Palm_ID)")
    threshold: float | None = None
    roi_size: int = 128


class RecognitionLogOut(ORMBase):
    id: int
    gallery_id: int | None
    mode: str
    probe_path: str
    roi_path: str
    predicted_label: str
    distance: float | None
    threshold: float | None
    matched: bool | None
    topk: list
    elapsed_ms: int
    created_at: datetime
