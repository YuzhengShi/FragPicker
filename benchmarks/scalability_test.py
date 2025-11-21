#!/usr/bin/env python3
"""
Scalability testing across different system configurations
Tests how the system scales with:
- Different file counts
- Different worker counts
- Different file sizes
- Different hardware configurations
"""

import sys
import os
import time
import tempfile
import shutil
from typing import Dict, List
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

from parallel_analyzer.parallel_processor import EnhancedParallelProcessor

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


class ScalabilityTester:
    """
    Comprehensive scalability testing
    
    Tests:
    1. Strong scaling: Fixed problem size, varying workers
    2. Weak scaling: Problem size scales with workers
    3. File size impact
    4. Memory scaling
    """
    
    def __init__(self, output_file: str = 'scalability_results.json'):
        self.output_file = output_file
        self.results = []
    
    def create_test_corpus(self, num_files: int, file_size_kb: int = 10) -> tuple:
        """Create test file corpus"""
        test_dir = tempfile.mkdtemp(prefix=f"scale_test_{num_files}_")
        files = []
        
        for i in range(num_files):
            filepath = os.path.join(test_dir, f"file_{i:06d}.dat")
            with open(filepath, 'wb') as f:
                f.write(os.urandom(file_size_kb * 1024))
            
            stat = os.stat(filepath)
            files.append((str(stat.st_ino), 1))
        
        return test_dir, files
    
    def run_test(self, num_files: int, num_workers: int, 
                 file_size_kb: int = 10, runs: int = 3) -> Dict:
        """
        Run single test configuration
        
        Args:
            num_files: Number of files to process
            num_workers: Number of worker threads
            file_size_kb: Size of each file in KB
            runs: Number of runs to average
        
        Returns:
            Test results dictionary
        """
        print(f"\nTesting: {num_files} files, {num_workers} workers, "
              f"{file_size_kb}KB files")
        print("-" * 60)
        
        # Create test corpus
        test_dir, files = self.create_test_corpus(num_files, file_size_kb)
        
        try:
            times = []
            throughputs = []
            memory_peaks = []
            
            for run in range(runs):
                print(f"  Run {run + 1}/{runs}...", end=' ', flush=True)
                
                # Track memory if available
                if PSUTIL_AVAILABLE:
                    process = psutil.Process()
                    initial_mem = process.memory_info().rss / (1024 * 1024)
                
                # Run test
                processor = EnhancedParallelProcessor(
                    num_workers=num_workers,
                    mount_point=test_dir,
                    enable_monitoring=False,
                    enable_profiling=False
                )
                
                start = time.time()
                result = processor.process_files(files, enable_sorting=False)
                elapsed = time.time() - start
                
                times.append(elapsed)
                throughputs.append(result['stats']['files_per_second'])
                
                if PSUTIL_AVAILABLE:
                    peak_mem = process.memory_info().rss / (1024 * 1024)
                    memory_peaks.append(peak_mem - initial_mem)
                
                print(f"{elapsed:.2f}s", flush=True)
            
            # Calculate statistics
            times.sort()
            median_time = times[len(times) // 2]
            median_throughput = sorted(throughputs)[len(throughputs) // 2]
            
            result_data = {
                'num_files': num_files,
                'num_workers': num_workers,
                'file_size_kb': file_size_kb,
                'median_time': median_time,
                'min_time': min(times),
                'max_time': max(times),
                'median_throughput': median_throughput,
                'runs': runs
            }
            
            if PSUTIL_AVAILABLE:
                result_data['median_memory_mb'] = sorted(memory_peaks)[len(memory_peaks) // 2]
            
            self.results.append(result_data)
            
            print(f"  Median: {median_time:.2f}s "
                  f"({median_throughput:.1f} files/sec)")
            
            return result_data
        
        finally:
            # Cleanup
            shutil.rmtree(test_dir)
    
    def test_strong_scaling(self, num_files: int = 1000):
        """
        Strong scaling test: Fixed problem size, varying workers
        
        Tests parallel efficiency with fixed workload
        """
        print("\n" + "=" * 70)
        print("STRONG SCALING TEST")
        print(f"Fixed workload: {num_files} files")
        print("=" * 70)
        
        worker_counts = [1, 2, 4, 8, 16]
        baseline_time = None
        
        for workers in worker_counts:
            result = self.run_test(num_files, workers)
            
            if workers == 1:
                baseline_time = result['median_time']
                speedup = 1.0
                efficiency = 100.0
            else:
                speedup = baseline_time / result['median_time']
                efficiency = (speedup / workers) * 100
            
            print(f"  Speedup: {speedup:.2f}x, Efficiency: {efficiency:.1f}%")
    
    def test_weak_scaling(self, files_per_worker: int = 250):
        """
        Weak scaling test: Problem size scales with workers
        
        Tests if system can handle proportionally larger workloads
        """
        print("\n" + "=" * 70)
        print("WEAK SCALING TEST")
        print(f"Files per worker: {files_per_worker}")
        print("=" * 70)
        
        worker_counts = [1, 2, 4, 8]
        baseline_time = None
        
        for workers in worker_counts:
            num_files = workers * files_per_worker
            result = self.run_test(num_files, workers)
            
            if workers == 1:
                baseline_time = result['median_time']
            
            overhead = (result['median_time'] - baseline_time) / baseline_time * 100
            print(f"  Time overhead vs. baseline: {overhead:+.1f}%")
    
    def test_file_size_impact(self, num_workers: int = 8):
        """
        Test impact of file size on performance
        """
        print("\n" + "=" * 70)
        print("FILE SIZE IMPACT TEST")
        print("=" * 70)
        
        file_sizes = [1, 10, 100, 1000]  # KB
        num_files = 500
        
        for size in file_sizes:
            self.run_test(num_files, num_workers, file_size_kb=size)
    
    def test_load_scaling(self):
        """
        Test performance across different problem sizes
        """
        print("\n" + "=" * 70)
        print("LOAD SCALING TEST")
        print("=" * 70)
        
        file_counts = [100, 500, 1000, 5000, 10000]
        num_workers = 8
        
        for count in file_counts:
            self.run_test(count, num_workers)
    
    def save_results(self):
        """Save results to JSON file"""
        with open(self.output_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\nResults saved to {self.output_file}")
    
    def print_summary(self):
        """Print summary of all results"""
        print("\n" + "=" * 70)
        print("SCALABILITY TEST SUMMARY")
        print("=" * 70)
        
        print(f"\nTotal tests run: {len(self.results)}")
        
        # Find best configuration
        best = max(self.results, key=lambda r: r['median_throughput'])
        print(f"\nBest performance:")
        print(f"  Configuration: {best['num_workers']} workers, "
              f"{best['num_files']} files")
        print(f"  Throughput: {best['median_throughput']:.1f} files/sec")
        
        # Memory efficiency
        if PSUTIL_AVAILABLE and any('median_memory_mb' in r for r in self.results):
            print(f"\nMemory usage:")
            for r in self.results:
                if 'median_memory_mb' in r:
                    memory_per_file = r['median_memory_mb'] / r['num_files']
                    print(f"  {r['num_workers']}w, {r['num_files']}f: "
                          f"{r['median_memory_mb']:.1f} MB "
                          f"({memory_per_file*1024:.2f} KB/file)")


def run_all_tests():
    """Run comprehensive scalability test suite"""
    tester = ScalabilityTester()
    
    # Run all test types
    tester.test_strong_scaling(num_files=1000)
    tester.test_weak_scaling(files_per_worker=250)
    tester.test_file_size_impact(num_workers=8)
    tester.test_load_scaling()
    
    # Save and summarize
    tester.save_results()
    tester.print_summary()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Scalability testing')
    parser.add_argument('--test', choices=['strong', 'weak', 'filesize', 'load', 'all'],
                       default='all',
                       help='Test type to run')
    parser.add_argument('--output', default='scalability_results.json',
                       help='Output file for results')
    
    args = parser.parse_args()
    
    tester = ScalabilityTester(output_file=args.output)
    
    if args.test == 'all':
        run_all_tests()
    elif args.test == 'strong':
        tester.test_strong_scaling()
        tester.save_results()
    elif args.test == 'weak':
        tester.test_weak_scaling()
        tester.save_results()
    elif args.test == 'filesize':
        tester.test_file_size_impact()
        tester.save_results()
    elif args.test == 'load':
        tester.test_load_scaling()
        tester.save_results()