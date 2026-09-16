#!/usr/bin/env bash
# Build palmlib on macOS / Linux.
# Requires an OpenCV dev package:
#   macOS : brew install opencv pkg-config
#   Ubuntu: sudo apt install libopencv-dev pkg-config
set -euo pipefail
cd "$(dirname "$0")"

FLAGS=""

# OpenCV 5 installs opencv5.pc, OpenCV 4 installs opencv4.pc, older ones opencv.pc
for module in opencv5 opencv4 opencv; do
  if pkg-config --exists "$module" 2>/dev/null; then
    FLAGS="$(pkg-config --cflags --libs "$module")"
    echo "Using pkg-config module: $module ($(pkg-config --modversion "$module"))"
    break
  fi
done

# Fallback for a Homebrew OpenCV without pkg-config metadata
if [ -z "$FLAGS" ] && command -v brew >/dev/null 2>&1; then
  P="$(brew --prefix)"
  for inc in opencv5 opencv4; do
    if [ -d "$P/include/$inc" ]; then
      FLAGS="-I$P/include/$inc -L$P/lib -lopencv_core -lopencv_imgproc -lopencv_imgcodecs"
      echo "Using Homebrew include dir: $P/include/$inc"
      break
    fi
  done
fi

if [ -z "$FLAGS" ]; then
  echo "ERROR: OpenCV dev package not found. Install it first (see the comments in this script)." >&2
  exit 1
fi

"${CXX:-c++}" -std=c++17 -O2 palmlib.cpp -o palmlib $FLAGS
echo "Built ./palmlib"
echo "Usage: ./palmlib <input_image_or_dir> <output_dir> [--roi-size 128] [--save-debug]"
