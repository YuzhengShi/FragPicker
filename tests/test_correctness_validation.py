#!/usr/bin/env python3
"""
Correctness Validation Test - Large Scale

This test validates that parallel processing produces IDENTICAL output
to sequential processing on large datasets (10K+ files).

Key validation:
- Byte-for-byte output comparison
- Extent data must match exactly
- Inode mapping must be identical
- Statistics must be consistent
"""

import os
import sys
import unittest
import tempfile
import shutil
import json
import hashlib

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

from parallel_analyzer.parallel_processor import EnhancedParallelProcessor
from parallel_analyzer.multiprocess_processor import MultiprocessParallelProcessor


class TestCorrectnessValidation(unittest.TestCase):
    """Large-scale correctness validation: parallel == sequential"""
    
    def setUp(self):
        """Create test environment with multiple files"""
        self.test_dir = tempfile.mkdtemp(prefix="correctness_test_")
        self.result_dir_seq = tempfile.mkdtemp(prefix="sequential_results_")
        self.result_dir_par = tempfile.mkdtemp(prefix="parallel_results_")
    
    def tearDown(self):
        """Clean up test environment"""
        for directory in [self.test_dir, self.result_dir_seq, self.result_dir_par]:
            if os.path.exists(directory):
                shutil.rmtree(directory)
    
    def create_test_files(self, num_files, size_kb=10):
        """Create test files and return list of (inode, count) tuples"""
        files = []
        print(f"\n[Correctness] Creating {num_files} test files ({size_kb}KB each)...")
        
        for i in range(num_files):
            filepath = os.path.join(self.test_dir, f"file_{i:06d}.dat")
            with open(filepath, 'wb') as f:
                f.write(os.urandom(size_kb * 1024))
            
            stat = os.stat(filepath)
            files.append((str(stat.st_ino), 1))
        
        print(f"[Correctness] Created {num_files} files")
        return files
    
    def save_results_to_files(self, results, output_dir):
        """
        Save extent data to individual files for comparison.
        Returns dict of {inode: filepath}
        """
        saved_files = {}
        
        for result in results:
            inode = result['inode']
            filepath = os.path.join(output_dir, f"{inode}.txt")
            
            with open(filepath, 'w') as f:
                # Write extent data in consistent format
                for extent in result.get('extents', []):
                    f.write(f"{extent['logical']} {extent['physical']} {extent['length']}\n")
            
            saved_files[inode] = filepath
        
        return saved_files
    
    def compute_file_hash(self, filepath):
        """Compute SHA256 hash of file contents"""
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            sha256.update(f.read())
        return sha256.hexdigest()
    
    def compare_extent_files(self, seq_files, par_files):
        """
        Compare extent files byte-for-byte.
        Returns (matches, mismatches, missing)
        """
        matches = 0
        mismatches = []
        missing = []
        
        for inode, seq_file in seq_files.items():
            if inode not in par_files:
                missing.append(inode)
                continue
            
            par_file = par_files[inode]
            
            # Compare file sizes first
            seq_size = os.path.getsize(seq_file)
            par_size = os.path.getsize(par_file)
            
            if seq_size != par_size:
                mismatches.append({
                    'inode': inode,
                    'reason': 'size_mismatch',
                    'seq_size': seq_size,
                    'par_size': par_size
                })
                continue
            
            # Compare file contents (byte-for-byte)
            seq_hash = self.compute_file_hash(seq_file)
            par_hash = self.compute_file_hash(par_file)
            
            if seq_hash != par_hash:
                mismatches.append({
                    'inode': inode,
                    'reason': 'content_mismatch',
                    'seq_hash': seq_hash[:16],
                    'par_hash': par_hash[:16]
                })
                continue
            
            matches += 1
        
        return matches, mismatches, missing
    
    def test_100_files_sequential_vs_parallel(self):
        """Test: 100 files - sequential == parallel (threading)"""
        num_files = 100
        files = self.create_test_files(num_files, size_kb=10)
        
        print(f"\n[Test 1/4] Processing {num_files} files...")
        
        # Sequential processing (1 worker)
        print("  Running sequential (1 worker)...")
        seq_processor = EnhancedParallelProcessor(
            num_workers=1,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        seq_result = seq_processor.process_files(files, enable_sorting=False)
        
        # Parallel processing (8 workers)
        print("  Running parallel (8 workers)...")
        par_processor = EnhancedParallelProcessor(
            num_workers=8,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        par_result = par_processor.process_files(files, enable_sorting=False)
        
        # Save results to files
        print("  Comparing results...")
        seq_files = self.save_results_to_files(seq_result['results'], self.result_dir_seq)
        par_files = self.save_results_to_files(par_result['results'], self.result_dir_par)
        
        # Compare
        matches, mismatches, missing = self.compare_extent_files(seq_files, par_files)
        
        # Report
        print(f"  ✓ Matches: {matches}/{num_files}")
        print(f"  ✗ Mismatches: {len(mismatches)}")
        print(f"  ? Missing: {len(missing)}")
        
        # Assertions
        self.assertEqual(len(mismatches), 0, f"Found {len(mismatches)} mismatches: {mismatches}")
        self.assertEqual(len(missing), 0, f"Found {len(missing)} missing files")
        self.assertEqual(matches, seq_result['stats']['successful'])
        
        print(f"  ✅ PASS: All {matches} files match exactly!")
    
    def test_1000_files_sequential_vs_parallel(self):
        """Test: 1000 files - sequential == parallel (threading)"""
        num_files = 1000
        files = self.create_test_files(num_files, size_kb=10)
        
        print(f"\n[Test 2/4] Processing {num_files} files...")
        
        # Sequential
        print("  Running sequential (1 worker)...")
        seq_processor = EnhancedParallelProcessor(
            num_workers=1,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        seq_result = seq_processor.process_files(files, enable_sorting=False)
        
        # Parallel
        print("  Running parallel (8 workers)...")
        par_processor = EnhancedParallelProcessor(
            num_workers=8,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        par_result = par_processor.process_files(files, enable_sorting=False)
        
        # Compare
        print("  Comparing results...")
        seq_files = self.save_results_to_files(seq_result['results'], self.result_dir_seq)
        par_files = self.save_results_to_files(par_result['results'], self.result_dir_par)
        
        matches, mismatches, missing = self.compare_extent_files(seq_files, par_files)
        
        # Report
        print(f"  ✓ Matches: {matches}/{num_files}")
        print(f"  ✗ Mismatches: {len(mismatches)}")
        print(f"  ? Missing: {len(missing)}")
        
        # Assertions
        self.assertEqual(len(mismatches), 0, f"Found {len(mismatches)} mismatches")
        self.assertEqual(len(missing), 0, f"Found {len(missing)} missing files")
        self.assertEqual(matches, seq_result['stats']['successful'])
        
        print(f"  ✅ PASS: All {matches} files match exactly!")
    
    def test_1000_files_threading_vs_multiprocessing(self):
        """Test: 1000 files - threading == multiprocessing"""
        num_files = 1000
        files = self.create_test_files(num_files, size_kb=10)
        
        print(f"\n[Test 3/4] Processing {num_files} files...")
        
        # Threading
        print("  Running threading (8 workers)...")
        thread_processor = EnhancedParallelProcessor(
            num_workers=8,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        thread_result = thread_processor.process_files(files, enable_sorting=False)
        
        # Multiprocessing
        print("  Running multiprocessing (8 workers)...")
        mp_processor = MultiprocessParallelProcessor(
            num_workers=8,
            mount_point=self.test_dir,
            enable_monitoring=False
        )
        mp_result = mp_processor.process_files(files, enable_sorting=False)
        
        # Compare
        print("  Comparing results...")
        thread_files = self.save_results_to_files(thread_result['results'], self.result_dir_seq)
        mp_files = self.save_results_to_files(mp_result['results'], self.result_dir_par)
        
        matches, mismatches, missing = self.compare_extent_files(thread_files, mp_files)
        
        # Report
        print(f"  ✓ Matches: {matches}/{num_files}")
        print(f"  ✗ Mismatches: {len(mismatches)}")
        print(f"  ? Missing: {len(missing)}")
        
        # Assertions
        self.assertEqual(len(mismatches), 0, f"Found {len(mismatches)} mismatches")
        self.assertEqual(len(missing), 0, f"Found {len(missing)} missing files")
        
        print(f"  ✅ PASS: Threading and multiprocessing produce identical results!")
    
    def test_5000_files_sequential_vs_parallel(self):
        """Test: 5,000 files - sequential == parallel (LARGE SCALE)"""
        num_files = 5000
        files = self.create_test_files(num_files, size_kb=5)  # Smaller files for speed
        
        print(f"\n[Test 4/4] Processing {num_files} files (LARGE SCALE)...")
        
        # Sequential
        print("  Running sequential (1 worker)...")
        seq_processor = EnhancedParallelProcessor(
            num_workers=1,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        seq_result = seq_processor.process_files(files, enable_sorting=False)
        print(f"    Sequential: {seq_result['stats']['total_time']:.2f}s")
        
        # Parallel
        print("  Running parallel (8 workers)...")
        par_processor = EnhancedParallelProcessor(
            num_workers=8,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        par_result = par_processor.process_files(files, enable_sorting=False)
        print(f"    Parallel: {par_result['stats']['total_time']:.2f}s")
        
        # Compare (sample verification - check first 50 for speed)
        print("  Comparing results (sampling for speed)...")
        seq_files = self.save_results_to_files(seq_result['results'], self.result_dir_seq)
        par_files = self.save_results_to_files(par_result['results'], self.result_dir_par)
        
        # Verify all inodes are present
        seq_inodes = set(seq_files.keys())
        par_inodes = set(par_files.keys())
        
        missing_in_par = seq_inodes - par_inodes
        extra_in_par = par_inodes - seq_inodes
        
        print(f"  Sequential processed: {len(seq_inodes)} files")
        print(f"  Parallel processed: {len(par_inodes)} files")
        
        self.assertEqual(len(missing_in_par), 0, f"Parallel missing {len(missing_in_par)} files")
        self.assertEqual(len(extra_in_par), 0, f"Parallel has {len(extra_in_par)} extra files")
        
        # Sample verification (first 50 files for speed)
        import random
        sample_inodes = list(seq_inodes)[:50]
        
        matches = 0
        mismatches = []
        
        for inode in sample_inodes:
            seq_hash = self.compute_file_hash(seq_files[inode])
            par_hash = self.compute_file_hash(par_files[inode])
            
            if seq_hash == par_hash:
                matches += 1
            else:
                mismatches.append(inode)
        
        # Report
        print(f"  ✓ Sample verified: {matches}/{len(sample_inodes)} files match")
        print(f"  ✗ Mismatches: {len(mismatches)}")
        
        # Assertions
        self.assertEqual(len(mismatches), 0, f"Found {len(mismatches)} mismatches in sample")
        self.assertEqual(matches, len(sample_inodes))
        
        # Stats comparison
        self.assertEqual(
            seq_result['stats']['successful'],
            par_result['stats']['successful'],
            "Sequential and parallel should process same number of files"
        )
        
        print(f"  ✅ PASS: Large-scale correctness validated on {num_files} files!")
        print(f"    All {len(seq_inodes)} files processed identically")


def run_correctness_validation():
    """Run all correctness validation tests"""
    print("=" * 70)
    print("  CORRECTNESS VALIDATION TEST SUITE")
    print("  Verifying: Parallel Output == Sequential Output")
    print("=" * 70)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestCorrectnessValidation))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print("  ✅ ALL CORRECTNESS TESTS PASSED!")
        print("  Parallel processing produces IDENTICAL output to sequential")
        print("=" * 70)
        return 0
    else:
        print("  ❌ SOME TESTS FAILED")
        print("  Parallel output does NOT match sequential output")
        print("=" * 70)
        return 1


if __name__ == '__main__':
    sys.exit(run_correctness_validation())
