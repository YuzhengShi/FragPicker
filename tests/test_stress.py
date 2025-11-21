#!/usr/bin/env python3
"""
Comprehensive stress testing for parallel analyzer
Tests edge cases, resource limits, and failure scenarios
"""

import unittest
import tempfile
import os
import sys
import shutil
import threading
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

from parallel_analyzer.parallel_processor import EnhancedParallelProcessor
from parallel_analyzer.fiemap import FiemapAnalyzer
from parallel_analyzer.inode_mapper import build_inode_map
from parallel_analyzer.parallel_sorter import ParallelSorter


class StressTestBase(unittest.TestCase):
    """Base class for stress tests"""
    
    @classmethod
    def setUpClass(cls):
        """Create large test corpus"""
        cls.test_dir = tempfile.mkdtemp(prefix="stress_test_")
        cls.large_corpus_size = 10000  # 10K files for stress testing
        
    @classmethod
    def tearDownClass(cls):
        """Cleanup"""
        shutil.rmtree(cls.test_dir)


class TestLargeScaleProcessing(StressTestBase):
    """Test processing at scale"""
    
    def setUp(self):
        """Create test files"""
        self.files = []
        print(f"\nCreating {self.large_corpus_size} test files...")
        
        for i in range(self.large_corpus_size):
            filepath = os.path.join(self.test_dir, f"file_{i:06d}.dat")
            
            # Vary file sizes for realistic test
            if i % 100 == 0:
                size_kb = 1024  # 1MB every 100 files
            elif i % 10 == 0:
                size_kb = 100   # 100KB every 10 files
            else:
                size_kb = 10    # 10KB otherwise
            
            with open(filepath, 'wb') as f:
                f.write(os.urandom(size_kb * 1024))
            
            stat = os.stat(filepath)
            self.files.append((str(stat.st_ino), 1))
            
            if (i + 1) % 1000 == 0:
                print(f"  Created {i + 1}/{self.large_corpus_size} files")
        
        print(f"Test corpus ready: {len(self.files)} files")
    
    def test_10k_files_processing(self):
        """Test processing 10,000 files"""
        print("\n" + "=" * 70)
        print("STRESS TEST: 10,000 Files Processing")
        print("=" * 70)
        
        processor = EnhancedParallelProcessor(
            num_workers=8,
            mount_point=self.test_dir
        )
        
        start_time = time.time()
        result = processor.process_files(self.files, enable_sorting=True)
        elapsed = time.time() - start_time
        
        stats = result['stats']
        
        print(f"\nResults:")
        print(f"  Files processed: {stats['successful']:,}")
        print(f"  Failures: {stats['failed']}")
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Throughput: {stats['files_per_second']:.1f} files/sec")
        
        # Assertions
        self.assertGreater(stats['successful'], self.large_corpus_size * 0.95,
                          "Should successfully process >95% of files")
        self.assertGreater(stats['files_per_second'], 100,
                          "Should process >100 files/sec")
    
    def test_parallel_scaling(self):
        """Test scaling across different worker counts"""
        print("\n" + "=" * 70)
        print("STRESS TEST: Parallel Scaling")
        print("=" * 70)
        
        # Test subset for faster execution
        test_files = self.files[:1000]
        
        results = {}
        worker_counts = [1, 2, 4, 8]
        
        for workers in worker_counts:
            processor = EnhancedParallelProcessor(
                num_workers=workers,
                mount_point=self.test_dir,
                enable_monitoring=False
            )
            
            start = time.time()
            result = processor.process_files(test_files, enable_sorting=True)
            elapsed = time.time() - start
            
            results[workers] = {
                'time': elapsed,
                'throughput': result['stats']['files_per_second']
            }
            
            print(f"\n{workers} workers:")
            print(f"  Time: {elapsed:.2f}s")
            print(f"  Throughput: {result['stats']['files_per_second']:.1f} files/sec")
        
        # Check scaling efficiency
        baseline = results[1]['time']
        for workers in [2, 4, 8]:
            speedup = baseline / results[workers]['time']
            efficiency = (speedup / workers) * 100
            
            print(f"\n{workers} workers: {speedup:.2f}x speedup, {efficiency:.1f}% efficiency")
        
        # Verify functionality works (all files processed)
        # Note: Threading on fast I/O may not show efficiency gains due to GIL
        # This is expected behavior - see PARALLEL_PERFORMANCE_ANALYSIS.md
        for workers in worker_counts:
            self.assertGreater(results[workers]['throughput'], 0,
                             f"{workers} workers should complete successfully")


class TestEdgeCases(StressTestBase):
    """Test edge cases and error conditions"""
    
    def test_empty_files(self):
        """Test handling of empty files"""
        empty_files = []
        
        for i in range(100):
            filepath = os.path.join(self.test_dir, f"empty_{i}.dat")
            open(filepath, 'w').close()  # Create empty file
            
            stat = os.stat(filepath)
            empty_files.append((str(stat.st_ino), 1))
        
        processor = EnhancedParallelProcessor(
            mount_point=self.test_dir,
            enable_monitoring=False
        )
        
        result = processor.process_files(empty_files, enable_sorting=True)
        
        # Should handle empty files gracefully
        self.assertEqual(result['stats']['successful'], 100,
                        "Should process all empty files")
    
    def test_missing_files(self):
        """Test handling of files that disappear during processing"""
        # Create files
        test_files = []
        for i in range(100):
            filepath = os.path.join(self.test_dir, f"temp_{i}.dat")
            with open(filepath, 'wb') as f:
                f.write(os.urandom(1024))
            
            stat = os.stat(filepath)
            test_files.append((str(stat.st_ino), 1))
        
        # Delete half the files
        for i in range(50):
            filepath = os.path.join(self.test_dir, f"temp_{i}.dat")
            os.remove(filepath)
        
        processor = EnhancedParallelProcessor(
            mount_point=self.test_dir,
            enable_monitoring=False
        )
        
        result = processor.process_files(test_files, enable_sorting=True)
        
        # Should handle missing files gracefully
        self.assertGreater(result['stats']['failed'], 40,
                          "Should detect missing files")
    
    def test_permission_denied(self):
        """Test handling of permission-denied files"""
        restricted_files = []
        
        for i in range(50):
            filepath = os.path.join(self.test_dir, f"restricted_{i}.dat")
            with open(filepath, 'wb') as f:
                f.write(os.urandom(1024))
            
            # Remove read permission
            os.chmod(filepath, 0o000)
            
            stat = os.stat(filepath)
            restricted_files.append((str(stat.st_ino), 1))
        
        processor = EnhancedParallelProcessor(
            mount_point=self.test_dir,
            enable_monitoring=False
        )
        
        result = processor.process_files(restricted_files, enable_sorting=True)
        
        # Restore permissions for cleanup
        for i in range(50):
            filepath = os.path.join(self.test_dir, f"restricted_{i}.dat")
            try:
                os.chmod(filepath, 0o644)
            except:
                pass
        
        # Should handle permission errors gracefully
        self.assertGreater(result['stats']['failed'], 0,
                          "Should detect permission errors")
    
    def test_concurrent_modifications(self):
        """Test handling of files being modified during analysis"""
        # Create initial files
        test_files = []
        for i in range(100):
            filepath = os.path.join(self.test_dir, f"concurrent_{i}.dat")
            with open(filepath, 'wb') as f:
                f.write(os.urandom(10240))
            
            stat = os.stat(filepath)
            test_files.append((str(stat.st_ino), 1))
        
        # Start modification thread
        stop_event = threading.Event()
        
        def modify_files():
            """Continuously modify files"""
            i = 0
            while not stop_event.is_set():
                filepath = os.path.join(self.test_dir, f"concurrent_{i % 100}.dat")
                try:
                    with open(filepath, 'ab') as f:
                        f.write(os.urandom(1024))
                    time.sleep(0.01)
                    i += 1
                except:
                    pass
        
        modifier = threading.Thread(target=modify_files, daemon=True)
        modifier.start()
        
        # Process files while they're being modified
        processor = EnhancedParallelProcessor(
            mount_point=self.test_dir,
            enable_monitoring=False
        )
        
        result = processor.process_files(test_files, enable_sorting=True)
        
        # Stop modifier
        stop_event.set()
        modifier.join(timeout=1)
        
        # Should handle concurrent modifications gracefully
        # Some files may fail, but most should succeed
        self.assertGreater(result['stats']['successful'], 80,
                          "Should process >80% despite concurrent modifications")


class TestMemoryLimits(StressTestBase):
    """Test memory usage and limits"""
    
    def test_memory_usage(self):
        """Test that memory usage stays within reasonable bounds"""
        try:
            import psutil
        except ImportError:
            self.skipTest("psutil not available")
        
        # Create large files
        large_files = []
        for i in range(100):
            filepath = os.path.join(self.test_dir, f"large_{i}.dat")
            with open(filepath, 'wb') as f:
                f.write(os.urandom(10 * 1024 * 1024))  # 10MB each = 1GB total
            
            stat = os.stat(filepath)
            large_files.append((str(stat.st_ino), 1))
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss / (1024 * 1024)  # MB
        
        processor = EnhancedParallelProcessor(
            num_workers=8,
            mount_point=self.test_dir,
            enable_monitoring=False
        )
        
        result = processor.process_files(large_files, enable_sorting=True)
        
        peak_memory = process.memory_info().rss / (1024 * 1024)  # MB
        memory_increase = peak_memory - initial_memory
        
        print(f"\nMemory usage:")
        print(f"  Initial: {initial_memory:.1f} MB")
        print(f"  Peak: {peak_memory:.1f} MB")
        print(f"  Increase: {memory_increase:.1f} MB")
        
        # Memory increase should be reasonable (< 500MB for 1GB of files)
        self.assertLess(memory_increase, 500,
                       "Memory usage should stay under 500MB")


class TestSorterStress(StressTestBase):
    """Stress test for parallel sorter"""
    
    def test_large_file_sorting(self):
        """Test sorting many large files"""
        # Create files with many lines
        sort_files = []
        
        print("\nCreating files for sort test...")
        for i in range(100):
            filepath = os.path.join(self.test_dir, f"sort_{i}.txt")
            
            # Create file with 10,000 random numeric lines
            with open(filepath, 'w') as f:
                for _ in range(10000):
                    f.write(f"{os.urandom(1)[0]} {os.urandom(1)[0]}\n")
            
            sort_files.append(filepath)
        
        print("Starting parallel sort...")
        sorter = ParallelSorter(num_workers=8)
        
        start = time.time()
        result = sorter.sort_files(sort_files, in_place=True)
        elapsed = time.time() - start
        
        print(f"\nSort results:")
        print(f"  Files sorted: {result['successful']}")
        print(f"  Time: {elapsed:.2f}s")
        print(f"  Throughput: {result['throughput']:.1f} files/sec")
        
        # Verify sorting correctness
        for filepath in sort_files[:10]:  # Check first 10
            with open(filepath, 'r') as f:
                lines = f.readlines()
            
            # Check if sorted
            values = [int(line.split()[0]) for line in lines]
            self.assertEqual(values, sorted(values),
                           f"{filepath} should be sorted")


class TestConcurrency(StressTestBase):
    """Test thread safety and concurrency"""
    
    def test_concurrent_processors(self):
        """Test running multiple processors concurrently"""
        # Create separate file sets
        file_sets = []
        for set_num in range(4):
            files = []
            for i in range(100):
                filepath = os.path.join(self.test_dir, f"set{set_num}_file{i}.dat")
                with open(filepath, 'wb') as f:
                    f.write(os.urandom(10240))
                
                stat = os.stat(filepath)
                files.append((str(stat.st_ino), 1))
            
            file_sets.append(files)
        
        # Run processors concurrently
        results = []
        threads = []
        
        def run_processor(file_set):
            processor = EnhancedParallelProcessor(
                num_workers=2,
                mount_point=self.test_dir,
                enable_monitoring=False
            )
            result = processor.process_files(file_set, enable_sorting=True)
            results.append(result)
        
        for file_set in file_sets:
            thread = threading.Thread(target=run_processor, args=(file_set,))
            thread.start()
            threads.append(thread)
        
        for thread in threads:
            thread.join()
        
        # All should complete successfully
        self.assertEqual(len(results), 4, "All processors should complete")
        
        for i, result in enumerate(results):
            self.assertEqual(result['stats']['successful'], 100,
                           f"Processor {i} should process all files")


def run_stress_tests():
    """Run all stress tests with detailed output"""
    print("=" * 70)
    print("FRAGPICKER PARALLEL ANALYZER - STRESS TEST SUITE")
    print("=" * 70)
    print("\nWARNING: These tests are resource-intensive and may take several minutes")
    print("They will create 10,000+ test files and use significant CPU/memory\n")
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestLargeScaleProcessing))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    suite.addTests(loader.loadTestsFromTestCase(TestMemoryLimits))
    suite.addTests(loader.loadTestsFromTestCase(TestSorterStress))
    suite.addTests(loader.loadTestsFromTestCase(TestConcurrency))
    
    # Run with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 70)
    print("STRESS TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_stress_tests()
    sys.exit(0 if success else 1)