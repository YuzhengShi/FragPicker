#!/usr/bin/env python3
"""
End-to-end integration tests
Tests complete workflows with realistic scenarios
"""

import unittest
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

from parallel_analyzer.parallel_processor import EnhancedParallelProcessor
from parallel_analyzer.multiprocess_processor import MultiprocessParallelProcessor


class TestEndToEndIntegration(unittest.TestCase):
    """Test complete workflows from start to finish"""
    
    def setUp(self):
        """Create test environment"""
        self.test_dir = tempfile.mkdtemp(prefix="e2e_test_")
    
    def tearDown(self):
        """Clean up test environment"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_nested_directory_structure(self):
        """Test with deep directory hierarchies"""
        # Create nested structure: /a/b/c/d/e/
        current_dir = self.test_dir
        files = []
        
        for level in range(5):
            current_dir = os.path.join(current_dir, f"level_{level}")
            os.makedirs(current_dir, exist_ok=True)
            
            # Create 10 files at each level
            for i in range(10):
                filepath = os.path.join(current_dir, f"file_{i}.dat")
                with open(filepath, 'wb') as f:
                    f.write(os.urandom(10 * 1024))
                
                stat = os.stat(filepath)
                files.append((str(stat.st_ino), 1))
        
        # Process with parallel processor
        processor = EnhancedParallelProcessor(
            num_workers=4,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        
        result = processor.process_files(files, enable_sorting=True)  # Re-enabled sorting!
        
        # Verify all files processed
        self.assertEqual(result['stats']['successful'], 50)
        self.assertEqual(result['stats']['failed'], 0)
        
        # Verify sorting was done
        self.assertIn('sorted_files', result)
        self.assertEqual(len(result['sorted_files']), 50)
    
    def test_mixed_file_sizes(self):
        """Test with varying file sizes (1KB to 10MB)"""
        files = []
        sizes_kb = [1, 10, 100, 1000, 10000]  # 1KB to 10MB
        
        for size_kb in sizes_kb:
            for i in range(5):
                filepath = os.path.join(self.test_dir, f"file_{size_kb}kb_{i}.dat")
                with open(filepath, 'wb') as f:
                    f.write(os.urandom(size_kb * 1024))
                
                stat = os.stat(filepath)
                files.append((str(stat.st_ino), 1))
        
        # Process with multiprocessing and sorting
        processor = MultiprocessParallelProcessor(
            num_workers=4,
            mount_point=self.test_dir,
            enable_monitoring=False
        )
        
        result = processor.process_files(files, enable_sorting=True)  # Re-enabled sorting!
        
        # Verify all files processed regardless of size
        self.assertEqual(result['stats']['successful'], 25)
        self.assertEqual(result['stats']['failed'], 0)
        
        # Verify sorting was done
        self.assertIn('sorted_files', result)
        self.assertEqual(len(result['sorted_files']), 25)
    
    def test_empty_files(self):
        """Test handling of empty files"""
        files = []
        
        # Create 10 empty files
        for i in range(10):
            filepath = os.path.join(self.test_dir, f"empty_{i}.dat")
            open(filepath, 'w').close()  # Create empty file
            
            stat = os.stat(filepath)
            files.append((str(stat.st_ino), 1))
        
        processor = EnhancedParallelProcessor(
            num_workers=2,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        
        result = processor.process_files(files, enable_sorting=True)
        
        # Empty files should still be processed
        total = result['stats']['successful'] + result['stats']['failed']
        self.assertEqual(total, 10)
    
    def test_large_batch_processing(self):
        """Test processing 1000 files in batches"""
        files = []
        num_files = 1000  # Reduced from 5000 for faster testing
        
        print(f"\nCreating {num_files} files...")
        for i in range(num_files):
            filepath = os.path.join(self.test_dir, f"file_{i:05d}.dat")
            with open(filepath, 'wb') as f:
                f.write(os.urandom(5 * 1024))  # 5KB each
            
            stat = os.stat(filepath)
            files.append((str(stat.st_ino), 1))
        
        print(f"Processing {num_files} files with 8 workers...")
        processor = EnhancedParallelProcessor(
            num_workers=8,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        
        result = processor.process_files(files, enable_sorting=True)  # Re-enabled sorting!
        
        # Verify all files processed
        self.assertEqual(result['stats']['successful'], num_files)
        self.assertEqual(result['stats']['failed'], 0)
        
        # Verify sorting was done
        self.assertIn('sorted_files', result)
        self.assertEqual(len(result['sorted_files']), num_files)
        
        print(f"Successfully processed {num_files} files!")
        print(f"Throughput: {result['stats']['files_per_second']:.1f} files/sec")
        print(f"Sort time: {result['stats']['sort_time']:.2f}s")
    
    def test_concurrent_processors(self):
        """Test multiple processors running simultaneously"""
        files = []
        
        # Create test files
        for i in range(100):
            filepath = os.path.join(self.test_dir, f"file_{i}.dat")
            with open(filepath, 'wb') as f:
                f.write(os.urandom(10 * 1024))
            
            stat = os.stat(filepath)
            files.append((str(stat.st_ino), 1))
        
        # Run two processors simultaneously
        processor1 = EnhancedParallelProcessor(
            num_workers=4,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        
        processor2 = EnhancedParallelProcessor(
            num_workers=4,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        
        import threading
        
        results = {}
        
        def run_processor(name, processor):
            results[name] = processor.process_files(files, enable_sorting=True)
        
        thread1 = threading.Thread(target=run_processor, args=("proc1", processor1))
        thread2 = threading.Thread(target=run_processor, args=("proc2", processor2))
        
        thread1.start()
        thread2.start()
        
        thread1.join()
        thread2.join()
        
        # Both processors should complete successfully
        self.assertEqual(results['proc1']['stats']['successful'], 100)
        self.assertEqual(results['proc2']['stats']['successful'], 100)


class TestErrorRecovery(unittest.TestCase):
    """Test error handling and recovery"""
    
    def setUp(self):
        """Create test environment"""
        self.test_dir = tempfile.mkdtemp(prefix="error_test_")
    
    def tearDown(self):
        """Clean up test environment"""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_missing_files(self):
        """Test handling of files deleted during processing"""
        files = []
        
        # Create files
        for i in range(50):
            filepath = os.path.join(self.test_dir, f"file_{i}.dat")
            with open(filepath, 'wb') as f:
                f.write(os.urandom(10 * 1024))
            
            stat = os.stat(filepath)
            files.append((str(stat.st_ino), 1))
        
        # Delete some files before processing
        for i in range(10, 20):
            filepath = os.path.join(self.test_dir, f"file_{i}.dat")
            os.remove(filepath)
        
        processor = EnhancedParallelProcessor(
            num_workers=4,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        
        result = processor.process_files(files, enable_sorting=True)
        
        # Should handle missing files gracefully
        total = result['stats']['successful'] + result['stats']['failed']
        self.assertEqual(total, 50)
        # 40 files exist, 10 deleted
        self.assertGreaterEqual(result['stats']['failed'], 10)
    
    def test_invalid_inodes(self):
        """Test handling of invalid inode numbers"""
        files = [
            ('999999999', 1),  # Non-existent inode
            ('invalid', 1),    # Invalid format
            ('0', 1),          # Invalid inode 0
        ]
        
        processor = EnhancedParallelProcessor(
            num_workers=2,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        
        result = processor.process_files(files, enable_sorting=True)
        
        # Should handle invalid inodes gracefully
        self.assertEqual(result['stats']['failed'], 3)
    
    def test_empty_file_list(self):
        """Test handling of empty input"""
        processor = EnhancedParallelProcessor(
            num_workers=4,
            mount_point=self.test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        
        result = processor.process_files([], enable_sorting=True)
        
        # Should handle empty list gracefully
        self.assertEqual(result['stats']['successful'], 0)
        self.assertEqual(result['stats']['failed'], 0)


def run_integration_tests():
    """Run all integration tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestEndToEndIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorRecovery))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_integration_tests())
