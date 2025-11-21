#!/usr/bin/env python3
"""
Configuration management for parallel analyzer
Supports YAML config files and environment variables
"""

import os
import yaml
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class FiemapConfig:
    """FIEMAP-specific configuration"""
    max_extents_per_call: int = 32
    retry_attempts: int = 3
    retry_delay_ms: int = 100
    timeout_seconds: int = 30


@dataclass
class ParallelConfig:
    """Parallel processing configuration"""
    num_workers: int = 8
    auto_detect_cores: bool = True
    max_workers: int = 64
    queue_size: int = 10000
    worker_timeout: int = 300
    
    # Load balancing
    use_work_stealing: bool = True
    task_chunk_size: int = 1
    
    # Performance tuning
    enable_hyperthreading: bool = False  # Use physical cores only


@dataclass
class InodeMapConfig:
    """Inode mapping configuration"""
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600
    parallel_find: bool = False  # Experimental: parallel directory walk


@dataclass
class PerformanceConfig:
    """Performance monitoring configuration"""
    enable_monitoring: bool = True
    sample_interval_ms: int = 100
    collect_cpu_stats: bool = True
    collect_memory_stats: bool = True
    collect_io_stats: bool = True


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR
    file_path: Optional[str] = None
    max_file_size_mb: int = 100
    backup_count: int = 5
    enable_console: bool = True


@dataclass
class Config:
    """Main configuration"""
    fiemap: FiemapConfig = field(default_factory=FiemapConfig)
    parallel: ParallelConfig = field(default_factory=ParallelConfig)
    inode_map: InodeMapConfig = field(default_factory=InodeMapConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    mount_point: str = "/mnt"
    temp_dir: str = "/tmp/fragpicker"
    
    @classmethod
    def from_yaml(cls, path: str) -> 'Config':
        """Load configuration from YAML file"""
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        return cls(
            fiemap=FiemapConfig(**data.get('fiemap', {})),
            parallel=ParallelConfig(**data.get('parallel', {})),
            inode_map=InodeMapConfig(**data.get('inode_map', {})),
            performance=PerformanceConfig(**data.get('performance', {})),
            logging=LoggingConfig(**data.get('logging', {})),
            mount_point=data.get('mount_point', '/mnt'),
            temp_dir=data.get('temp_dir', '/tmp/fragpicker')
        )
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Load configuration from environment variables"""
        config = cls()
        
        # Override with environment variables
        if 'FRAGPICKER_WORKERS' in os.environ:
            config.parallel.num_workers = int(os.environ['FRAGPICKER_WORKERS'])
        
        if 'FRAGPICKER_MOUNT_POINT' in os.environ:
            config.mount_point = os.environ['FRAGPICKER_MOUNT_POINT']
        
        if 'FRAGPICKER_LOG_LEVEL' in os.environ:
            config.logging.level = os.environ['FRAGPICKER_LOG_LEVEL']
        
        return config
    
    def auto_tune(self):
        """Auto-tune configuration based on system resources"""
        import multiprocessing
        import psutil
        
        # Auto-detect CPU cores
        if self.parallel.auto_detect_cores:
            cpu_count = multiprocessing.cpu_count()
            
            # Use physical cores only if hyperthreading disabled
            if not self.parallel.enable_hyperthreading:
                cpu_count = psutil.cpu_count(logical=False) or cpu_count
            
            # Use 75% of available cores, leaving some for system
            optimal_workers = max(1, int(cpu_count * 0.75))
            self.parallel.num_workers = min(optimal_workers, self.parallel.max_workers)
        
        # Adjust queue size based on available memory
        available_memory_gb = psutil.virtual_memory().available / (1024**3)
        if available_memory_gb < 4:
            self.parallel.queue_size = 1000  # Smaller queue for low memory
        
        return self


# Global config instance
_global_config: Optional[Config] = None


def get_config() -> Config:
    """Get global configuration instance"""
    global _global_config
    if _global_config is None:
        _global_config = Config.from_env()
        _global_config.auto_tune()
    return _global_config


def set_config(config: Config):
    """Set global configuration"""
    global _global_config
    _global_config = config