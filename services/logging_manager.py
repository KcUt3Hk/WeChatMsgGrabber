"""
Logging manager to configure Python logging according to AppConfig.Logging.
"""
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional
import os

from models.config import LoggingConfig, AppConfig


class LoggingManager:
    def __init__(self):
        self._configured = False

    def setup(self, cfg: AppConfig) -> None:
        """Configure logging based on AppConfig.logging settings."""
        if self._configured:
            return

        log_cfg: LoggingConfig = cfg.logging
        level = getattr(logging, log_cfg.level.upper(), logging.INFO)

        root_logger = logging.getLogger()
        root_logger.setLevel(level)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(level)
        ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

        # Ensure log directory exists
        log_dir = os.path.dirname(log_cfg.file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # File handler with rotation
        fh = RotatingFileHandler(log_cfg.file, maxBytes=self._parse_size(log_cfg.max_size), backupCount=3, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

        root_logger.handlers.clear()
        root_logger.addHandler(ch)
        root_logger.addHandler(fh)
        self._configured = True

    @staticmethod
    def _parse_size(size_str: str) -> int:
        """Parse human-readable size (e.g., '10MB') into bytes."""
        s = size_str.strip().upper()
        try:
            if s.endswith("KB"):
                return int(float(s[:-2]) * 1024)
            if s.endswith("MB"):
                return int(float(s[:-2]) * 1024 * 1024)
            if s.endswith("GB"):
                return int(float(s[:-2]) * 1024 * 1024 * 1024)
            return int(s)
        except Exception:
            return 10 * 1024 * 1024  # default 10MB