import logging
import sys

from backend.app.core.config import settings


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False

    return logger
