from __future__ import annotations

import logging

_LOGGER_NAME = "lorechat"


def get_logger(name: str | None = None) -> logging.Logger:
    base = logging.getLogger(_LOGGER_NAME)
    if not base.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        base.addHandler(handler)
        base.setLevel(logging.INFO)
    return base.getChild(name) if name else base
