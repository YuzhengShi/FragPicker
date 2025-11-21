#!/usr/bin/env python3
"""
Edge case testing for robust error handling
Tests unusual and boundary conditions
"""

import unittest
import tempfile
import os
import sys
import stat as stat_module

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

from parallel_analyzer.fiemap import FiemapAnalyzer, FileType
from parallel_analyzer.inode_mapper import build_inode_map


class TestFileTypes(unittest.TestCase):
    """Test handling of different file types"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.analyzer = FiemapAnalyzer()
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir)
    
    def test_empty_file(self):
        """Test empty file (0 bytes)"""
        filepath = os.path.join(self.test_dir, "empty.dat")
        open(filepath, 'w').close()
        
        extents = self.analyzer.get_extents(filepath)
        
        self.assertIsNotNone(extents)
        self.assertEqual(len(extents), 0, "Empty file should have 0 extents")
    
    def test_very_small_file(self):
        """Test very small file (1 byte)"""
        filepath = os.path.join(self.test_dir, "tiny.dat")
        with open(filepath, 'wb') as f:
            f.write(b'x')
        
        extents = self.analyzer.get_extents(filepath)
        
        self.assertIsNotNone(extents)
        self.assertGreaterEqual(len(extents), 1, "1-byte file should have >=1 extent")
    
    def test_sparse_file(self):
        """Test sparse file with holes"""
        filepath = os.path.join(self.test_dir, "sparse.dat")
        
        # Create sparse file
        with open(filepath, 'wb') as f:
            f.write(b'data')
            f.seek(1024 * 1024)  # Seek 1MB ahead
            f.write(b'more data')
        
        extents = self.analyzer.get_extents(filepath)
        
        self.assertIsNotNone(extents)
        # Sparse file may have multiple extents
    
    def test_symlink(self):
        """Test symbolic link"""
        target = os.path.join(self.test_dir, "target.dat")
        link = os.path.join(self.test_dir, "link.dat")
        
        with open(target, 'wb') as f:
            f.write(b'target file')
        
        os.symlink(target, link)
        
        file_type = self.analyzer.get_file_type(link)
        
        # Should detect as symlink or regular file (depends on os.stat vs os.lstat)
        self.assertIn(file_type, [FileType.SYMLINK, FileType.REGULAR])
    
    def test_directory(self):
        """Test that directories are rejected"""
        dirpath = os.path.join(self.test_dir, "subdir")
        os.makedirs(dirpath)
        
        extents = self.analyzer.get_extents(dirpath)
        
        # Should return None for directories
        self.assertIsNone(extents)
    
    def test_nonexistent_file(self):
        """Test non-existent file"""
        filepath = os.path.join(self.test_dir, "does_not_exist.dat")
        
        extents = self.analyzer.get_extents(filepath)
        
        self.assertIsNone(extents, "Should return None for non-existent file")


class TestFilePermissions(unittest.TestCase):
    """Test permission handling"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.analyzer = FiemapAnalyzer()
    
    def tearDown(self):
        # Restore permissions before cleanup
        for root, dirs, files in os.walk(self.test_dir):
            for d in dirs:
                try:
                    os.chmod(os.path.join(root, d), 0o755)
                except:
                    pass
            for f in files:
                try:
                    os.chmod(os.path.join(root, f), 0o644)
                except:
                    pass
        
        import shutil
        shutil.rmtree(self.test_dir)
    
    def test_no_read_permission(self):
        """Test file with no read permission"""
        filepath = os.path.join(self.test_dir, "noperm.dat")
        with open(filepath, 'wb') as f:
            f.write(b'test data')
        
        # Remove read permission
        os.chmod(filepath, 0o000)
        
        extents = self.analyzer.get_extents(filepath)
        
        # Restore permission for cleanup
        os.chmod(filepath, 0o644)
        
        # Should handle gracefully (return None)
        self.assertIsNone(extents)
    
    def test_write_only_file(self):
        """Test write-only file"""
        filepath = os.path.join(self.test_dir, "writeonly.dat")
        with open(filepath, 'wb') as f:
            f.write(b'test data')
        
        # Make write-only
        os.chmod(filepath, 0o200)
        
        extents = self.analyzer.get_extents(filepath)
        
        # Restore for cleanup
        os.chmod(filepath, 0o644)
        
        # Should fail to open
        self.assertIsNone(extents)


class TestFilenameEdgeCases(unittest.TestCase):
    """Test unusual filenames"""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.analyzer = FiemapAnalyzer()
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir)
    
    def test_unicode_filename(self):
        """Test Unicode filename"""
        filepath = os.path.join(self.test_dir, "文件.dat")
        with open(filepath, 'wb') as f:
            f.write(b'unicode filename')
        
        extents = self.analyzer.get_extents(filepath)
        
        self.assertIsNotNone(extents, "Should handle Unicode filenames")
    
    def test_spaces_in_filename(self):
        """Test filename with spaces"""
        filepath = os.path.join(self.test_dir, "file with spaces.dat")
        with open(filepath, 'wb') as f:
            f.write(b'spaces in name')
        
        extents = self.analyzer.get_extents(filepath)
        
        self.assertIsNotNone(extents)
    
    def test_special_characters(self):
        """Test special characters in filename"""
        special_chars = ['file(1).dat', 'file[test].dat', 'file$test.dat']
        
        for filename in special_chars:
            filepath = os.path.join(self.test_dir, filename)
            with open(filepath, 'wb') as f:
                f.write(b'special chars')
            
            extents = self.analyzer.get_extents(filepath)
            
            self.assertIsNotNone(extents, f"Should handle {filename}")


class TestInodeMapperEdgeCases(unittest.TestCase):
    """Test inode mapper edge cases"""
    
    def test_empty_directory(self):
        """Test empty directory"""
        test_dir = tempfile.mkdtemp()
        
        try:
            inode_map = build_inode_map(test_dir, verbose=False)
            
            self.assertEqual(len(inode_map), 0, "Empty directory should return empty map")
        finally:
            os.rmdir(test_dir)
    
    def test_deep_nesting(self):
        """Test deeply nested directories"""
        test_dir = tempfile.mkdtemp()
        
        try:
            # Create deeply nested structure
            deep_path = test_dir
            for i in range(10):
                deep_path = os.path.join(deep_path, f"level{i}")
                os.makedirs(deep_path)
            
            # Create file at deepest level
            filepath = os.path.join(deep_path, "deep.dat")
            with open(filepath, 'wb') as f:
                f.write(b'deep file')
            
            inode_map = build_inode_map(test_dir, verbose=False)
            
            stat = os.stat(filepath)
            self.assertIn(str(stat.st_ino), inode_map)
        
        finally:
            import shutil
            shutil.rmtree(test_dir)
    
    def test_nonexistent_mount_point(self):
        """Test non-existent mount point"""
        inode_map = build_inode_map("/nonexistent/path", verbose=False)
        
        self.assertEqual(len(inode_map), 0, "Should return empty map for invalid path")


class TestConcurrency(unittest.TestCase):
    """Test concurrent access scenarios"""
    
    def test_concurrent_file_access(self):
        """Test concurrent access to same file"""
        import threading
        
        test_dir = tempfile.mkdtemp()
        filepath = os.path.join(test_dir, "concurrent.dat")
        
        with open(filepath, 'wb') as f:
            f.write(os.urandom(10240))
        
        try:
            results = []
            
            def analyze_file():
                analyzer = FiemapAnalyzer()
                extents = analyzer.get_extents(filepath)
                results.append(extents)
            
            # Run 10 concurrent analyses
            threads = []
            for _ in range(10):
                t = threading.Thread(target=analyze_file)
                t.start()
                threads.append(t)
            
            for t in threads:
                t.join()
            
            # All should succeed
            self.assertEqual(len(results), 10)
            self.assertTrue(all(r is not None for r in results))
            
            # All should return same extent count
            extent_counts = [len(r) for r in results]
            self.assertEqual(len(set(extent_counts)), 1, 
                           "All concurrent reads should return same extent count")
        
        finally:
            import shutil
            shutil.rmtree(test_dir)


if __name__ == '__main__':
    unittest.main(verbosity=2)