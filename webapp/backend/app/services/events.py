"""SSE 推送：轮询数据库快照并推给前端，用于实时查看任务进度。"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

from fastapi.responses import StreamingResponse

TERMINAL_STATUS = {"success", "failed", "stopped"}


def event_stream(
    snapshot: Callable[[], dict | None],
    interval: float = 1.0,
    keepalive_ticks: int = 15,
):
    async def generator():
        last: str | None = None
        idle = 0
        while True:
            payload = snapshot()
            if payload is None:
                yield 'event: error\ndata: {"message": "记录不存在"}\n\n'
                return
            data = json.dumps(payload, ensure_ascii=False, default=str)
            if data != last:
                yield f"data: {data}\n\n"
                last = data
                idle = 0
            else:
                idle += 1
                if idle >= keepalive_ticks:
                    yield ": keepalive\n\n"
                    idle = 0
            if payload.get("status") in TERMINAL_STATUS:
                yield "event: end\ndata: {}\n\n"
                return
            await asyncio.sleep(interval)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
