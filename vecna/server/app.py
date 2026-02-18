"""
Vecna HTTP Server.

Provides REST API and WebSocket endpoints for interacting with Vecna
from any client (channels, integrations, UIs).

Amendment 3: All inbound messages flow through MessageRouter (when wired in Task 26).
The HTTP server delegates to the router, never calling HiveLoop.think() directly.
"""

import logging
from typing import Optional

from aiohttp import web

from vecna.server.routes import setup_routes

logger = logging.getLogger("vecna.server")


def create_app(
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> web.Application:
    """Create the aiohttp application.

    Parameters
    ----------
    host : str, optional
        Host to bind to (stored on app for reference, not used by create_app itself).
    port : int, optional
        Port to bind to (stored on app for reference, not used by create_app itself).
    """
    app = web.Application()
    setup_routes(app)

    # Store shared state — lazy-initialized on first /api/state request
    app["hive_state"] = None
    app["sessions"] = {}
    app["message_router"] = None  # Wired in Task 26

    # Store bind info for logging/reference
    app["host"] = host or "127.0.0.1"
    app["port"] = port or 8420

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
