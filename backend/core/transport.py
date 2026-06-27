import asyncio
import json
from collections import defaultdict
from typing import Any, AsyncIterator

from .interfaces import Transport


class SSETransport(Transport):
    def __init__(self) -> None:
        self._subscribers: dict[int, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    async def push(self, channel_id: int, event: dict[str, Any]) -> None:
        payload = {"channel_id": channel_id, **event}
        for queue in list(self._subscribers.get(channel_id, set())):
            await queue.put(payload)

    def push_nowait(self, channel_id: int, event: dict[str, Any]) -> None:
        payload = {"channel_id": channel_id, **event}
        for queue in list(self._subscribers.get(channel_id, set())):
            queue.put_nowait(payload)

    async def subscribe(self, channel_id: int) -> AsyncIterator[str]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers[channel_id].add(queue)
        try:
            yield "event: ready\ndata: {}\n\n"
            while True:
                event = await queue.get()
                event_type = event.get("type", "message")
                data = json.dumps(event, ensure_ascii=False)
                yield f"event: {event_type}\ndata: {data}\n\n"
        finally:
            self._subscribers[channel_id].discard(queue)
            if not self._subscribers[channel_id]:
                self._subscribers.pop(channel_id, None)


transport = SSETransport()
