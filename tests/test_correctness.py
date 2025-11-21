#!/usr/bin/env python3
"""
Correctness validation: parallel vs sequential processing
Ensures parallel optimization produces identical results
"""

import unittest
import tempfile
import os
import subprocess
import sys
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

from parallel_analyzer.inode_mapper import build_inode_map, lookup_filepath


class TestCorrectness(unittest.TestCase):
    """Validate parallel implementation correctness"""
    
    @classmethod
    def setUpClass(cls):
        """Create test corpus"""
        cls.test_dir = tempfile.mkdtemp()
        cls.test_files = []
        
        # Create test files
        for i in range(50):
            filepath = os.path.join(cls.test_dir, f"test_{i:03d}.dat")
            with open(filepath, 'wb') as f:
                f.write(os.urandom(10 * 1024))  # 10KB each
            cls.test_files.append(filepath)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up"""
        shutil.rmtree(cls.test_dir)
    
    def test_inode_mapping_completeness(self):
        """Test that inode map includes all files"""
        inode_map = build_inode_map(self.test_dir, verbose=False)
        
        # Get actual inodes
        actual_inodes = set()
        for filepath in self.test_files:
            stat = os.stat(filepath)
            actual_inodes.add(str(stat.st_ino))
        
        # Get mapped inodes
        mapped_inodes = set(inode_map.keys())
        
        # Should include all our test files
        self.assertTrue(
            actual_inodes.issubset(mapped_inodes),
            "Inode map missing some test files"
        )
    
    def test_inode_lookup_accuracy(self):
        """Test that inode lookup returns correct paths"""
        inode_map = build_inode_map(self.test_dir, verbose=False)
        
        for filepath in self.test_files:
            stat = os.stat(filepath)
            inode = str(stat.st_ino)
            
            looked_up_path = lookup_filepath(inode, inode_map)
            
            # Should return the correct path
            self.assertEqual(looked_up_path, filepath,
                           f"Inode {inode} mapped to wrong path")
    
    def test_parallel_vs_sequential_speed(self):
        """Test that parallel is faster than sequential (not equal)"""
        import time
        
        # Measure sequential lookup time
        seq_start = time.time()
        for filepath in self.test_files:
            stat = os.stat(filepath)
            inode = str(stat.st_ino)
            # Simulate sequential find (slow)
            result = subprocess.run(
                ['find', self.test_dir, '-inum', inode],
                capture_output=True,
                text=True
            )
        seq_time = time.time() - seq_start
        
        # Measure parallel lookup time
        par_start = time.time()
        inode_map = build_inode_map(self.test_dir, verbose=False)
        for filepath in self.test_files:
            stat = os.stat(filepath)
            inode = str(stat.st_ino)
            looked_up_path = lookup_filepath(inode, inode_map)
        par_time = time.time() - par_start
        
        # Parallel should be faster
        speedup = seq_time / par_time
        print(f"\nSpeedup: {speedup:.2f}x "
              f"(Sequential: {seq_time:.2f}s, Parallel: {par_time:.2f}s)")
        
        self.assertGreater(speedup, 2.0,
                          "Parallel should be at least 2x faster")


if __name__ == '__main__':
    unittest.main()