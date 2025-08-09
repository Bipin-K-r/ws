"""
ASGI config for app project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/howto/deployment/asgi/
"""

import os
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")

from django.core.asgi import get_asgi_application
from prometheus_client import Counter, Gauge

logger = logging.getLogger("ws.asgi")

django_asgi_app = get_asgi_application()

METRIC_TOTAL_MESSAGES = Counter("ws_total_messages", "Total websocket messages processed")
METRIC_ACTIVE_CONNECTIONS = Gauge("ws_active_connections", "Active websocket connections")
METRIC_ERROR_COUNT = Counter("ws_error_count", "Errors in websocket handling")
METRIC_LAST_SHUTDOWN_SECONDS = Gauge("ws_last_shutdown_seconds", "Last shutdown duration")

# In-memory connections registry
active_connections: dict[str, dict[str, Any]] = {}
active_connections_lock = asyncio.Lock()


async def _safe_send(send_callable, lock: asyncio.Lock, message: dict):
    """
    sends per-connection using a per-connection asyncio.Lock.
    prevents concurrent awaits on the same send from different tasks.
    """
    try:
        async with lock:
            await send_callable(message)
    except Exception:
        logger.exception("safe_send failed")
        METRIC_ERROR_COUNT.inc()


async def websocket_app(scope, receive, send):
    """
    - counts text messages per-connection
    - replies {"count": n} for each message
    - on close, attempts to send {"bye": true, "total": n}
    """
    if scope["type"] != "websocket":
        raise RuntimeError("websocket_app only handles websocket scopes")

    await send({"type": "websocket.accept"})

    conn_id = uuid.uuid4().hex
    send_lock = asyncio.Lock()

    async with active_connections_lock:
        active_connections[conn_id] = {"send": send, "lock": send_lock}
        METRIC_ACTIVE_CONNECTIONS.inc()

    count = 0
    client = scope.get("client")
    logger.info(json.dumps({"event": "ws.connect", "conn_id": conn_id, "client": client}))

    try:
        while True:
            message = await receive()
            mtype = message.get("type")
            if mtype == "websocket.receive":
                text = message.get("text")
                if text is None:
                    continue
                try:
                    count += 1
                    METRIC_TOTAL_MESSAGES.inc()
                    payload = {"count": count}
                    await _safe_send(send, send_lock, {"type": "websocket.send", "text": json.dumps(payload)})
                except Exception:
                    METRIC_ERROR_COUNT.inc()
                    logger.exception("error while handling websocket.receive")
            elif mtype == "websocket.disconnect":
                break
            else:
                continue
    except Exception:
        METRIC_ERROR_COUNT.inc()
        logger.exception("unhandled websocket exception")
    finally:
        try:
            await _safe_send(send, send_lock, {"type": "websocket.send", "text": json.dumps({"bye": True, "total": count})})
        except Exception:
            pass

        async with active_connections_lock:
            if conn_id in active_connections:
                del active_connections[conn_id]
                try:
                    METRIC_ACTIVE_CONNECTIONS.dec()
                except Exception:
                    pass

        logger.info(json.dumps({"event": "ws.disconnect", "conn_id": conn_id, "total": count, "client": client}))


async def heartbeater(stop_event: asyncio.Event):
    """
    sends a heartbeat to all active connections every 30s.
    sends to connections in parallel but with per-connection send locks
    """
    while not stop_event.is_set():
        ts = datetime.now(timezone.utc).isoformat()
        payload_text = json.dumps({"ts": ts})

        async with active_connections_lock:
            conn_items = list(active_connections.items())

        if conn_items:
            tasks = []
            for _, info in conn_items:
                send_callable = info["send"]
                lock = info["lock"]
                tasks.append(asyncio.create_task(_safe_send(send_callable, lock, {"type": "websocket.send", "text": payload_text})))
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5.0)
            except Exception:
                logger.exception("heartbeater send gather timed out or failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            continue


async def lifespan(scope, receive, send):
    if scope["type"] != "lifespan":
        return

    stop_event = asyncio.Event()
    hb_task = None

    while True:
        message = await receive()
        mtype = message["type"]

        if mtype == "lifespan.startup":
            hb_task = asyncio.create_task(heartbeater(stop_event))
            await send({"type": "lifespan.startup.complete"})

        elif mtype == "lifespan.shutdown":
            start = asyncio.get_event_loop().time()
            stop_event.set()

            if hb_task:
                try:
                    await asyncio.wait_for(hb_task, timeout=2.0)
                except Exception:
                    hb_task.cancel()

            async with active_connections_lock:
                items = list(active_connections.items())
                active_connections.clear()
                try:
                    METRIC_ACTIVE_CONNECTIONS.set(0)
                except Exception:
                    pass

            if items:
                close_tasks = []
                for _, info in items:
                    send_callable = info["send"]
                    lock = info["lock"]

                    async def _close_one(snd, lck):
                        try:
                            async with lck:
                                await snd({"type": "websocket.close", "code": 1001})
                        except Exception:
                            pass

                    close_tasks.append(asyncio.create_task(_close_one(send_callable, lock)))

                try:
                    await asyncio.wait_for(asyncio.gather(*close_tasks, return_exceptions=True), timeout=8.0)
                except Exception:
                    pass

            duration = asyncio.get_event_loop().time() - start
            METRIC_LAST_SHUTDOWN_SECONDS.set(duration)

            await send({"type": "lifespan.shutdown.complete"})
            return


async def application(scope, receive, send):
    if scope["type"] == "lifespan":
        return await lifespan(scope, receive, send)

    if scope["type"] == "websocket" and scope.get("path", "").startswith("/ws/chat/"):
        return await websocket_app(scope, receive, send)

    return await django_asgi_app(scope, receive, send)
