"""API route handlers for the Vecna server.

All endpoints follow REST conventions:
- GET  /api/health           -- Health check
- POST /api/chat             -- Send a message to Vecna
- GET  /api/state            -- Get current hive state summary
- GET  /api/metrics          -- System-wide observability metrics
- POST /api/webhooks/ingest  -- Ingest external webhook events
- WS   /ws/stream            -- WebSocket streaming (authenticated)

Amendment 3: Chat endpoint delegates to MessageRouter.route_inbound() first.
When no MessageRouter is wired, falls back to HiveLoop.think() (Task 26).
Amendment 8: All exceptions are caught with specific types.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict

from aiohttp import web

if TYPE_CHECKING:
    from vecna.observability.dashboard import MetricsCollector

logger = logging.getLogger("vecna.server")


async def health(request: web.Request) -> web.Response:
    """Health check endpoint.

    Returns server status, version, and current timestamp.
    When a HiveLoop is wired, also returns state_version and adapter_count.
    """
    data = {
        "status": "ok",
        "version": "0.1.0",
        "timestamp": datetime.now().isoformat(),
    }

    hive_loop = request.app.get("hive_loop")
    if hive_loop is not None:
        data["state_version"] = hive_loop.state.version
        data["adapter_count"] = len(hive_loop.adapters)

    return web.json_response(data)


async def chat(request: web.Request) -> web.Response:
    """Chat endpoint -- send a message to Vecna.

    Expects JSON body with:
    - message (str, required): The user message
    - session_id (str, optional): Session identifier, defaults to "default"

    Amendment 3: Delegates to MessageRouter.route_inbound() when available.
    Falls back to HiveLoop.think() when a HiveLoop is wired (Task 26).
    Falls back to placeholder if neither is available.
    """
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    message = data.get("message", "")
    session_id = data.get("session_id", "default")

    if not message or not message.strip():
        return web.json_response({"error": "Message required"}, status=400)

    # Priority 1: MessageRouter (Amendment 3)
    router = request.app.get("message_router")
    if router is not None:
        from vecna.channels.router import InboundMessage, RateLimitError, RoutingError

        try:
            inbound = InboundMessage(
                content=message,
                channel_name="http",
                session_id=session_id,
            )
            outbound = await router.route_inbound(inbound)
            return web.json_response(
                {
                    "response": outbound.content,
                    "session_id": session_id,
                    "format_type": outbound.format_type,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        except asyncio.TimeoutError:
            logger.warning("Chat request timed out for session %s", session_id)
            return web.json_response({"error": "Request timed out"}, status=504)
        except RateLimitError:
            logger.warning("Rate limit exceeded for session %s", session_id)
            return web.json_response({"error": "Rate limit exceeded"}, status=429)
        except RoutingError as exc:
            logger.error("Routing error for session %s: %s", session_id, exc)
            return web.json_response({"error": "Internal routing error"}, status=500)
        except ValueError as exc:
            logger.warning("Invalid chat request: %s", exc)
            return web.json_response({"error": str(exc)}, status=400)

    # Priority 2: HiveLoop.think() (Task 26)
    hive_loop = request.app.get("hive_loop")
    if hive_loop is not None:
        try:
            response_text = await hive_loop.think(message)
        except ValueError as exc:
            # HiveLoop raises ValueError when no adapters are configured
            logger.error("HiveLoop.think failed (ValueError): %s", exc)
            return web.json_response({"error": "Internal processing error"}, status=500)
        except asyncio.TimeoutError:
            logger.warning("HiveLoop.think timed out for session %s", session_id)
            return web.json_response({"error": "Request timed out"}, status=504)
        except RuntimeError as exc:
            logger.error("HiveLoop.think runtime error: %s", exc)
            return web.json_response({"error": "Internal processing error"}, status=500)

        return web.json_response(
            {
                "response": response_text,
                "state_version": hive_loop.state.version,
                "session_id": session_id,
                "timestamp": datetime.now().isoformat(),
            }
        )

    # Priority 3: Placeholder response when nothing is wired
    return web.json_response(
        {
            "response": f"[Vecna server placeholder] Received: {message}",
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
        }
    )


async def get_state(request: web.Request) -> web.Response:
    """Get current hive state.

    When a HiveLoop is wired (Task 26), returns HiveLoop's state as full dict.
    Otherwise, lazily initializes a standalone HiveState and returns its summary.
    """
    # Priority 1: HiveLoop state (Task 26)
    hive_loop = request.app.get("hive_loop")
    if hive_loop is not None:
        return web.json_response(hive_loop.state.to_full_dict())

    # Fallback: standalone HiveState (backward compat)
    from vecna.core.hive_state import HiveState

    state = request.app.get("hive_state")
    if state is None:
        state = HiveState()
        state.ensure_identity()
        request.app["hive_state"] = state

    return web.json_response(state.to_summary_dict())


async def webhook_ingest(request: web.Request) -> web.Response:
    """Ingest webhook events from external services.

    Expects JSON body with:
    - source (str, optional): Event source (e.g. "github"), defaults to "unknown"
    - event (str, optional): Event type (e.g. "push"), defaults to "unknown"
    - payload (dict, optional): Event payload data
    """
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    source = data.get("source", "unknown")
    event = data.get("event", "unknown")

    logger.info("Webhook received: %s/%s", source, event)

    # TODO: Route to BackgroundObserver in Task 14
    return web.json_response(
        {
            "status": "accepted",
            "source": source,
            "event": event,
        }
    )


async def ws_stream(request: web.Request) -> web.WebSocketResponse:
    """WebSocket streaming endpoint.

    When a HiveLoop is wired (Task 26), delegates to HiveLoop.think().
    When a MessageRouter is wired (Amendment 3), delegates to route_inbound().
    Requires authentication via token query parameter or header.
    Unauthenticated connections are immediately closed.

    Amendment 10: Must reject unauthenticated connections.
    """
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # Check for auth token (query param or header)
    token = request.query.get("token") or request.headers.get("Authorization")
    if not token:
        logger.warning("WebSocket connection rejected: no auth token")
        await ws.close(code=4001, message=b"Authentication required")
        return ws

    # TODO: Validate token against auth system
    # For now, accept any non-empty token
    logger.info("WebSocket connection established")

    hive_loop = request.app.get("hive_loop")
    ws_router = request.app.get("message_router")

    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                # Parse incoming JSON
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    await ws.send_json({"error": "Invalid JSON"})
                    continue

                message = data.get("message", "")
                if not message:
                    await ws.send_json({"error": "message field required"})
                    continue

                # Priority 1: MessageRouter (Amendment 3)
                if ws_router is not None:
                    from vecna.channels.router import InboundMessage

                    inbound = InboundMessage(
                        content=message,
                        channel_name="websocket",
                        session_id=request.query.get("session_id", "ws-default"),
                    )
                    try:
                        outbound = await ws_router.route_inbound(inbound)
                        await ws.send_json(
                            {
                                "response": outbound.content,
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                    except (ValueError, ImportError) as exc:
                        await ws.send_json(
                            {
                                "error": str(exc),
                                "timestamp": datetime.now().isoformat(),
                            }
                        )

                # Priority 2: HiveLoop (Task 26)
                elif hive_loop is not None:
                    try:
                        response = await hive_loop.think(message)
                        await ws.send_json({"response": response})
                    except ValueError as exc:
                        logger.error("WebSocket HiveLoop error: %s", exc)
                        await ws.send_json({"error": "Processing failed"})
                    except asyncio.TimeoutError:
                        logger.warning("WebSocket HiveLoop.think timed out")
                        await ws.send_json({"error": "Request timed out"})
                    except RuntimeError as exc:
                        logger.error("WebSocket runtime error: %s", exc)
                        await ws.send_json({"error": "Processing failed"})

                # Priority 3: Echo fallback
                else:
                    await ws.send_str(
                        json.dumps(
                            {
                                "echo": msg.data,
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                    )
            elif msg.type == web.WSMsgType.ERROR:
                logger.error("WebSocket error: %s", ws.exception())
    except asyncio.CancelledError:
        logger.info("WebSocket connection cancelled")

    logger.info("WebSocket connection closed")
    return ws


def handle_metrics_request(collector: "MetricsCollector") -> Dict[str, Any]:
    """Build the metrics report from a MetricsCollector.

    This is a pure function that converts collector state into a
    JSON-serializable dict. Used by the /api/metrics HTTP handler
    and available for direct use in tests.

    Args:
        collector: The MetricsCollector instance to report on.

    Returns:
        Full metrics report as a dict.
    """
    return collector.to_full_report()


async def metrics(request: web.Request) -> web.Response:
    """System-wide observability metrics endpoint.

    Returns the full metrics report from the MetricsCollector
    when one is wired into the application. Returns an empty
    report structure when no collector is available.
    """
    collector = request.app.get("metrics_collector")
    if collector is None:
        return web.json_response({"error": "Metrics collector not configured"}, status=503)
    report = handle_metrics_request(collector)
    return web.json_response(report)


def setup_routes(app: web.Application) -> None:
    """Register all API routes on the application."""
    app.router.add_get("/api/health", health)
    app.router.add_post("/api/chat", chat)
    app.router.add_get("/api/state", get_state)
    app.router.add_get("/api/metrics", metrics)
    app.router.add_post("/api/webhooks/ingest", webhook_ingest)
    app.router.add_get("/ws/stream", ws_stream)
