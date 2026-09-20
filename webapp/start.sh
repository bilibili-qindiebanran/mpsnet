#!/usr/bin/env bash
# 一键启动 MPSNet 掌静脉识别平台（后端已内置托管前端构建产物）。
#
#   bash webapp/start.sh            # 构建前端（如需要）并启动服务
#   bash webapp/start.sh --dev      # 只启动后端 API（前端用 npm run dev 自行启动）
#   bash webapp/start.sh --port 9000
set -euo pipefail

WEBAPP_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$WEBAPP_DIR")"

DEV_MODE=0
PORT=8000
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dev) DEV_MODE=1; shift ;;
    --port) PORT="$2"; shift 2 ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

# 1. Python 依赖
if [[ ! -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  echo "==> 创建虚拟环境并安装依赖"
  python3 -m venv "$PROJECT_ROOT/.venv"
  "$PROJECT_ROOT/.venv/bin/pip" install -r "$PROJECT_ROOT/Keras_Code/requirements.txt"
fi
"$PROJECT_ROOT/.venv/bin/python" -c "import fastapi" 2>/dev/null || {
  echo "==> 安装 Web 后端依赖"
  "$PROJECT_ROOT/.venv/bin/pip" install -r "$WEBAPP_DIR/backend/requirements.txt"
}

# 2. palmlib（ROI 提取模块）
if [[ ! -x "$PROJECT_ROOT/ROI_Extraction_Code/palmlib" ]]; then
  echo "==> 编译 ROI 提取模块"
  bash "$PROJECT_ROOT/ROI_Extraction_Code/build.sh"
fi

# 3. 前端构建（生产模式）
if [[ "$DEV_MODE" -eq 0 ]]; then
  if [[ ! -d "$WEBAPP_DIR/frontend/node_modules" ]]; then
    echo "==> 安装前端依赖"
    (cd "$WEBAPP_DIR/frontend" && npm install)
  fi
  echo "==> 构建前端"
  (cd "$WEBAPP_DIR/frontend" && npm run build)
fi

# 4. 启动服务
echo "==> 启动 http://127.0.0.1:${PORT}    (API 文档: /docs)"
cd "$WEBAPP_DIR/backend"
exec "$PROJECT_ROOT/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
