#!/usr/bin/env python3
"""
Test suite for FIEMAP implementation
Validates correctness against filefrag command
"""

import unittest
import tempfile
import os
import subprocess
import sys

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

from parallel_analyzer.fiemap import FiemapAnalyzer, compare_with_filefrag


class TestFiemap(unittest.TestCase):
    """Test FIEMAP ioctl implementation"""
    
    @classmethod
    def setUpClass(cls):
        """Create test files"""
        cls.test_dir = tempfile.mkdtemp()
        cls.test_files = []
        
        # Create various test files
        # Small file
        small_file = os.path.join(cls.test_dir, "small.dat")
        with open(small_file, 'wb') as f:
            f.write(os.urandom(4096))  # 4KB
        cls.test_files.append(small_file)
        
        # Medium file
        medium_file = os.path.join(cls.test_dir, "medium.dat")
        with open(medium_file, 'wb') as f:
            f.write(os.urandom(1024 * 1024))  # 1MB
        cls.test_files.append(medium_file)
        
        # Large file
        large_file = os.path.join(cls.test_dir, "large.dat")
        with open(large_file, 'wb') as f:
            f.write(os.urandom(10 * 1024 * 1024))  # 10MB
        cls.test_files.append(large_file)
        
        # Empty file
        empty_file = os.path.join(cls.test_dir, "empty.dat")
        open(empty_file, 'w').close()
        cls.test_files.append(empty_file)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test files"""
        import shutil
        shutil.rmtree(cls.test_dir)
    
    def test_basic_functionality(self):
        """Test that FIEMAP returns extent information"""
        analyzer = FiemapAnalyzer()
        
        for filepath in self.test_files:
            extents = analyzer.get_extents(filepath)
            
            # Should return a list (possibly empty for empty file)
            self.assertIsInstance(extents, list, 
                                f"FIEMAP failed for {filepath}")
    
    def test_empty_file(self):
        """Test FIEMAP on empty file"""
        analyzer = FiemapAnalyzer()
        empty_file = [f for f in self.test_files if 'empty' in f][0]
        
        extents = analyzer.get_extents(empty_file)
        
        # Empty file should have 0 extents
        self.assertEqual(len(extents), 0, 
                        "Empty file should have 0 extents")
    
    def test_extent_structure(self):
        """Test that extent dictionary has required fields"""
        analyzer = FiemapAnalyzer()
        
        # Use a non-empty file
        test_file = [f for f in self.test_files if 'medium' in f][0]
        extents = analyzer.get_extents(test_file)
        
        if len(extents) > 0:
            extent = extents[0]
            
            # Check required fields
            self.assertIn('logical', extent)
            self.assertIn('physical', extent)
            self.assertIn('length', extent)
            self.assertIn('flags', extent)
            
            # Check types
            self.assertIsInstance(extent['logical'], int)
            self.assertIsInstance(extent['physical'], int)
            self.assertIsInstance(extent['length'], int)
    
    def test_comparison_with_filefrag(self):
        """Test that FIEMAP matches filefrag output"""
        # Skip if filefrag not available
        try:
            # filefrag doesn't support --version, so just check if it exists
            result = subprocess.run(['which', 'filefrag'], 
                         capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.skipTest("filefrag command not available")
        
        for filepath in self.test_files:
            if os.path.getsize(filepath) == 0:
                continue  # Skip empty file
            
            comparison = compare_with_filefrag(filepath)
            
            # Extent counts should match
            self.assertEqual(
                comparison['fiemap_count'],
                comparison['filefrag_count'],
                f"Extent count mismatch for {filepath}: "
                f"FIEMAP={comparison['fiemap_count']}, "
                f"filefrag={comparison['filefrag_count']}"
            )
    
    def test_statistics(self):
        """Test that statistics are tracked correctly"""
        analyzer = FiemapAnalyzer()
        
        # Process some files
        for filepath in self.test_files[:3]:
            analyzer.get_extents(filepath)
        
        stats = analyzer.get_stats()
        
        # Check statistics
        self.assertEqual(stats['files_analyzed'], 3)
        self.assertGreaterEqual(stats['ioctl_calls'], 3)
        self.assertGreaterEqual(stats['total_extents'], 0)


if __name__ == '__main__':
    unittest.main()