"""Vecna Channel System — multi-channel message delivery."""

from vecna.channels.base import (
    BaseChannel,
    InboundMessage,
    OutboundMessage,
    ChannelCapability,
)

__all__ = [
    "BaseChannel",
    "InboundMessage",
    "OutboundMessage",
    "ChannelCapability",
]
