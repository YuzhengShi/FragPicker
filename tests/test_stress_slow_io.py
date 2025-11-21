#!/usr/bin/env python3
"""
Stress test WITH slow I/O simulation
Demonstrates parallel speedup on stress test scale (10,000 files)
"""

import unittest
import tempfile
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

# Monkey-patch FiemapAnalyzer to add artificial delay
from parallel_analyzer import fiemap
original_get_extents = fiemap.FiemapAnalyzer.get_extents

def slow_get_extents(self, filepath, validate=True):
    """Add 1ms delay to simulate slow I/O"""
    time.sleep(0.001)  # 1ms delay per file
    return original_get_extents(self, filepath, validate)

fiemap.FiemapAnalyzer.get_extents = slow_get_extents

from parallel_analyzer.parallel_processor import EnhancedParallelProcessor
from parallel_analyzer.multiprocess_processor import MultiprocessParallelProcessor


class TestStressWithSlowIO(unittest.TestCase):
    """Stress test with simulated slow I/O"""
    
    @classmethod
    def setUpClass(cls):
        """Create 5000-file test dataset"""
        cls.test_dir = tempfile.mkdtemp()
        cls.files = []
        
        print(f"\n{'='*70}")
        print("STRESS TEST WITH SLOW I/O SIMULATION")
        print(f"{'='*70}")
        print("Creating 5,000 test files (this may take a minute)...")
        print("Simulating 1ms I/O delay per file (represents fragmented HDD)")
        print()
        
        start = time.time()
        for i in range(5000):
            filepath = os.path.join(cls.test_dir, f"file_{i:05d}.dat")
            
            # Vary file sizes
            if i % 100 == 0:
                size = 100 * 1024  # 100KB
            elif i % 10 == 0:
                size = 50 * 1024   # 50KB
            else:
                size = 10 * 1024   # 10KB
            
            with open(filepath, 'wb') as f:
                f.write(os.urandom(size))
            
            stat = os.stat(filepath)
            cls.files.append((str(stat.st_ino), 1))
            
            if (i + 1) % 1000 == 0:
                print(f"  Created {i+1}/5000 files ({time.time()-start:.1f}s)")
        
        setup_time = time.time() - start
        print(f"\nDataset ready: {len(cls.files)} files in {setup_time:.1f}s")
        print(f"Expected baseline time: ~{len(cls.files) * 0.001:.1f}s (with 1ms delay)")
        print(f"{'='*70}\n")
    
    @classmethod
    def tearDownClass(cls):
        """Cleanup"""
        import shutil
        shutil.rmtree(cls.test_dir)
    
    def test_large_scale_speedup(self):
        """Test that parallel processing shows speedup at large scale"""
        print(f"\n{'='*70}")
        print("LARGE SCALE PARALLEL SPEEDUP TEST (5,000 files)")
        print(f"{'='*70}\n")
        
        results = {}
        
        # Test 1: Single-threaded baseline
        print("[1/5] Single-threaded baseline...", end='', flush=True)
        processor1 = EnhancedParallelProcessor(
            num_workers=1,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        start = time.time()
        result1 = processor1.process_files(self.files, enable_sorting=True)
        results['single_thread'] = time.time() - start
        print(f" {results['single_thread']:.2f}s")
        
        # Test 2: Threading with 4 workers
        print("[2/5] Threading (4 workers)...", end='', flush=True)
        processor2 = EnhancedParallelProcessor(
            num_workers=4,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        start = time.time()
        result2 = processor2.process_files(self.files, enable_sorting=True)
        results['threading_4'] = time.time() - start
        print(f" {results['threading_4']:.2f}s")
        
        # Test 3: Threading with 8 workers
        print("[3/5] Threading (8 workers)...", end='', flush=True)
        processor3 = EnhancedParallelProcessor(
            num_workers=8,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        start = time.time()
        result3 = processor3.process_files(self.files, enable_sorting=True)
        results['threading_8'] = time.time() - start
        print(f" {results['threading_8']:.2f}s")
        
        # Test 4: Multiprocessing with 4 workers
        print("[4/5] Multiprocessing (4 workers)...", end='', flush=True)
        processor4 = MultiprocessParallelProcessor(
            num_workers=4,
            mount_point=self.test_dir,
            enable_monitoring=False
        )
        start = time.time()
        result4 = processor4.process_files(self.files, enable_sorting=True)
        results['multiprocess_4'] = time.time() - start
        print(f" {results['multiprocess_4']:.2f}s")
        
        # Test 5: Multiprocessing with 8 workers
        print("[5/5] Multiprocessing (8 workers)...", end='', flush=True)
        processor5 = MultiprocessParallelProcessor(
            num_workers=8,
            mount_point=self.test_dir,
            enable_monitoring=False
        )
        start = time.time()
        result5 = processor5.process_files(self.files, enable_sorting=True)
        results['multiprocess_8'] = time.time() - start
        print(f" {results['multiprocess_8']:.2f}s")
        
        # Print detailed results
        print(f"\n{'='*70}")
        print("RESULTS (with 1ms delay per file)")
        print(f"{'='*70}\n")
        
        baseline = results['single_thread']
        
        print(f"{'Method':<30} {'Time':>10} {'Speedup':>10} {'Efficiency':>12} {'Files/s':>10}")
        print("-" * 80)
        
        for name, elapsed in sorted(results.items(), key=lambda x: x[1]):
            speedup = baseline / elapsed
            throughput = len(self.files) / elapsed
            
            # Calculate efficiency
            if 'single' in name:
                efficiency = 100.0
                workers = 1
            elif '4' in name:
                efficiency = (speedup / 4) * 100
                workers = 4
            else:
                efficiency = (speedup / 8) * 100
                workers = 8
            
            if speedup >= 3.5:
                marker = "🚀"
            elif speedup >= 2.0:
                marker = "✅"
            elif speedup >= 1.5:
                marker = "✓"
            else:
                marker = "⚠️"
            
            print(f"{marker} {name:<28} {elapsed:>8.2f}s  {speedup:>8.2f}x  {efficiency:>10.1f}%  {throughput:>9.1f}")
        
        print(f"{'='*70}\n")
        
        # Calculate key metrics
        threading_4_speedup = baseline / results['threading_4']
        threading_8_speedup = baseline / results['threading_8']
        mp4_speedup = baseline / results['multiprocess_4']
        mp8_speedup = baseline / results['multiprocess_8']
        
        print("SCALING ANALYSIS:")
        print(f"  Threading (4 workers):         {threading_4_speedup:>5.2f}x speedup ({(threading_4_speedup/4)*100:.1f}% efficiency)")
        print(f"  Threading (8 workers):         {threading_8_speedup:>5.2f}x speedup ({(threading_8_speedup/8)*100:.1f}% efficiency)")
        print(f"  Multiprocessing (4 workers):   {mp4_speedup:>5.2f}x speedup ({(mp4_speedup/4)*100:.1f}% efficiency)")
        print(f"  Multiprocessing (8 workers):   {mp8_speedup:>5.2f}x speedup ({(mp8_speedup/8)*100:.1f}% efficiency)")
        print()
        
        # Interpretation
        if mp4_speedup >= 3.5:
            print("🎉 EXCELLENT: Near-linear scaling with multiprocessing!")
        elif mp4_speedup >= 2.5:
            print("✅ GREAT: Strong parallel speedup achieved!")
        elif mp4_speedup >= 1.8:
            print("✓ GOOD: Significant speedup with parallel processing")
        else:
            print("⚠️ Moderate speedup - overhead still significant")
        
        print()
        print("CONCLUSION:")
        print(f"  At scale ({len(self.files)} files), with realistic I/O delays:")
        print(f"  - Threading shows {threading_4_speedup:.1f}x speedup (GIL still impacts)")
        print(f"  - Multiprocessing shows {mp4_speedup:.1f}x speedup (no GIL!)")
        print(f"  - Best result: {min(results.values()):.2f}s vs {baseline:.2f}s baseline")
        print()
        
        best_speedup = max([threading_4_speedup, threading_8_speedup, mp4_speedup, mp8_speedup])
        print(f"  Maximum speedup achieved: {best_speedup:.2f}x")
        print(f"  Time saved: {baseline - min(results.values()):.2f}s")
        print(f"  Improvement: {((baseline - min(results.values())) / baseline * 100):.1f}% faster")
        
        # Verify correctness
        self.assertEqual(result1['stats']['successful'], 5000)
        self.assertEqual(result2['stats']['successful'], 5000)
        self.assertEqual(result3['stats']['successful'], 5000)
        self.assertEqual(result4['stats']['successful'], 5000)
        self.assertEqual(result5['stats']['successful'], 5000)
        
        # Assert that we see speedup at this scale
        self.assertGreater(threading_4_speedup, 1.5,
                          f"Threading (4 workers) should show speedup at scale (got {threading_4_speedup:.2f}x)")
        self.assertGreater(mp4_speedup, 2.0,
                          f"Multiprocessing (4 workers) should show good speedup (got {mp4_speedup:.2f}x)")


if __name__ == '__main__':
    unittest.main(verbosity=2)
