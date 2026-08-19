from __future__ import annotations

import base64
import binascii
import hmac
from collections.abc import Mapping


def validate_basic_authorization(
    headers: Mapping[str, str],
    expected_username: str,
    expected_password: str,
) -> bool:
    authorization = headers.get("authorization", "")
    scheme, _, encoded = authorization.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return False

    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False

    username, separator, password = decoded.partition(":")
    if not separator:
        return False
    return hmac.compare_digest(username, expected_username) and hmac.compare_digest(
        password, expected_password
    )

