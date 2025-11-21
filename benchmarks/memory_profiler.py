#!/usr/bin/env python3
"""
Memory profiling and analysis
Tracks memory usage patterns and identifies memory leaks
"""

import sys
import os
import time
import gc
from typing import Dict, List, Optional
from dataclasses import dataclass
import tracemalloc

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("Warning: psutil not available. Install with: pip install psutil")

from parallel_analyzer.parallel_processor import EnhancedParallelProcessor


@dataclass
class MemorySnapshot:
    """Memory usage snapshot"""
    timestamp: float
    rss_mb: float  # Resident Set Size
    vms_mb: float  # Virtual Memory Size
    percent: float
    available_mb: float


class MemoryProfiler:
    """
    Memory profiler for analyzing memory usage patterns
    
    Features:
    - Track memory over time
    - Detect memory leaks
    - Peak memory usage
    - Per-operation memory deltas
    """
    
    def __init__(self, sample_interval: float = 0.5):
        self.sample_interval = sample_interval
        self.snapshots: List[MemorySnapshot] = []
        self.baseline: Optional[MemorySnapshot] = None
        
        if not PSUTIL_AVAILABLE:
            raise RuntimeError("psutil required for memory profiling")
        
        self.process = psutil.Process()
    
    def start(self):
        """Start memory profiling"""
        # Take baseline measurement
        self.baseline = self._take_snapshot()
        
        # Start tracemalloc for detailed Python memory tracking
        tracemalloc.start()
        
        print(f"Memory profiling started. Baseline: {self.baseline.rss_mb:.1f} MB RSS")
    
    def take_snapshot(self) -> MemorySnapshot:
        """Take memory snapshot"""
        snapshot = self._take_snapshot()
        self.snapshots.append(snapshot)
        return snapshot
    
    def _take_snapshot(self) -> MemorySnapshot:
        """Internal: take memory snapshot"""
        mem_info = self.process.memory_info()
        virtual_mem = psutil.virtual_memory()
        
        return MemorySnapshot(
            timestamp=time.time(),
            rss_mb=mem_info.rss / (1024 * 1024),
            vms_mb=mem_info.vms / (1024 * 1024),
            percent=self.process.memory_percent(),
            available_mb=virtual_mem.available / (1024 * 1024)
        )
    
    def stop(self) -> Dict:
        """Stop profiling and return statistics"""
        final_snapshot = self._take_snapshot()
        
        # Get tracemalloc statistics
        trace_stats = tracemalloc.take_snapshot()
        tracemalloc.stop()
        
        # Calculate statistics
        stats = self._calculate_statistics(final_snapshot, trace_stats)
        
        return stats
    
    def _calculate_statistics(self, final_snapshot: MemorySnapshot, 
                             trace_stats) -> Dict:
        """Calculate memory statistics"""
        if not self.snapshots or not self.baseline:
            return {}
        
        # RSS statistics
        rss_values = [s.rss_mb for s in self.snapshots]
        
        stats = {
            'baseline_mb': self.baseline.rss_mb,
            'final_mb': final_snapshot.rss_mb,
            'peak_mb': max(rss_values),
            'min_mb': min(rss_values),
            'avg_mb': sum(rss_values) / len(rss_values),
            'increase_mb': final_snapshot.rss_mb - self.baseline.rss_mb,
            'samples': len(self.snapshots)
        }
        
        # Top memory consumers from tracemalloc
        top_stats = trace_stats.statistics('lineno')[:10]
        
        stats['top_allocations'] = []
        for stat in top_stats:
            stats['top_allocations'].append({
                'file': stat.traceback.format()[0],
                'size_mb': stat.size / (1024 * 1024),
                'count': stat.count
            })
        
        return stats
    
    def print_report(self):
        """Print memory profiling report"""
        final = self._take_snapshot()
        stats = self._calculate_statistics(final, tracemalloc.take_snapshot())
        
        print("\n" + "=" * 70)
        print("MEMORY PROFILING REPORT")
        print("=" * 70)
        
        print(f"\nMemory Usage:")
        print(f"  Baseline:     {stats['baseline_mb']:8.1f} MB")
        print(f"  Final:        {stats['final_mb']:8.1f} MB")
        print(f"  Peak:         {stats['peak_mb']:8.1f} MB")
        print(f"  Average:      {stats['avg_mb']:8.1f} MB")
        print(f"  Increase:     {stats['increase_mb']:+8.1f} MB")
        
        print(f"\nTop Memory Allocations:")
        for i, alloc in enumerate(stats['top_allocations'][:5], 1):
            print(f"  {i}. {alloc['size_mb']:.2f} MB - {alloc['file']}")
        
        # Memory leak detection
        if stats['increase_mb'] > 100:
            print(f"\n⚠️  WARNING: Significant memory increase detected!")
            print(f"   Possible memory leak: +{stats['increase_mb']:.1f} MB")
        
        print("=" * 70)


def profile_processing(file_count: int = 1000, num_workers: int = 8):
    """
    Profile memory usage during file processing
    
    Args:
        file_count: Number of files to process
        num_workers: Number of worker threads
    """
    print(f"Memory Profiling: {file_count} files, {num_workers} workers")
    print("=" * 70)
    
    # Create test files
    import tempfile
    test_dir = tempfile.mkdtemp()
    files = []
    
    print("Creating test files...")
    for i in range(file_count):
        filepath = os.path.join(test_dir, f"test_{i:06d}.dat")
        with open(filepath, 'wb') as f:
            f.write(os.urandom(10 * 1024))  # 10KB each
        
        stat = os.stat(filepath)
        files.append((str(stat.st_ino), 1))
    
    # Start profiling
    profiler = MemoryProfiler()
    profiler.start()
    
    # Initial snapshot
    profiler.take_snapshot()
    
    # Create processor
    print("\nCreating processor...")
    processor = EnhancedParallelProcessor(
        num_workers=num_workers,
        mount_point=test_dir,
        enable_monitoring=False,
        enable_profiling=False
    )
    
    profiler.take_snapshot()
    
    # Process files
    print("Processing files...")
    
    # Take snapshots during processing
    import threading
    stop_sampling = threading.Event()
    
    def sample_memory():
        while not stop_sampling.is_set():
            profiler.take_snapshot()
            time.sleep(profiler.sample_interval)
    
    sampler = threading.Thread(target=sample_memory, daemon=True)
    sampler.start()
    
    result = processor.process_files(files, enable_sorting=False)
    
    stop_sampling.set()
    sampler.join()
    
    # Final snapshot
    profiler.take_snapshot()
    
    # Force garbage collection
    print("\nForcing garbage collection...")
    gc.collect()
    time.sleep(1)
    
    profiler.take_snapshot()
    
    # Print report
    profiler.print_report()
    
    # Cleanup
    import shutil
    shutil.rmtree(test_dir)
    
    print(f"\nProcessing Results:")
    print(f"  Files processed: {result['stats']['successful']}")
    print(f"  Time: {result['stats']['total_time']:.2f}s")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Memory profiler')
    parser.add_argument('--files', type=int, default=1000,
                       help='Number of files to process')
    parser.add_argument('--workers', type=int, default=8,
                       help='Number of worker threads')
    
    args = parser.parse_args()
    
    if not PSUTIL_AVAILABLE:
        print("ERROR: psutil required. Install with: pip install psutil")
        sys.exit(1)
    
    profile_processing(args.files, args.workers)