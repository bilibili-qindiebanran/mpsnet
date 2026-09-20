"""全局配置：项目路径、工作区目录、外部可执行文件位置。"""
import os
import pathlib

# app/config.py -> app -> backend -> webapp -> <project root>
BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
WEBAPP_DIR = BACKEND_DIR.parent
PROJECT_ROOT = WEBAPP_DIR.parent

# 项目自带的算法代码 / 可执行文件
KERAS_CODE_DIR = PROJECT_ROOT / "Keras_Code"
PALMLIB_BINARY = PROJECT_ROOT / "ROI_Extraction_Code" / "palmlib"
PALMLIB_BUILD_SCRIPT = PROJECT_ROOT / "ROI_Extraction_Code" / "build.sh"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
SYSTEM_PYTHON = "python3"


def _resolve_python() -> str:
    """优先使用项目自带的 .venv（已安装 TensorFlow / Keras / OpenCV）。"""
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return SYSTEM_PYTHON


PYTHON_BIN = _resolve_python()

# 工作区：所有上传、ROI 结果、训练任务、识别库都放在这里
WORKSPACE = pathlib.Path(
    os.environ.get("MPSNET_WORKSPACE", str(PROJECT_ROOT / "webapp_workspace"))
).resolve()

WORKSPACE_DIRS = {
    "root": WORKSPACE,
    "uploads": WORKSPACE / "uploads",
    "roi": WORKSPACE / "roi",
    "jobs": WORKSPACE / "jobs",
    "galleries": WORKSPACE / "galleries",
    "predict": WORKSPACE / "predict",
}

DB_PATH = WORKSPACE / "mpsnet.db"
DATABASE_URL = os.environ.get("MPSNET_DATABASE_URL", f"sqlite:///{DB_PATH}")

# 允许通过 /api/files/raw 读取文件的根目录白名单（数据集可位于项目外）
ALLOWED_FILE_ROOTS = [PROJECT_ROOT, WORKSPACE]

# 训练 / 识别的子进程超时与保存上限
LOG_TAIL_LINES = 400
IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"]

# 前端构建产物（生产模式下由 FastAPI 直接托管）
FRONTEND_DIST = WEBAPP_DIR / "frontend" / "dist"


def ensure_workspace() -> None:
    for path in WORKSPACE_DIRS.values():
        path.mkdir(parents=True, exist_ok=True)


def resolve_path(value: str | pathlib.Path) -> pathlib.Path:
    """相对路径按项目根目录解析，便于直接填 'Images/200_samples/ntust-hp'。"""
    path = pathlib.Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()
