#!/usr/bin/env python3
"""
Performance analysis and profiling tools
Comprehensive performance metrics collection and analysis
"""

import time
import threading
import functools
from typing import Dict, List, Optional, Callable, Any
from collections import defaultdict
from dataclasses import dataclass, field
from contextlib import contextmanager

from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class TimingEntry:
    """Single timing measurement"""
    name: str
    start: float
    end: float
    thread_id: int
    metadata: Dict = field(default_factory=dict)
    
    @property
    def duration(self) -> float:
        return self.end - self.start


class PerformanceAnalyzer:
    """
    Comprehensive performance analyzer
    
    Tracks:
    - Function call timings
    - Thread-level performance
    - Bottleneck identification
    - Statistical analysis
    
    Usage:
        analyzer = PerformanceAnalyzer()
        
        with analyzer.time_block('file_processing'):
            process_files()
        
        stats = analyzer.get_statistics()
    """
    
    def __init__(self):
        self.timings: List[TimingEntry] = []
        self._lock = threading.Lock()
        self._thread_local = threading.local()
    
    @contextmanager
    def time_block(self, name: str, **metadata):
        """
        Context manager for timing code blocks
        
        Usage:
            with analyzer.time_block('inode_mapping', file_count=1000):
                build_inode_map()
        """
        start = time.time()
        thread_id = threading.get_ident()
        
        try:
            yield
        finally:
            end = time.time()
            
            entry = TimingEntry(
                name=name,
                start=start,
                end=end,
                thread_id=thread_id,
                metadata=metadata
            )
            
            with self._lock:
                self.timings.append(entry)
    
    def time_function(self, func: Callable) -> Callable:
        """
        Decorator for timing function calls
        
        Usage:
            @analyzer.time_function
            def my_function():
                ...
        """
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with self.time_block(func.__name__):
                return func(*args, **kwargs)
        return wrapper
    
    def get_statistics(self) -> Dict:
        """
        Get comprehensive performance statistics
        
        Returns:
            {
                'by_name': {...},       # Stats grouped by operation name
                'by_thread': {...},     # Stats grouped by thread
                'total': {...},         # Overall statistics
                'bottlenecks': [...],   # Identified bottlenecks
                'timeline': [...]       # Chronological timeline
            }
        """
        with self._lock:
            if not self.timings:
                return {}
            
            # Group by name
            by_name = self._group_by_name()
            
            # Group by thread
            by_thread = self._group_by_thread()
            
            # Calculate totals
            total = self._calculate_totals()
            
            # Identify bottlenecks
            bottlenecks = self._identify_bottlenecks(by_name)
            
            # Build timeline
            timeline = self._build_timeline()
            
            return {
                'by_name': by_name,
                'by_thread': by_thread,
                'total': total,
                'bottlenecks': bottlenecks,
                'timeline': timeline
            }
    
    def _group_by_name(self) -> Dict:
        """Group timings by operation name"""
        grouped = defaultdict(list)
        
        for entry in self.timings:
            grouped[entry.name].append(entry.duration)
        
        stats = {}
        for name, durations in grouped.items():
            stats[name] = {
                'count': len(durations),
                'total': sum(durations),
                'avg': sum(durations) / len(durations),
                'min': min(durations),
                'max': max(durations),
                'median': sorted(durations)[len(durations) // 2]
            }
        
        return stats
    
    def _group_by_thread(self) -> Dict:
        """Group timings by thread"""
        grouped = defaultdict(list)
        
        for entry in self.timings:
            grouped[entry.thread_id].append(entry)
        
        stats = {}
        for thread_id, entries in grouped.items():
            durations = [e.duration for e in entries]
            stats[thread_id] = {
                'count': len(entries),
                'total': sum(durations),
                'avg': sum(durations) / len(durations)
            }
        
        return stats
    
    def _calculate_totals(self) -> Dict:
        """Calculate overall statistics"""
        durations = [e.duration for e in self.timings]
        
        return {
            'total_operations': len(self.timings),
            'total_time': sum(durations),
            'avg_time': sum(durations) / len(durations),
            'wall_time': self.timings[-1].end - self.timings[0].start,
            'unique_threads': len(set(e.thread_id for e in self.timings))
        }
    
    def _identify_bottlenecks(self, by_name: Dict) -> List[Dict]:
        """Identify performance bottlenecks"""
        bottlenecks = []
        
        # Sort by total time
        sorted_ops = sorted(by_name.items(), 
                           key=lambda x: x[1]['total'], 
                           reverse=True)
        
        # Top 5 time consumers
        for name, stats in sorted_ops[:5]:
            bottlenecks.append({
                'operation': name,
                'total_time': stats['total'],
                'percentage': (stats['total'] / sum(s['total'] for _, s in sorted_ops)) * 100,
                'call_count': stats['count']
            })
        
        return bottlenecks
    
    def _build_timeline(self) -> List[Dict]:
        """Build chronological timeline"""
        # Sort by start time
        sorted_timings = sorted(self.timings, key=lambda e: e.start)
        
        timeline = []
        for entry in sorted_timings:
            timeline.append({
                'name': entry.name,
                'start': entry.start - sorted_timings[0].start,  # Relative time
                'duration': entry.duration,
                'thread_id': entry.thread_id
            })
        
        return timeline
    
    def print_report(self):
        """Print formatted performance report"""
        stats = self.get_statistics()
        
        if not stats:
            print("No performance data collected")
            return
        
        print("\n" + "=" * 70)
        print("PERFORMANCE ANALYSIS REPORT")
        print("=" * 70)
        
        # Overall stats
        print("\nOverall Statistics:")
        total = stats['total']
        print(f"  Total operations:     {total['total_operations']:,}")
        print(f"  Total time:           {total['total_time']:.2f}s")
        print(f"  Wall clock time:      {total['wall_time']:.2f}s")
        print(f"  Average per op:       {total['avg_time']*1000:.2f}ms")
        print(f"  Threads used:         {total['unique_threads']}")
        
        # Bottlenecks
        print("\nTop 5 Time Consumers:")
        for i, bottleneck in enumerate(stats['bottlenecks'], 1):
            print(f"  {i}. {bottleneck['operation']:30s} "
                  f"{bottleneck['total_time']:8.2f}s "
                  f"({bottleneck['percentage']:5.1f}%) "
                  f"× {bottleneck['call_count']}")
        
        # Per-operation breakdown
        print("\nOperation Breakdown:")
        for name, op_stats in sorted(stats['by_name'].items(), 
                                     key=lambda x: x[1]['total'], 
                                     reverse=True):
            print(f"\n  {name}:")
            print(f"    Calls:    {op_stats['count']:,}")
            print(f"    Total:    {op_stats['total']:.3f}s")
            print(f"    Average:  {op_stats['avg']*1000:.2f}ms")
            print(f"    Min:      {op_stats['min']*1000:.2f}ms")
            print(f"    Max:      {op_stats['max']*1000:.2f}ms")
        
        # Thread utilization
        print("\nThread Utilization:")
        for thread_id, thread_stats in stats['by_thread'].items():
            print(f"  Thread {thread_id:016x}: "
                  f"{thread_stats['count']:4d} ops, "
                  f"{thread_stats['total']:6.2f}s total, "
                  f"{thread_stats['avg']*1000:6.2f}ms avg")
        
        print("=" * 70 + "\n")
    
    def export_chrome_trace(self, filename: str):
        """
        Export timeline in Chrome Trace format
        Can be viewed in chrome://tracing
        """
        import json
        
        events = []
        
        for entry in self.timings:
            events.append({
                'name': entry.name,
                'cat': 'function',
                'ph': 'X',  # Complete event
                'ts': entry.start * 1_000_000,  # Convert to microseconds
                'dur': entry.duration * 1_000_000,
                'pid': 1,
                'tid': entry.thread_id,
                'args': entry.metadata
            })
        
        with open(filename, 'w') as f:
            json.dump({'traceEvents': events}, f)
        
        logger.info(f"Chrome trace exported to {filename}")
        logger.info("View at chrome://tracing")


# Global analyzer instance
_global_analyzer: Optional[PerformanceAnalyzer] = None


def get_analyzer() -> PerformanceAnalyzer:
    """Get global performance analyzer"""
    global _global_analyzer
    if _global_analyzer is None:
        _global_analyzer = PerformanceAnalyzer()
    return _global_analyzer


# Convenience decorator
def profile(func: Callable) -> Callable:
    """
    Decorator to profile function calls
    
    Usage:
        @profile
        def my_function():
            ...
    """
    analyzer = get_analyzer()
    return analyzer.time_function(func)


if __name__ == '__main__':
    # Demo performance analysis
    print("Performance Analyzer Demo")
    print("=" * 70)
    
    analyzer = PerformanceAnalyzer()
    
    # Simulate some operations
    with analyzer.time_block('operation_1'):
        time.sleep(0.1)
    
    with analyzer.time_block('operation_2'):
        time.sleep(0.05)
    
    for i in range(10):
        with analyzer.time_block('fast_op'):
            time.sleep(0.01)
    
    # Print report
    analyzer.print_report()
    
    # Export Chrome trace
    analyzer.export_chrome_trace('/tmp/trace.json')
    print("\nChrome trace exported to /tmp/trace.json")