#!/usr/bin/env python3
"""
Real-time progress monitoring and reporting
Provides live updates during long-running operations
"""

import threading
import time
import sys
from typing import Optional, Dict, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class ProgressState:
    """Current progress state"""
    total: int = 0
    completed: int = 0
    failed: int = 0
    start_time: float = field(default_factory=time.time)
    
    @property
    def elapsed(self) -> float:
        """Elapsed time in seconds"""
        return time.time() - self.start_time
    
    @property
    def rate(self) -> float:
        """Items per second"""
        if self.elapsed > 0:
            return self.completed / self.elapsed
        return 0
    
    @property
    def eta(self) -> Optional[float]:
        """Estimated time to completion in seconds"""
        remaining = self.total - self.completed
        if remaining > 0 and self.rate > 0:
            return remaining / self.rate
        return None
    
    @property
    def percentage(self) -> float:
        """Completion percentage"""
        if self.total > 0:
            return (self.completed / self.total) * 100
        return 0


class ProgressBar:
    """
    Terminal progress bar with ETA and rate display
    
    Example output:
    [████████████████░░░░░░░░] 65% | 6500/10000 | 1250 files/sec | ETA: 00:02:48
    """
    
    def __init__(self, total: int, description: str = "", 
                 width: int = 40, update_interval: float = 0.1):
        self.state = ProgressState(total=total)
        self.description = description
        self.width = width
        self.update_interval = update_interval
        
        self._last_update = 0
        self._lock = threading.Lock()
    
    def update(self, completed: Optional[int] = None, 
              increment: int = 0, failed: int = 0):
        """
        Update progress
        
        Args:
            completed: Set absolute completed count
            increment: Increment completed count by this amount
            failed: Increment failed count
        """
        with self._lock:
            if completed is not None:
                self.state.completed = completed
            else:
                self.state.completed += increment
            
            if failed > 0:
                self.state.failed += failed
            
            # Rate limit updates
            now = time.time()
            if now - self._last_update >= self.update_interval:
                self._render()
                self._last_update = now
    
    def _render(self):
        """Render progress bar to terminal"""
        # Calculate bar fill
        filled = int(self.width * (self.state.completed / self.state.total))
        empty = self.width - filled
        
        # Build bar string
        bar = "█" * filled + "░" * empty
        
        # Format percentage
        pct = self.state.percentage
        
        # Format counts
        counts = f"{self.state.completed:,}/{self.state.total:,}"
        
        # Format rate
        rate = f"{self.state.rate:.0f} files/sec" if self.state.rate > 0 else "-- files/sec"
        
        # Format ETA
        if self.state.eta is not None:
            eta_td = timedelta(seconds=int(self.state.eta))
            eta_str = str(eta_td)
        else:
            eta_str = "--:--:--"
        
        # Build complete line
        line = f"\r{self.description}[{bar}] {pct:5.1f}% | {counts} | {rate} | ETA: {eta_str}"
        
        # Write to terminal
        sys.stdout.write(line)
        sys.stdout.flush()
    
    def finish(self):
        """Mark as complete and print final statistics"""
        with self._lock:
            self.state.completed = self.state.total
            self._render()
            print()  # New line
            
            # Print summary
            print(f"Completed: {self.state.completed:,} files")
            print(f"Failed: {self.state.failed:,} files")
            print(f"Time: {self.state.elapsed:.2f}s")
            print(f"Average rate: {self.state.rate:.1f} files/sec")


class ProgressMonitor:
    """
    Advanced progress monitoring with callbacks
    
    Supports multiple progress trackers and custom callbacks for monitoring
    different stages of processing.
    """
    
    def __init__(self, enable_ui: bool = True):
        self.enable_ui = enable_ui
        self.stages = {}
        self.current_stage = None
        self._lock = threading.Lock()
    
    def create_stage(self, name: str, total: int, description: str = "") -> ProgressBar:
        """
        Create a new progress stage
        
        Args:
            name: Unique stage identifier
            total: Total items in this stage
            description: Display description
        
        Returns:
            ProgressBar instance for this stage
        """
        with self._lock:
            if name in self.stages:
                logger.warning(f"Stage {name} already exists, replacing")
            
            bar = ProgressBar(total, description or name)
            self.stages[name] = bar
            self.current_stage = name
            
            return bar
    
    def update(self, stage: Optional[str] = None, **kwargs):
        """Update specified stage (or current stage)"""
        with self._lock:
            stage_name = stage or self.current_stage
            
            if stage_name and stage_name in self.stages:
                self.stages[stage_name].update(**kwargs)
    
    def finish(self, stage: Optional[str] = None):
        """Finish specified stage"""
        with self._lock:
            stage_name = stage or self.current_stage
            
            if stage_name and stage_name in self.stages:
                self.stages[stage_name].finish()


class BackgroundMonitor(threading.Thread):
    """
    Background thread for monitoring system resources
    
    Tracks CPU, memory, and I/O during processing
    """
    
    def __init__(self, interval: float = 1.0, 
                 callback: Optional[Callable] = None):
        super().__init__(name="BackgroundMonitor", daemon=True)
        self.interval = interval
        self.callback = callback
        self._stop_event = threading.Event()
        
        self.samples = []
        
        # Try to import psutil
        try:
            import psutil
            self.psutil = psutil
            self.process = psutil.Process()
        except ImportError:
            logger.warning("psutil not available, resource monitoring disabled")
            self.psutil = None
    
    def run(self):
        """Background monitoring loop"""
        if not self.psutil:
            return
        
        while not self._stop_event.is_set():
            try:
                sample = self._collect_sample()
                self.samples.append(sample)
                
                if self.callback:
                    self.callback(sample)
                
            except Exception as e:
                logger.error(f"Monitor error: {e}")
            
            time.sleep(self.interval)
    
    def _collect_sample(self) -> Dict:
        """Collect resource usage sample"""
        sample = {
            'timestamp': time.time(),
            'cpu_percent': self.process.cpu_percent(interval=0.1),
            'memory_mb': self.process.memory_info().rss / (1024 * 1024),
            'threads': self.process.num_threads(),
        }
        
        # I/O counters (not always available)
        try:
            io = self.process.io_counters()
            sample['io_read_mb'] = io.read_bytes / (1024 * 1024)
            sample['io_write_mb'] = io.write_bytes / (1024 * 1024)
        except:
            pass
        
        return sample
    
    def stop(self) -> Dict:
        """Stop monitoring and return statistics"""
        self._stop_event.set()
        self.join(timeout=5)
        
        if not self.samples:
            return {}
        
        # Calculate statistics
        cpu_values = [s['cpu_percent'] for s in self.samples]
        mem_values = [s['memory_mb'] for s in self.samples]
        
        stats = {
            'duration': self.samples[-1]['timestamp'] - self.samples[0]['timestamp'],
            'samples': len(self.samples),
            'cpu': {
                'avg': sum(cpu_values) / len(cpu_values),
                'max': max(cpu_values),
                'min': min(cpu_values)
            },
            'memory_mb': {
                'avg': sum(mem_values) / len(mem_values),
                'max': max(mem_values),
                'min': min(mem_values)
            }
        }
        
        return stats


if __name__ == '__main__':
    # Demo progress monitoring
    print("Progress Monitor Demo")
    print("=" * 60)
    
    # Create monitor
    monitor = ProgressMonitor()
    
    # Stage 1: File discovery
    bar1 = monitor.create_stage('discovery', 1000, 'Discovering files: ')
    for i in range(1000):
        time.sleep(0.001)
        bar1.update(increment=1)
    bar1.finish()
    
    print()
    
    # Stage 2: Analysis
    bar2 = monitor.create_stage('analysis', 5000, 'Analyzing files: ')
    for i in range(5000):
        time.sleep(0.0005)
        bar2.update(increment=1)
        if i % 100 == 0 and i > 0:
            bar2.update(failed=1)
    bar2.finish()
    
    print("\nDemo complete!")