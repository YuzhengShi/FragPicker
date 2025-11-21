#!/usr/bin/env python3
"""
Speedup benchmark: measure parallel performance gains
Tests different thread counts and file sizes
"""

import sys
import os
import time
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

from parallel_analyzer.parallel_processor import EnhancedParallelProcessor


def create_test_corpus(num_files, file_size_kb=100):
    """Create test corpus"""
    test_dir = tempfile.mkdtemp()
    files = []
    
    print(f"Creating test corpus: {num_files} files × {file_size_kb}KB")
    for i in range(num_files):
        filepath = os.path.join(test_dir, f"test_{i:05d}.dat")
        with open(filepath, 'wb') as f:
            f.write(os.urandom(file_size_kb * 1024))
        
        stat = os.stat(filepath)
        files.append((str(stat.st_ino), 1))  # (inode, req_count)
    
    return test_dir, files


def run_benchmark(files, test_dir, num_workers):
    """Run benchmark with specified worker count"""
    processor = EnhancedParallelProcessor(
        num_workers=num_workers,
        mount_point=test_dir,
        enable_monitoring=False,
        enable_profiling=False
    )
    
    start = time.time()
    result = processor.process_files(files, enable_sorting=False)
    elapsed = time.time() - start
    
    return elapsed, result['stats']


def main():
    print("=" * 70)
    print("PARALLEL PROCESSING SPEEDUP BENCHMARK")
    print("=" * 70)
    
    # Test configurations
    file_counts = [100, 500, 1000]
    worker_counts = [1, 2, 4, 8]
    
    for num_files in file_counts:
        print(f"\n{'='*70}")
        print(f"Testing with {num_files} files")
        print(f"{'='*70}")
        
        # Create test corpus
        test_dir, files = create_test_corpus(num_files)
        
        baseline_time = None
        
        try:
            for workers in worker_counts:
                # Run 3 times and take median
                times = []
                for run in range(3):
                    elapsed, stats = run_benchmark(files, test_dir, workers)
                    times.append(elapsed)
                
                times.sort()
                median_time = times[1]  # Median of 3
                
                if workers == 1:
                    baseline_time = median_time
                    speedup = 1.0
                    efficiency = 100.0
                else:
                    speedup = baseline_time / median_time
                    efficiency = (speedup / workers) * 100
                
                print(f"\n{workers} worker{'s' if workers > 1 else ''}:")
                print(f"  Time:       {median_time:.2f}s")
                print(f"  Speedup:    {speedup:.2f}x")
                print(f"  Efficiency: {efficiency:.1f}%")
                print(f"  Throughput: {num_files/median_time:.1f} files/sec")
        
        finally:
            # Cleanup
            shutil.rmtree(test_dir)
    
    print(f"\n{'='*70}")
    print("BENCHMARK COMPLETE")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()