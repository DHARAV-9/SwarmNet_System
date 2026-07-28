from __future__ import annotations

import json
from typing import Any


def encode(msg: dict[str, Any]) -> bytes:
    """Serialize a message dict to UTF-8 JSON bytes.

    Args:
        msg: A dict matching one of the message schemas defined in
             the TRD (vote_request, vote_response, append_entries, etc.).

    Returns:
        UTF-8 encoded JSON bytes ready to send over a ZeroMQ frame.
    """
    return json.dumps(msg, separators=(",", ":")).encode("utf-8")


def decode(data: bytes) -> dict[str, Any]:
    """Deserialize UTF-8 JSON bytes back to a Python dict.

    Args:
        data: Raw bytes received from a ZeroMQ socket.

    Returns:
        The deserialized message dict.

    Raises:
        json.JSONDecodeError: If *data* is not valid JSON.
    """
    return json.loads(data.decode("utf-8"))
