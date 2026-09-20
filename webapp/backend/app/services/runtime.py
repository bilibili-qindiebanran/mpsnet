"""后台子进程管理：启动训练 / 建库脚本，落日志，支持中断。"""
from __future__ import annotations

import codecs
import os
import re
import signal
import subprocess
import threading
import time
import traceback
from collections.abc import Callable
from pathlib import Path

from ..config import LOG_TAIL_LINES


class BackgroundProcess:
    """把一个外部命令包装成可查询、可中断的后台任务。"""

    def __init__(
        self,
        cmd: list[str],
        cwd: Path,
        log_path: Path,
        env: dict[str, str] | None = None,
        on_start: Callable[[], None] | None = None,
        on_line: Callable[[str], None] | None = None,
        on_finish: Callable[[int, str], None] | None = None,
    ) -> None:
        self.cmd = cmd
        self.cwd = str(cwd)
        self.log_path = Path(log_path)
        self.env = env
        self.on_start = on_start
        self.on_line = on_line
        self.on_finish = on_finish

        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._log_handle = None
        self._status = "pending"
        self._error = ""
        self._lines: list[str] = []

    # ---------- 状态 ----------
    @property
    def status(self) -> str:
        return self._status

    @property
    def error(self) -> str:
        return self._error

    @property
    def running(self) -> bool:
        return self._status == "running"

    def tail(self, n: int = LOG_TAIL_LINES) -> str:
        return "\n".join(self._lines[-n:])

    # ---------- 控制 ----------
    def start(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        # 强制赋值而非 setdefault：父进程若带了其他值会影响子进程的输出实时性
        env["MPLBACKEND"] = env.get("MPLBACKEND") or "Agg"
        env["PYTHONUNBUFFERED"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        if self.env:
            env.update(self.env)

        self._status = "running"
        self._lines.clear()
        if self.on_start:
            self.on_start()

        # 子进程 stdout/stderr 直接落到日志文件：
        # 不经过管道就不会因缓冲区写满而卡住，进程被杀时日志也不会丢。
        self._log_handle = self.log_path.open("w", encoding="utf-8")
        self._proc = subprocess.Popen(
            self.cmd,
            cwd=self.cwd,
            env=env,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._thread = threading.Thread(target=self._tail, daemon=True)
        self._thread.start()

    def _handle_line(self, line: str) -> None:
        self._lines.append(line)
        if len(self._lines) > 4000:
            del self._lines[:2000]
        if self.on_line:
            try:
                self.on_line(line)
            except Exception:  # 回调不应影响主流程
                pass

    def _drain(self, buffer: str, end: bool = False) -> str:
        """按 \\r / \\n 切分成行（Keras 进度条用 \\r 刷新），返回未构成整行的残留。"""
        parts = re.split(r"[\r\n]", buffer)
        tail = "" if end else parts.pop()
        for part in parts:
            if part.strip():
                self._handle_line(part.rstrip())
        return tail

    def _tail(self) -> None:
        """读取日志文件的新增内容；子进程直接写文件，因此不会被缓冲区卡住。"""
        assert self._proc is not None
        try:
            self._tail_loop()
        except Exception:  # 采集失败也不能让任务永远停在 running
            traceback.print_exc()
            self._error = self._error or "日志采集线程异常"
        finally:
            code = self._proc.wait()
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._status = "success" if code == 0 else "failed"
            if code != 0 and not self._error:
                self._error = f"进程退出码 {code}"
            if self.on_finish:
                try:
                    self.on_finish(code, self._error)
                except Exception:
                    traceback.print_exc()

    def _tail_loop(self) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        buffer = ""
        position = 0

        while True:
            try:
                with self.log_path.open("rb") as handle:
                    handle.seek(position)
                    chunk = handle.read()
                    position = handle.tell()
            except OSError:
                chunk = b""

            if chunk:
                buffer = self._drain(buffer + decoder.decode(chunk))
            elif self._proc.poll() is not None:
                break
            else:
                time.sleep(0.15)

        self._drain(buffer + decoder.decode(b"", True), end=True)

    def stop(self) -> None:
        if self._proc is None or self._proc.poll() is not None:
            return
        self._error = "已被用户中断"
        try:
            os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
        except Exception:
            self._proc.terminate()
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
            except Exception:
                self._proc.kill()
        self._status = "stopped"


class ProcessManager:
    """进程注册表，按 key（如 train:1 / gallery:2）索引。"""

    def __init__(self) -> None:
        self._procs: dict[str, BackgroundProcess] = {}
        self._lock = threading.Lock()

    def register(self, key: str, proc: BackgroundProcess) -> None:
        with self._lock:
            self._procs[key] = proc

    def get(self, key: str) -> BackgroundProcess | None:
        with self._lock:
            return self._procs.get(key)

    def pop(self, key: str) -> BackgroundProcess | None:
        with self._lock:
            return self._procs.pop(key, None)

    def running_keys(self) -> list[str]:
        with self._lock:
            return [k for k, p in self._procs.items() if p.running]

    def stop(self, key: str) -> bool:
        proc = self.get(key)
        if proc is None or not proc.running:
            return False
        proc.stop()
        return True


manager = ProcessManager()
