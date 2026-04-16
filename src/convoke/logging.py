import logging
import sys
from pathlib import Path


def setup_logging(log_file: Path | None = None, level: str = "INFO") -> logging.Logger:
    """Configure the convoke logger.

    Args:
        log_file: Path to log file. If None, only stdout.
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
    """
    logger = logging.getLogger("convoke")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers
    logger.handlers.clear()

    formatter = logging.Formatter("[%(asctime)s] %(levelname)-8s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
