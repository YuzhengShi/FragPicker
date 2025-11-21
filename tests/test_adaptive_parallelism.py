#!/usr/bin/env python3
"""
Adaptive parallelism tests
Automatically choose optimal worker count based on workload characteristics
"""

import unittest
import sys
import os
import tempfile
import shutil
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

from parallel_analyzer.parallel_processor import EnhancedParallelProcessor


class AdaptiveParallelismSelector:
    """
    Intelligently selects optimal worker count based on:
    - File count
    - I/O speed (sampled)
    - Available CPU cores
    """
    
    def __init__(self, mount_point):
        self.mount_point = mount_point
    
    def measure_io_speed(self, sample_files, sample_size=100):
        """
        Measure I/O speed by processing a sample of files
        Returns: average time per file in seconds
        """
        if len(sample_files) == 0:
            return 0.0001  # Assume fast I/O
        
        # Sample up to sample_size files
        sample = sample_files[:min(sample_size, len(sample_files))]
        
        # Process with single worker to get baseline
        processor = EnhancedParallelProcessor(
            num_workers=1,
            mount_point=self.mount_point,
            enable_monitoring=False,
            enable_profiling=False
        )
        
        start = time.time()
        result = processor.process_files(sample, enable_sorting=True)
        elapsed = time.time() - start
        
        if result['stats']['successful'] == 0:
            return 0.0001
        
        avg_time_per_file = elapsed / result['stats']['successful']
        return avg_time_per_file
    
    def recommend_worker_count(self, num_files, avg_io_time=None):
        """
        Recommend optimal worker count based on workload
        
        Rules:
        - Fast I/O (<0.0001s/file): 1 worker (overhead dominates)
        - Medium I/O (0.0001-0.001s/file): 2-4 workers
        - Slow I/O (>0.001s/file): 4-8 workers
        - Very large datasets: scale up to 16 workers
        """
        import multiprocessing
        max_workers = multiprocessing.cpu_count()
        
        # If I/O time not provided, estimate based on typical SSD
        if avg_io_time is None:
            avg_io_time = 0.00005  # 50 microseconds typical for SSD
        
        # Decision logic
        if avg_io_time < 0.0001:  # Very fast I/O (modern SSD)
            if num_files < 1000:
                return 1  # Overhead not worth it
            else:
                return min(2, max_workers)  # Minimal parallelism
        
        elif avg_io_time < 0.001:  # Medium I/O (fragmented SSD, fast HDD)
            if num_files < 100:
                return min(2, max_workers)
            elif num_files < 1000:
                return min(4, max_workers)
            else:
                return min(8, max_workers)
        
        else:  # Slow I/O (HDD, network FS)
            if num_files < 100:
                return min(4, max_workers)
            else:
                return min(8, max_workers)
    
    def get_speedup_estimate(self, num_files, num_workers, avg_io_time):
        """
        Estimate expected speedup based on Amdahl's law
        
        Speedup = 1 / (serial_fraction + (parallel_fraction / num_workers))
        """
        # Overhead per file (queue operations, thread switching)
        overhead_per_file = 0.00001  # 10 microseconds
        
        # Serial fraction (setup, teardown, inode mapping)
        serial_time = 0.05  # 50ms fixed overhead
        
        # Parallel fraction (actual file processing)
        parallel_time = num_files * avg_io_time
        
        # Total time single-threaded
        total_time_1w = serial_time + parallel_time
        
        # Parallel overhead
        parallel_overhead = num_files * overhead_per_file * (num_workers - 1)
        
        # Total time with N workers
        total_time_nw = serial_time + (parallel_time / num_workers) + parallel_overhead
        
        # Avoid division by zero
        if total_time_nw <= 0:
            return 1.0
        
        speedup = total_time_1w / total_time_nw
        return max(0.1, speedup)  # Minimum 0.1x


class TestAdaptiveParallelism(unittest.TestCase):
    """Test adaptive worker selection"""
    
    def setUp(self):
        """Create test environment"""
        self.test_dir = tempfile.mkdtemp(prefix="adaptive_test_")
        self.selector = AdaptiveParallelismSelector(self.test_dir)
    
    def tearDown(self):
        """Clean up test environment"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_fast_io_recommendation(self):
        """Test recommendation for fast I/O (SSD)"""
        # Fast I/O: 0.00005s per file
        workers = self.selector.recommend_worker_count(
            num_files=500,
            avg_io_time=0.00005
        )
        
        # Should recommend 1-2 workers for fast I/O
        self.assertLessEqual(workers, 2)
        print(f"\nFast I/O (500 files): {workers} workers recommended")
    
    def test_slow_io_recommendation(self):
        """Test recommendation for slow I/O (HDD, network)"""
        # Slow I/O: 0.002s per file (2ms)
        workers = self.selector.recommend_worker_count(
            num_files=1000,
            avg_io_time=0.002
        )
        
        # Should recommend 4-8 workers for slow I/O
        self.assertGreaterEqual(workers, 4)
        self.assertLessEqual(workers, 8)
        print(f"\nSlow I/O (1000 files): {workers} workers recommended")
    
    def test_small_dataset_recommendation(self):
        """Test recommendation for small datasets"""
        workers = self.selector.recommend_worker_count(
            num_files=50,
            avg_io_time=0.0001
        )
        
        # Small datasets should use fewer workers
        self.assertLessEqual(workers, 4)
        print(f"\nSmall dataset (50 files): {workers} workers recommended")
    
    def test_large_dataset_recommendation(self):
        """Test recommendation for large datasets"""
        workers = self.selector.recommend_worker_count(
            num_files=10000,
            avg_io_time=0.001
        )
        
        # Large datasets with slow I/O should use more workers
        self.assertGreaterEqual(workers, 4)
        print(f"\nLarge dataset (10000 files): {workers} workers recommended")
    
    def test_speedup_estimation(self):
        """Test speedup prediction accuracy"""
        num_files = 1000
        avg_io_time = 0.001  # 1ms per file
        
        for workers in [1, 2, 4, 8]:
            estimated_speedup = self.selector.get_speedup_estimate(
                num_files, workers, avg_io_time
            )
            
            print(f"\nEstimated speedup with {workers} workers: {estimated_speedup:.2f}x")
            
            # Sanity checks
            if workers == 1:
                self.assertAlmostEqual(estimated_speedup, 1.0, places=1)
            else:
                # Speedup should be positive and less than worker count
                self.assertGreater(estimated_speedup, 0.5)
                self.assertLess(estimated_speedup, workers * 1.2)
    
    def test_io_speed_measurement(self):
        """Test actual I/O speed measurement"""
        files = []
        
        # Create 100 test files
        for i in range(100):
            filepath = os.path.join(self.test_dir, f"file_{i}.dat")
            with open(filepath, 'wb') as f:
                f.write(os.urandom(10 * 1024))
            
            stat = os.stat(filepath)
            files.append((str(stat.st_ino), 1))
        
        # Measure I/O speed
        avg_time = self.selector.measure_io_speed(files, sample_size=50)
        
        print(f"\nMeasured I/O speed: {avg_time*1000:.3f}ms per file")
        
        # Should be reasonably fast on local disk
        self.assertLess(avg_time, 0.1)  # Less than 100ms per file
        self.assertGreater(avg_time, 0.00001)  # More than 10 microseconds
    
    def test_adaptive_workflow(self):
        """Test complete adaptive workflow"""
        files = []
        
        # Create 500 test files
        print("\nCreating 500 test files...")
        for i in range(500):
            filepath = os.path.join(self.test_dir, f"file_{i}.dat")
            with open(filepath, 'wb') as f:
                f.write(os.urandom(10 * 1024))
            
            stat = os.stat(filepath)
            files.append((str(stat.st_ino), 1))
        
        # Step 1: Measure I/O speed with sample
        print("Step 1: Measuring I/O speed...")
        avg_io_time = self.selector.measure_io_speed(files, sample_size=50)
        print(f"  I/O speed: {avg_io_time*1000:.3f}ms per file")
        
        # Step 2: Get recommendation
        print("Step 2: Getting worker recommendation...")
        recommended_workers = self.selector.recommend_worker_count(
            len(files), avg_io_time
        )
        print(f"  Recommended: {recommended_workers} workers")
        
        # Step 3: Estimate speedup
        estimated_speedup = self.selector.get_speedup_estimate(
            len(files), recommended_workers, avg_io_time
        )
        print(f"  Estimated speedup: {estimated_speedup:.2f}x")
        
        # Step 4: Process with recommended settings
        print(f"Step 3: Processing with {recommended_workers} workers...")
        processor = EnhancedParallelProcessor(
            num_workers=recommended_workers,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        
        start = time.time()
        result = processor.process_files(files, enable_sorting=True)
        elapsed = time.time() - start
        
        print(f"  Completed in {elapsed:.2f}s")
        print(f"  Throughput: {result['stats']['files_per_second']:.1f} files/sec")
        
        # Verify success
        self.assertEqual(result['stats']['successful'], 500)
        self.assertEqual(result['stats']['failed'], 0)


def run_adaptive_tests():
    """Run all adaptive parallelism tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestAdaptiveParallelism))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_adaptive_tests())
