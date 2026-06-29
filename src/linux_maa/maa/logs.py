from __future__ import annotations


def translate_maa_cli_log(text: str) -> str:
    """Translate maa-cli log text into user-facing UI text.

    The first UI slice intentionally preserves the original info-level maa-cli
    log text. Future rules can be added here without changing the runner or UI.
    """

    return text
