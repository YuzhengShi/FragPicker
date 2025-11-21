#!/usr/bin/env python3
"""
Structured logging system with performance tracking
"""

import logging
import sys
import time
from pathlib import Path
from typing import Optional
from logging.handlers import RotatingFileHandler
from .config import get_config


class PerformanceLogger:
    """
    Logger with built-in performance tracking
    Automatically logs timing information
    """
    
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(name)
        self._setup_logger()
        
    def _setup_logger(self):
        """Setup logger with console and file handlers"""
        config = get_config().logging
        
        # Set level
        level = getattr(logging, config.level.upper())
        self.logger.setLevel(level)
        
        # Remove existing handlers
        self.logger.handlers.clear()
        
        # Console handler
        if config.enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            console_format = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                datefmt='%H:%M:%S'
            )
            console_handler.setFormatter(console_format)
            self.logger.addHandler(console_handler)
        
        # File handler
        if config.file_path:
            Path(config.file_path).parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                config.file_path,
                maxBytes=config.max_file_size_mb * 1024 * 1024,
                backupCount=config.backup_count
            )
            file_handler.setLevel(level)
            file_format = logging.Formatter(
                '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s'
            )
            file_handler.setFormatter(file_format)
            self.logger.addHandler(file_handler)
    
    def debug(self, msg: str, **kwargs):
        """Log debug message"""
        self.logger.debug(msg, extra=kwargs)
    
    def info(self, msg: str, **kwargs):
        """Log info message"""
        self.logger.info(msg, extra=kwargs)
    
    def warning(self, msg: str, **kwargs):
        """Log warning message"""
        self.logger.warning(msg, extra=kwargs)
    
    def error(self, msg: str, **kwargs):
        """Log error message"""
        self.logger.error(msg, extra=kwargs)
    
    def time_block(self, description: str):
        """Context manager for timing code blocks"""
        return TimedBlock(self, description)


class TimedBlock:
    """Context manager for timing code blocks"""
    
    def __init__(self, logger: PerformanceLogger, description: str):
        self.logger = logger
        self.description = description
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        self.logger.debug(f"Starting: {self.description}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.time() - self.start_time
        
        if exc_type is None:
            self.logger.info(f"Completed: {self.description} ({elapsed:.2f}s)")
        else:
            self.logger.error(f"Failed: {self.description} ({elapsed:.2f}s) - {exc_val}")
        
        return False  # Don't suppress exceptions


# Convenience function
def get_logger(name: str) -> PerformanceLogger:
    """Get logger instance"""
    return PerformanceLogger(name)