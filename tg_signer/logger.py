import logging
import os
import pathlib
from logging.handlers import RotatingFileHandler


class ExactLevelFilter(logging.Filter):
    def __init__(self, level: int):
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno == self.level


format_str = (
    "[%(levelname)s] [%(name)s] %(asctime)s %(filename)s %(lineno)s %(message)s"
)
formatter = logging.Formatter(format_str)


def _add_file_handler(
    logger: logging.Logger,
    path: pathlib.Path,
    max_bytes: int,
    level: int | None = None,
) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=10, encoding="utf-8"
    )
    if level is not None:
        handler.setLevel(level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return handler


def configure_logger(
    name: str = "tg-signer",
    log_level: str = "INFO",
    log_dir: str | pathlib.Path = "logs",
    log_file: str | pathlib.Path = None,
    max_bytes: int = 1024 * 1024 * 3,
):
    level = log_level.strip().upper()
    level_no: int = logging.getLevelName(level)
    logger = logging.getLogger(name)
    logger.setLevel(level_no)
    logger.handlers.clear()
    logger.propagate = False

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    log_dir = pathlib.Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_file or log_dir / f"{name}.log"
    _add_file_handler(logger, log_file, max_bytes)

    if logging.WARNING >= level_no:
        warn_file_handler = _add_file_handler(
            logger, log_dir / "warn.log", max_bytes, logging.WARNING
        )
        warn_file_handler.addFilter(ExactLevelFilter(logging.WARNING))

    if logging.ERROR >= level_no:
        _add_file_handler(logger, log_dir / "error.log", max_bytes, logging.ERROR)
    if os.environ.get("PYROGRAM_LOG_ON", "0") == "1":
        pyrogram_logger = logging.getLogger("pyrogram")
        pyrogram_logger.setLevel(level)
        pyrogram_logger.addHandler(console_handler)
    return logger
