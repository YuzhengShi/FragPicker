#!/usr/bin/env python3
"""
Realistic performance test with larger files and simulated workload
Tests parallel processing under conditions similar to real FragPicker usage
"""

import unittest
import tempfile
import os
import sys
import time
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

from parallel_analyzer.parallel_processor import EnhancedParallelProcessor
from parallel_analyzer.multiprocess_processor import MultiprocessParallelProcessor


def create_fragmented_file(filepath, size_mb=10, write_pattern='random'):
    """
    Create a file with potential for fragmentation
    
    Args:
        filepath: Path to create file
        size_mb: Size in megabytes
        write_pattern: 'sequential' or 'random' writes
    """
    size_bytes = size_mb * 1024 * 1024
    
    if write_pattern == 'random':
        # Random writes can cause fragmentation on some filesystems
        with open(filepath, 'wb') as f:
            # Write in random-sized chunks
            written = 0
            while written < size_bytes:
                chunk_size = min(os.urandom(1)[0] * 1024 + 4096, size_bytes - written)
                f.write(os.urandom(chunk_size))
                written += chunk_size
                # Seek to create holes (sparse file behavior)
                if written < size_bytes and os.urandom(1)[0] < 50:
                    skip = min(4096, size_bytes - written)
                    f.seek(skip, 1)
                    written += skip
    else:
        # Sequential write
        with open(filepath, 'wb') as f:
            f.write(os.urandom(size_bytes))
    
    # Sync to ensure data is written
    os.sync()


def create_many_extent_file(filepath, num_extents=100):
    """
    Create a file likely to have many extents by writing in a scattered pattern
    
    This simulates files that have been updated many times over their lifetime
    """
    # Create a 10MB sparse file with scattered writes
    size = 10 * 1024 * 1024
    chunk_size = size // num_extents
    
    with open(filepath, 'wb') as f:
        for i in range(num_extents):
            # Write a chunk
            f.write(os.urandom(min(chunk_size, 65536)))
            # Skip ahead to create potential fragmentation
            if i < num_extents - 1:
                f.seek(chunk_size - 65536, 1)
    
    os.sync()


class TestRealisticWorkload(unittest.TestCase):
    """Test with realistic file sizes and patterns"""
    
    @classmethod
    def setUpClass(cls):
        """Create realistic test dataset"""
        cls.test_dir = tempfile.mkdtemp()
        cls.files = []
        
        print(f"\n{'='*70}")
        print("CREATING REALISTIC TEST DATASET")
        print(f"{'='*70}")
        print("This simulates real FragPicker workload:")
        print("  - Mix of small, medium, and large files")
        print("  - Files with potential fragmentation")
        print("  - Varied write patterns")
        print()
        
        start_time = time.time()
        
        # Small files (100 files, 100KB each) - Quick operations
        print("[1/4] Creating 100 small files (100KB each)...", end='', flush=True)
        for i in range(100):
            filepath = os.path.join(cls.test_dir, f"small_{i:03d}.dat")
            with open(filepath, 'wb') as f:
                f.write(os.urandom(100 * 1024))
            stat = os.stat(filepath)
            cls.files.append((str(stat.st_ino), 1))
        print(f" Done ({time.time()-start_time:.1f}s)")
        
        # Medium files (50 files, 1MB each) - Moderate operations
        print("[2/4] Creating 50 medium files (1MB each)...", end='', flush=True)
        for i in range(50):
            filepath = os.path.join(cls.test_dir, f"medium_{i:03d}.dat")
            create_fragmented_file(filepath, size_mb=1, write_pattern='random')
            stat = os.stat(filepath)
            cls.files.append((str(stat.st_ino), 1))
        print(f" Done ({time.time()-start_time:.1f}s)")
        
        # Large files (20 files, 10MB each) - Slow operations
        print("[3/4] Creating 20 large files (10MB each)...", end='', flush=True)
        for i in range(20):
            filepath = os.path.join(cls.test_dir, f"large_{i:03d}.dat")
            create_fragmented_file(filepath, size_mb=10, write_pattern='random')
            stat = os.stat(filepath)
            cls.files.append((str(stat.st_ino), 1))
        print(f" Done ({time.time()-start_time:.1f}s)")
        
        # Very large files with many potential extents (10 files, 10MB each)
        print("[4/4] Creating 10 files with scattered writes...", end='', flush=True)
        for i in range(10):
            filepath = os.path.join(cls.test_dir, f"scattered_{i:03d}.dat")
            create_many_extent_file(filepath, num_extents=50)
            stat = os.stat(filepath)
            cls.files.append((str(stat.st_ino), 1))
        print(f" Done ({time.time()-start_time:.1f}s)")
        
        setup_time = time.time() - start_time
        total_size = sum(os.path.getsize(os.path.join(cls.test_dir, f)) 
                        for f in os.listdir(cls.test_dir)) / (1024*1024)
        
        print()
        print(f"Dataset ready: {len(cls.files)} files, {total_size:.1f}MB total")
        print(f"Setup time: {setup_time:.1f}s")
        print(f"{'='*70}\n")
    
    @classmethod
    def tearDownClass(cls):
        """Cleanup"""
        import shutil
        shutil.rmtree(cls.test_dir)
    
    def test_realistic_comparison(self):
        """Compare threading vs multiprocessing on realistic workload"""
        print(f"\n{'='*70}")
        print("REALISTIC WORKLOAD PERFORMANCE TEST")
        print(f"{'='*70}")
        print(f"Dataset: {len(self.files)} files (mix of sizes)")
        print()
        
        results = {}
        
        # Test 1: Single-threaded baseline
        print("[1/5] Testing single-threaded baseline...")
        processor1 = EnhancedParallelProcessor(
            num_workers=1,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        start = time.time()
        result1 = processor1.process_files(self.files, enable_sorting=True)
        results['single_thread'] = time.time() - start
        print(f"      Time: {results['single_thread']:.3f}s")
        
        # Test 2: Threading with 4 workers
        print("[2/5] Testing threading (4 workers)...")
        processor2 = EnhancedParallelProcessor(
            num_workers=4,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        start = time.time()
        result2 = processor2.process_files(self.files, enable_sorting=True)
        results['threading_4'] = time.time() - start
        print(f"      Time: {results['threading_4']:.3f}s")
        
        # Test 3: Multiprocessing with 2 workers
        print("[3/5] Testing multiprocessing (2 workers)...")
        processor3 = MultiprocessParallelProcessor(
            num_workers=2,
            mount_point=self.test_dir,
            enable_monitoring=False
        )
        start = time.time()
        result3 = processor3.process_files(self.files, enable_sorting=True)
        results['multiprocess_2'] = time.time() - start
        print(f"      Time: {results['multiprocess_2']:.3f}s")
        
        # Test 4: Multiprocessing with 4 workers
        print("[4/5] Testing multiprocessing (4 workers)...")
        processor4 = MultiprocessParallelProcessor(
            num_workers=4,
            mount_point=self.test_dir,
            enable_monitoring=False
        )
        start = time.time()
        result4 = processor4.process_files(self.files, enable_sorting=True)
        results['multiprocess_4'] = time.time() - start
        print(f"      Time: {results['multiprocess_4']:.3f}s")
        
        # Test 5: Multiprocessing with 8 workers (if available)
        print("[5/5] Testing multiprocessing (8 workers)...")
        processor5 = MultiprocessParallelProcessor(
            num_workers=8,
            mount_point=self.test_dir,
            enable_monitoring=False
        )
        start = time.time()
        result5 = processor5.process_files(self.files, enable_sorting=True)
        results['multiprocess_8'] = time.time() - start
        print(f"      Time: {results['multiprocess_8']:.3f}s")
        
        # Print detailed comparison
        print(f"\n{'='*70}")
        print("RESULTS")
        print(f"{'='*70}")
        
        baseline = results['single_thread']
        
        print(f"{'Method':<25} {'Time':>10} {'Speedup':>10} {'Throughput':>15}")
        print("-" * 70)
        
        for name, elapsed in sorted(results.items()):
            speedup = baseline / elapsed
            throughput = len(self.files) / elapsed
            marker = "🚀" if speedup > 1.5 else "✓" if speedup > 1.0 else "⚠"
            print(f"{marker} {name:<23} {elapsed:>8.3f}s  {speedup:>8.2f}x  {throughput:>12.1f} files/s")
        
        print(f"{'='*70}\n")
        
        # Calculate key metrics
        threading_speedup = baseline / results['threading_4']
        mp2_speedup = baseline / results['multiprocess_2']
        mp4_speedup = baseline / results['multiprocess_4']
        mp8_speedup = baseline / results['multiprocess_8']
        
        print("KEY FINDINGS:")
        print(f"  Threading (4 workers):         {threading_speedup:>5.2f}x")
        print(f"  Multiprocessing (2 workers):   {mp2_speedup:>5.2f}x")
        print(f"  Multiprocessing (4 workers):   {mp4_speedup:>5.2f}x")
        print(f"  Multiprocessing (8 workers):   {mp8_speedup:>5.2f}x")
        print()
        
        if mp4_speedup > 2.0:
            print("🎉 EXCELLENT: 2x+ speedup achieved with multiprocessing!")
        elif mp4_speedup > 1.5:
            print("✅ GOOD: Significant speedup with multiprocessing")
        elif mp4_speedup > 1.1:
            print("✓ OK: Moderate speedup with multiprocessing")
        else:
            print("ℹ️  File operations still too fast - need even larger dataset")
        
        # Verify correctness
        self.assertEqual(result1['stats']['successful'], len(self.files))
        self.assertEqual(result2['stats']['successful'], len(self.files))
        self.assertEqual(result3['stats']['successful'], len(self.files))
        self.assertEqual(result4['stats']['successful'], len(self.files))
        self.assertEqual(result5['stats']['successful'], len(self.files))


if __name__ == '__main__':
    unittest.main(verbosity=2)
