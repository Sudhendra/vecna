"""Vecna HTTP Server.

Provides REST API and WebSocket endpoints for interacting with Vecna
from any client (channels, integrations, UIs).

Amendment 3: All inbound messages flow through MessageRouter (when wired).
The HTTP server delegates to the router, never calling HiveLoop.think() directly
when a MessageRouter is available. When no router is present, falls back to
HiveLoop.think() for direct integration.

Task 26: Wire HiveLoop into the server. create_app() now accepts adapters,
config, or a pre-built HiveLoop instance.
"""

import logging
from typing import Any, Awaitable, Callable, List, Optional

from aiohttp import web

from vecna.server.routes import setup_routes

logger = logging.getLogger("vecna.server")


class _NoopChannel:
    """Minimal channel implementation for router registration."""

    async def send(self, _message: str) -> None:
        return None


def _extract_api_key(config: Optional[Any], explicit_api_key: Optional[str]) -> Optional[str]:
    """Extract API key from explicit argument or config object."""
    if explicit_api_key:
        return explicit_api_key

    if config is None:
        return None

    if isinstance(config, dict):
        for key in ("api_key", "server_api_key", "http_api_key"):
            value = config.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    for attr in ("api_key", "server_api_key", "http_api_key"):
        value = getattr(config, attr, None)
        if isinstance(value, str) and value.strip():
            return value

    return None


@web.middleware
async def cors_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    """Add permissive CORS headers for API and WebSocket endpoints."""
    if request.method == "OPTIONS":
        response: web.StreamResponse = web.Response(status=204)
    else:
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            response = exc

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization,X-API-Key"
    response.headers["Access-Control-Max-Age"] = "3600"
    return response


@web.middleware
async def api_key_auth_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    """Enforce API key auth when app['api_key'] is configured."""
    configured_key = request.app.get("api_key")
    if not configured_key:
        return await handler(request)

    if request.path == "/api/health" or request.method == "OPTIONS":
        return await handler(request)

    provided_key = request.headers.get("X-API-Key", "")
    if provided_key != configured_key:
        return web.json_response({"error": "Unauthorized"}, status=401)

    return await handler(request)


async def on_startup(app: web.Application) -> None:
    """Initialize resources on server startup."""
    logger.info("Vecna server starting up")


async def on_shutdown(app: web.Application) -> None:
    """Clean up resources on server shutdown."""
    logger.info("Vecna server shutting down")


def create_app(
    host: Optional[str] = None,
    port: Optional[int] = None,
    adapters: Optional[List[Any]] = None,
    config: Optional[Any] = None,
    hive_loop: Optional[Any] = None,
    api_key: Optional[str] = None,
) -> web.Application:
    """Create the aiohttp application.

    Supports three modes:
    1. **Pre-built HiveLoop** — pass ``hive_loop`` directly.
    2. **Adapters + config** — builds a HiveLoop from the given adapters.
    3. **No args** — backward-compatible placeholder mode (no HiveLoop).

    Parameters
    ----------
    host : str, optional
        Host to bind to (stored on app for reference, not used by create_app itself).
    port : int, optional
        Port to bind to (stored on app for reference, not used by create_app itself).
    adapters : list of BaseAdapter, optional
        LLM adapters to initialize a HiveLoop with.
    config : HiveConfig or VecnaConfig, optional
        Configuration for the HiveLoop.
    hive_loop : HiveLoop, optional
        A pre-built HiveLoop instance. Takes precedence over adapters/config.
    """
    app = web.Application(middlewares=[cors_middleware, api_key_auth_middleware])

    # Wire HiveLoop into the app
    loop = None
    if hive_loop is not None:
        loop = hive_loop
    elif adapters is not None:
        from vecna.orchestrator.loop import HiveConfig, HiveLoop

        hive_config = config if config is not None else HiveConfig()
        loop = HiveLoop(
            config=hive_config,
            adapters=adapters,
            name="vecna-server",
        )

    app["hive_loop"] = loop

    message_router = None
    if loop is not None:
        from vecna.channels.router import MessageRouter

        message_router = MessageRouter(hive_loop=loop)
        message_router.register_channel("http", _NoopChannel())
        message_router.register_channel("websocket", _NoopChannel())

    # Backward-compatible keys
    app["hive_state"] = None
    app["sessions"] = {}
    app["message_router"] = message_router
    app["api_key"] = _extract_api_key(config, api_key)

    # Store bind info for logging/reference
    app["host"] = host or "127.0.0.1"
    app["port"] = port or 8420

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    setup_routes(app)

    if loop is not None:
        logger.info(
            "Vecna server app created with HiveLoop (%d adapters)",
            len(loop.adapters),
        )
    else:
        logger.info("Vecna server app created (placeholder mode, no HiveLoop)")

    return app


def run_server(host: str = "127.0.0.1", port: int = 8420) -> None:
    """Run the Vecna HTTP server.

    Parameters
    ----------
    host : str
        Host to bind to. Defaults to 127.0.0.1 (localhost only).
    port : int
        Port to listen on. Defaults to 8420.
    """
    app = create_app(host=host, port=port)
    logger.info("Starting Vecna server on %s:%d", host, port)
    web.run_app(app, host=host, port=port)
