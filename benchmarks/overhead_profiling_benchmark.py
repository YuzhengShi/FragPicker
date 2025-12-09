#!/usr/bin/env python3
"""
Overhead Profiling Benchmark
Detailed component-level timing breakdown for parallel analysis pipeline.
"""

import sys
import os
import time
import json
import tempfile
import shutil

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

from parallel_analyzer.performance_analyzer import PerformanceAnalyzer
from parallel_analyzer.parallel_processor import EnhancedParallelProcessor
from parallel_analyzer.multiprocess_processor import MultiprocessProcessor
from parallel_analyzer.inode_mapper import build_inode_map
from parallel_analyzer.parallel_sorter import ParallelSorter


def create_test_files(num_files=1000, file_size_kb=10):
    """Create test files for benchmarking"""
    test_dir = tempfile.mkdtemp(prefix='fragpicker_overhead_')
    print(f"Creating {num_files} test files in {test_dir}...")
    
    file_list = []
    for i in range(num_files):
        filepath = os.path.join(test_dir, f"test_{i:06d}.dat")
        with open(filepath, 'wb') as f:
            f.write(os.urandom(file_size_kb * 1024))
        
        stat = os.stat(filepath)
        file_list.append((str(stat.st_ino), 1))  # (inode, access_count)
    
    return test_dir, file_list


def profile_sequential(test_dir, file_list):
    """Profile sequential processing with detailed component timing"""
    print("\n" + "="*70)
    print("PROFILING SEQUENTIAL PROCESSING")
    print("="*70)
    
    analyzer = PerformanceAnalyzer()
    results = {}
    
    # Start timing
    total_start = time.time()
    
    # 1. Inode mapping
    with analyzer.time_block('inode_mapping'):
        inode_map = build_inode_map(test_dir)
    
    # 2. File processing (sequential - 1 worker)
    with analyzer.time_block('file_processing'):
        processor = EnhancedParallelProcessor(
            num_workers=1,
            mount_point=test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        process_result = processor.process_files(file_list, enable_sorting=False)
    
    # 3. Sorting
    with analyzer.time_block('sorting'):
        sorter = ParallelSorter(num_workers=1)
        sorted_results = sorter.sort_results(process_result['results'])
    
    total_time = time.time() - total_start
    
    # Extract timing statistics
    stats = analyzer.get_statistics()
    
    results['total_time'] = total_time
    results['components'] = {}
    
    for name, timing_stats in stats['by_name'].items():
        results['components'][name] = {
            'time': timing_stats['total'],
            'calls': timing_stats['count'],
            'avg': timing_stats['avg'],
            'percentage': (timing_stats['total'] / total_time) * 100
        }
    
    # Calculate overhead (everything except file processing)
    processing_time = results['components']['file_processing']['time']
    overhead_time = total_time - processing_time
    results['overhead_time'] = overhead_time
    results['overhead_percentage'] = (overhead_time / total_time) * 100
    
    # Print report
    print(f"\nTotal time: {total_time:.3f}s")
    print("\nComponent Breakdown:")
    for name, comp in results['components'].items():
        print(f"  {name:20s}: {comp['time']:.3f}s ({comp['percentage']:5.1f}%)")
    print(f"  {'Total Overhead':20s}: {overhead_time:.3f}s ({results['overhead_percentage']:5.1f}%)")
    
    return results


def profile_parallel_threading(test_dir, file_list, num_workers=8):
    """Profile parallel threading with detailed component timing"""
    print("\n" + "="*70)
    print(f"PROFILING PARALLEL THREADING ({num_workers} workers)")
    print("="*70)
    
    analyzer = PerformanceAnalyzer()
    results = {}
    
    # Start timing
    total_start = time.time()
    
    # 1. Inode mapping (same as sequential - only done once)
    with analyzer.time_block('inode_mapping'):
        inode_map = build_inode_map(test_dir)
    
    # 2. File processing (parallel threading)
    with analyzer.time_block('file_processing'):
        processor = EnhancedParallelProcessor(
            num_workers=num_workers,
            mount_point=test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        process_result = processor.process_files(file_list, enable_sorting=False)
    
    # 3. Sorting (parallel)
    with analyzer.time_block('sorting'):
        sorter = ParallelSorter(num_workers=num_workers)
        sorted_results = sorter.sort_results(process_result['results'])
    
    total_time = time.time() - total_start
    
    # Extract timing statistics
    stats = analyzer.get_statistics()
    
    results['total_time'] = total_time
    results['num_workers'] = num_workers
    results['components'] = {}
    
    for name, timing_stats in stats['by_name'].items():
        results['components'][name] = {
            'time': timing_stats['total'],
            'calls': timing_stats['count'],
            'avg': timing_stats['avg'],
            'percentage': (timing_stats['total'] / total_time) * 100
        }
    
    # Calculate overhead
    processing_time = results['components']['file_processing']['time']
    overhead_time = total_time - processing_time
    results['overhead_time'] = overhead_time
    results['overhead_percentage'] = (overhead_time / total_time) * 100
    
    # Calculate speedup vs sequential baseline
    results['speedup'] = None  # Will be filled in by main function
    
    # Print report
    print(f"\nTotal time: {total_time:.3f}s")
    print("\nComponent Breakdown:")
    for name, comp in results['components'].items():
        print(f"  {name:20s}: {comp['time']:.3f}s ({comp['percentage']:5.1f}%)")
    print(f"  {'Total Overhead':20s}: {overhead_time:.3f}s ({results['overhead_percentage']:5.1f}%)")
    
    return results


def profile_parallel_multiprocess(test_dir, file_list, num_workers=8):
    """Profile parallel multiprocess with detailed component timing"""
    print("\n" + "="*70)
    print(f"PROFILING PARALLEL MULTIPROCESSING ({num_workers} workers)")
    print("="*70)
    
    analyzer = PerformanceAnalyzer()
    results = {}
    
    # Start timing
    total_start = time.time()
    
    # 1. Inode mapping
    with analyzer.time_block('inode_mapping'):
        inode_map = build_inode_map(test_dir)
    
    # 2. File processing (multiprocess)
    with analyzer.time_block('file_processing'):
        processor = MultiprocessProcessor(
            num_workers=num_workers,
            mount_point=test_dir,
            enable_monitoring=False
        )
        process_result = processor.process_files(file_list, enable_sorting=False)
    
    # 3. Sorting (parallel)
    with analyzer.time_block('sorting'):
        sorter = ParallelSorter(num_workers=num_workers)
        sorted_results = sorter.sort_results(process_result['results'])
    
    total_time = time.time() - total_start
    
    # Extract timing statistics
    stats = analyzer.get_statistics()
    
    results['total_time'] = total_time
    results['num_workers'] = num_workers
    results['components'] = {}
    
    for name, timing_stats in stats['by_name'].items():
        results['components'][name] = {
            'time': timing_stats['total'],
            'calls': timing_stats['count'],
            'avg': timing_stats['avg'],
            'percentage': (timing_stats['total'] / total_time) * 100
        }
    
    # Calculate overhead
    processing_time = results['components']['file_processing']['time']
    overhead_time = total_time - processing_time
    results['overhead_time'] = overhead_time
    results['overhead_percentage'] = (overhead_time / total_time) * 100
    
    # Print report
    print(f"\nTotal time: {total_time:.3f}s")
    print("\nComponent Breakdown:")
    for name, comp in results['components'].items():
        print(f"  {name:20s}: {comp['time']:.3f}s ({comp['percentage']:5.1f}%)")
    print(f"  {'Total Overhead':20s}: {overhead_time:.3f}s ({results['overhead_percentage']:5.1f}%)")
    
    return results


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Overhead profiling benchmark')
    parser.add_argument('--files', type=int, default=1000,
                       help='Number of test files (default: 1000)')
    parser.add_argument('--workers', type=int, default=8,
                       help='Number of workers for parallel tests (default: 8)')
    parser.add_argument('--file-size', type=int, default=10,
                       help='File size in KB (default: 10)')
    
    args = parser.parse_args()
    
    print("="*70)
    print("OVERHEAD PROFILING BENCHMARK")
    print("="*70)
    print(f"Configuration:")
    print(f"  Files: {args.files}")
    print(f"  Workers (parallel): {args.workers}")
    print(f"  File size: {args.file_size} KB")
    
    # Create test files
    test_dir, file_list = create_test_files(args.files, args.file_size)
    
    try:
        # Profile all three methods
        sequential_results = profile_sequential(test_dir, file_list)
        threading_results = profile_parallel_threading(test_dir, file_list, args.workers)
        multiprocess_results = profile_parallel_multiprocess(test_dir, file_list, args.workers)
        
        # Calculate speedups
        baseline_time = sequential_results['total_time']
        threading_results['speedup'] = baseline_time / threading_results['total_time']
        multiprocess_results['speedup'] = baseline_time / multiprocess_results['total_time']
        
        # Compile final results
        final_results = {
            'configuration': {
                'num_files': args.files,
                'num_workers': args.workers,
                'file_size_kb': args.file_size
            },
            'sequential': sequential_results,
            'threading': threading_results,
            'multiprocess': multiprocess_results
        }
        
        # Save to JSON
        output_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'overhead_profiling_results.json'
        )
        
        with open(output_file, 'w') as f:
            json.dump(final_results, f, indent=2)
        
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"Sequential:     {sequential_results['total_time']:.3f}s (baseline)")
        print(f"Threading:      {threading_results['total_time']:.3f}s ({threading_results['speedup']:.2f}x speedup)")
        print(f"Multiprocess:   {multiprocess_results['total_time']:.3f}s ({multiprocess_results['speedup']:.2f}x speedup)")
        print(f"\nResults saved to: {output_file}")
        
    finally:
        # Cleanup
        print(f"\nCleaning up test directory: {test_dir}")
        shutil.rmtree(test_dir)


if __name__ == '__main__':
    main()
