#!/usr/bin/env python3
"""
Compare threading vs multiprocessing performance
"""

import unittest
import tempfile
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

from parallel_analyzer.parallel_processor import EnhancedParallelProcessor
from parallel_analyzer.multiprocess_processor import MultiprocessParallelProcessor


class TestMultiprocessComparison(unittest.TestCase):
    """Compare threading vs multiprocessing"""
    
    @classmethod
    def setUpClass(cls):
        """Create test dataset"""
        cls.test_dir = tempfile.mkdtemp()
        cls.files = []
        
        print(f"\n[Setup] Creating 1000 test files...")
        for i in range(1000):
            filepath = os.path.join(cls.test_dir, f"test_{i:04d}.dat")
            with open(filepath, 'wb') as f:
                f.write(os.urandom(10 * 1024))  # 10KB each
            
            stat = os.stat(filepath)
            cls.files.append((str(stat.st_ino), 1))
        
        print(f"[Setup] Created {len(cls.files)} test files")
    
    @classmethod
    def tearDownClass(cls):
        """Cleanup"""
        import shutil
        shutil.rmtree(cls.test_dir)
    
    def test_threading_baseline(self):
        """Baseline: single-threaded processing"""
        print("\n" + "=" * 70)
        print("THREADING BASELINE (1 worker)")
        print("=" * 70)
        
        processor = EnhancedParallelProcessor(
            num_workers=1,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        
        start = time.time()
        result = processor.process_files(self.files, enable_sorting=True)
        elapsed = time.time() - start
        
        print(f"Time: {elapsed:.3f}s")
        print(f"Throughput: {result['stats']['files_per_second']:.1f} files/sec")
        print(f"Processed: {result['stats']['successful']}/{result['stats']['total_files']}")
        
        self.assertEqual(result['stats']['successful'], 1000)
        
        return elapsed
    
    def test_threading_parallel(self):
        """Threading with 4 workers"""
        print("\n" + "=" * 70)
        print("THREADING (4 workers)")
        print("=" * 70)
        
        processor = EnhancedParallelProcessor(
            num_workers=4,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        
        start = time.time()
        result = processor.process_files(self.files, enable_sorting=True)
        elapsed = time.time() - start
        
        print(f"Time: {elapsed:.3f}s")
        print(f"Throughput: {result['stats']['files_per_second']:.1f} files/sec")
        print(f"Processed: {result['stats']['successful']}/{result['stats']['total_files']}")
        
        self.assertEqual(result['stats']['successful'], 1000)
        
        return elapsed
    
    def test_multiprocess_parallel(self):
        """Multiprocessing with 4 workers"""
        print("\n" + "=" * 70)
        print("MULTIPROCESSING (4 workers)")
        print("=" * 70)
        
        processor = MultiprocessParallelProcessor(
            num_workers=4,
            mount_point=self.test_dir,
            enable_monitoring=False
        )
        
        start = time.time()
        result = processor.process_files(self.files, enable_sorting=True)
        elapsed = time.time() - start
        
        print(f"Time: {elapsed:.3f}s")
        print(f"Throughput: {result['stats']['files_per_second']:.1f} files/sec")
        print(f"Processed: {result['stats']['successful']}/{result['stats']['total_files']}")
        
        self.assertEqual(result['stats']['successful'], 1000)
        
        return elapsed
    
    def test_full_comparison(self):
        """Run full comparison of all approaches"""
        print("\n" + "=" * 70)
        print("COMPREHENSIVE PERFORMANCE COMPARISON")
        print("=" * 70)
        print(f"Dataset: {len(self.files)} files")
        print(f"File size: 10KB each")
        print()
        
        results = {}
        
        # Test 1: Threading with 1 worker
        processor1 = EnhancedParallelProcessor(
            num_workers=1,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        start = time.time()
        result1 = processor1.process_files(self.files, enable_sorting=True)
        results['threading_1'] = time.time() - start
        
        # Test 2: Threading with 4 workers
        processor2 = EnhancedParallelProcessor(
            num_workers=4,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        start = time.time()
        result2 = processor2.process_files(self.files, enable_sorting=True)
        results['threading_4'] = time.time() - start
        
        # Test 3: Multiprocessing with 2 workers
        processor3 = MultiprocessParallelProcessor(
            num_workers=2,
            mount_point=self.test_dir,
            enable_monitoring=False
        )
        start = time.time()
        result3 = processor3.process_files(self.files, enable_sorting=True)
        results['multiprocess_2'] = time.time() - start
        
        # Test 4: Multiprocessing with 4 workers
        processor4 = MultiprocessParallelProcessor(
            num_workers=4,
            mount_point=self.test_dir,
            enable_monitoring=False
        )
        start = time.time()
        result4 = processor4.process_files(self.files, enable_sorting=True)
        results['multiprocess_4'] = time.time() - start
        
        # Print comparison
        print("\nRESULTS:")
        print("-" * 70)
        baseline = results['threading_1']
        
        for name, elapsed in results.items():
            speedup = baseline / elapsed
            throughput = len(self.files) / elapsed
            print(f"{name:20s}: {elapsed:.3f}s  |  {speedup:.2f}x  |  {throughput:.1f} files/sec")
        
        print("-" * 70)
        print()
        
        # Calculate speedups
        threading_speedup = baseline / results['threading_4']
        multiprocess_speedup_2 = baseline / results['multiprocess_2']
        multiprocess_speedup_4 = baseline / results['multiprocess_4']
        
        print("KEY FINDINGS:")
        print(f"  Threading (4 workers):       {threading_speedup:.2f}x speedup")
        print(f"  Multiprocessing (2 workers): {multiprocess_speedup_2:.2f}x speedup")
        print(f"  Multiprocessing (4 workers): {multiprocess_speedup_4:.2f}x speedup")
        print()
        
        if multiprocess_speedup_4 > 1.5:
            print("✅ Multiprocessing shows significant speedup!")
        elif multiprocess_speedup_4 > threading_speedup:
            print("✅ Multiprocessing outperforms threading")
        else:
            print("ℹ️  Overhead dominates on this workload")
        
        # All should process all files correctly
        self.assertEqual(result1['stats']['successful'], 1000)
        self.assertEqual(result2['stats']['successful'], 1000)
        self.assertEqual(result3['stats']['successful'], 1000)
        self.assertEqual(result4['stats']['successful'], 1000)


if __name__ == '__main__':
    # Run with verbose output
    unittest.main(verbosity=2)
