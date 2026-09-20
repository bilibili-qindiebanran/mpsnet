"""模型推理封装：TFLite / Keras 两种后端，统一输出 L2 特征向量。

优先使用 train.py 导出的 TFLite 模型（输出层即 embedding 层，单输入、无自定义层，
加载最稳）；没有 TFLite 时回退到 .keras 模型并截取 embedding 层。
"""
from __future__ import annotations

import pathlib
import threading

import numpy as np

KERAS_CODE_DIR = pathlib.Path(__file__).resolve().parents[3] / "Keras_Code"

_cache: dict[str, "BaseEmbedder"] = {}
_cache_lock = threading.Lock()


class EmbedderError(RuntimeError):
    pass


class BaseEmbedder:
    input_size: int
    embedding_dim: int
    model_path: str

    def embed(self, images: np.ndarray) -> np.ndarray:
        """images: (N, H, W, 1) float32 in [0, 1] -> (N, D) float32"""
        raise NotImplementedError

    def embed_one(self, image: np.ndarray) -> np.ndarray:
        return self.embed(image[None, ...])[0]


class TfliteEmbedder(BaseEmbedder):
    def __init__(self, model_path: str):
        import tensorflow as tf

        self.model_path = model_path
        self._interp = tf.lite.Interpreter(model_path=model_path)
        self._interp.allocate_tensors()
        self._input = self._interp.get_input_details()[0]
        self._output = self._interp.get_output_details()[0]

        shape = self._input["shape"]
        self.input_size = int(shape[1])
        self._channels = int(shape[3]) if len(shape) == 4 else 1
        self.embedding_dim = int(self._output["shape"][-1])

    def _run(self, batch: np.ndarray) -> np.ndarray:
        self._interp.set_tensor(self._input["index"], batch.astype(np.float32))
        self._interp.invoke()
        return np.asarray(self._interp.get_tensor(self._output["index"]), dtype=np.float32)

    def embed(self, images: np.ndarray) -> np.ndarray:
        images = prepare_images(images, self.input_size, self._channels)
        try:
            self._interp.resize_tensor_input(
                self._input["index"], list(images.shape), strict=False
            )
            self._interp.allocate_tensors()
            return self._run(images)
        except Exception:
            # 动态 batch 不支持的模型逐张推理
            return np.vstack([self._run(img[None, ...]) for img in images])


class KerasEmbedder(BaseEmbedder):
    def __init__(self, model_path: str, embedding_layer: str = "embeddings"):
        import sys

        if str(KERAS_CODE_DIR) not in sys.path:
            sys.path.insert(0, str(KERAS_CODE_DIR))
        import keras

        from model.adacos import AdaCos

        self.model_path = model_path
        model = keras.models.load_model(
            model_path, compile=False, custom_objects={"AdaCos": AdaCos}
        )
        try:
            embedding = model.get_layer(embedding_layer).output
            inputs = model.inputs[0] if isinstance(model.inputs, (list, tuple)) else model.inputs
            self._model = keras.Model(inputs=inputs, outputs=embedding)
        except Exception as exc:
            raise EmbedderError(
                f"无法从 {model_path} 取出特征层 '{embedding_layer}'：{exc}"
            ) from exc

        shape = self._model.input_shape
        self.input_size = int(shape[1])
        self._channels = int(shape[3]) if len(shape) == 4 else 1
        self.embedding_dim = int(self._model.output_shape[-1])

    def embed(self, images: np.ndarray) -> np.ndarray:
        images = prepare_images(images, self.input_size, self._channels)
        return np.asarray(self._model.predict(images, verbose=0), dtype=np.float32)


def prepare_images(images: np.ndarray, size: int, channels: int = 1) -> np.ndarray:
    """统一到 (N, size, size, channels) 的 float32。"""
    import cv2

    images = np.asarray(images)
    if images.ndim == 2:
        images = images[None, ...]
    if images.ndim == 3 and images.shape[-1] not in (1, 3):
        images = images[..., None]
    if images.ndim == 3:
        images = images[None, ...]

    out = []
    for img in images:
        if img.shape[0] != size or img.shape[1] != size:
            img = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
        if img.ndim == 2:
            img = img[..., None]
        if channels == 1 and img.shape[-1] != 1:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)[..., None]
        elif channels == 3 and img.shape[-1] == 1:
            img = np.repeat(img, 3, axis=-1)
        out.append(img)
    return np.asarray(out, dtype=np.float32)


def load_image_gray(path: str | pathlib.Path, size: int | None = None) -> np.ndarray:
    """按训练一致的方式读取：灰度 + 归一化到 [0, 1]。"""
    import cv2

    img = cv2.imread(str(path), 0)
    if img is None:
        raise EmbedderError(f"无法读取图片：{path}")
    if size:
        img = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
    return (img.astype(np.float32) / 255.0)[..., None]


def get_embedder(model_path: str, embedding_layer: str = "embeddings") -> BaseEmbedder:
    path = pathlib.Path(model_path)
    if not path.exists():
        raise EmbedderError(f"模型文件不存在：{model_path}")

    key = f"{path.resolve()}::{embedding_layer}"
    with _cache_lock:
        cached = _cache.get(key)
        if cached is not None:
            return cached
        if path.suffix.lower() == ".tflite":
            embedder = TfliteEmbedder(str(path))
        elif path.suffix.lower() in (".keras", ".h5"):
            embedder = KerasEmbedder(str(path), embedding_layer)
        else:
            raise EmbedderError(f"不支持的模型格式：{path.suffix}")
        _cache[key] = embedder
        return embedder


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def cosine_distances(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    """与 sklearn.pairwise_distances(metric='cosine') 一致：1 - 余弦相似度。"""
    matrix = np.asarray(matrix, dtype=np.float32)
    vector = np.asarray(vector, dtype=np.float32)
    denominator = (np.linalg.norm(matrix, axis=1) * np.linalg.norm(vector)) + 1e-12
    similarity = (matrix @ vector) / denominator
    return 1.0 - np.clip(similarity, -1.0, 1.0)
