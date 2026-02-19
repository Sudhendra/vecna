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
from typing import Any, List, Optional

from aiohttp import web

from vecna.server.routes import setup_routes

logger = logging.getLogger("vecna.server")


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
    app = web.Application()

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

    # Backward-compatible keys
    app["hive_state"] = None
    app["sessions"] = {}
    app["message_router"] = None

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
