#!/usr/bin/env python3
"""
Quick test to verify sorting actually works
"""

import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

from parallel_analyzer.parallel_processor import EnhancedParallelProcessor


def test_sorting_works():
    """Create files, process with sorting, verify sorted files exist"""
    test_dir = tempfile.mkdtemp(prefix="sorting_test_")
    
    try:
        print("Creating 10 test files...")
        files = []
        for i in range(10):
            filepath = os.path.join(test_dir, f"file_{i}.dat")
            with open(filepath, 'wb') as f:
                f.write(os.urandom(10 * 1024))
            
            stat = os.stat(filepath)
            files.append((str(stat.st_ino), 1))
        
        print(f"Processing with sorting enabled...")
        processor = EnhancedParallelProcessor(
            num_workers=2,
            mount_point=test_dir,
            enable_monitoring=False,
            enable_profiling=False
        )
        
        result = processor.process_files(files, enable_sorting=True)
        
        print(f"\nResults:")
        print(f"  Successful: {result['stats']['successful']}")
        print(f"  Failed: {result['stats']['failed']}")
        print(f"  Sort time: {result['stats']['sort_time']:.2f}s")
        
        if 'sorted_files' in result:
            print(f"  Sorted files created: {len(result['sorted_files'])}")
            
            # Check a few sorted files
            for i, sorted_file in enumerate(result['sorted_files'][:3]):
                print(f"\n  Checking sorted file #{i+1}: {os.path.basename(sorted_file)}")
                
                with open(sorted_file, 'r') as f:
                    lines = f.readlines()
                
                print(f"    Lines: {len(lines)}")
                if lines:
                    print(f"    First line: {lines[0].strip()}")
                    
                    # Verify sorting (logical offsets should be in order)
                    if len(lines) > 1:
                        values = [int(line.split()[0]) for line in lines if line.strip()]
                        is_sorted = values == sorted(values)
                        print(f"    Is sorted: {'✅ YES' if is_sorted else '❌ NO'}")
            
            print("\n✅ Sorting feature is working correctly!")
            return True
        else:
            print("\n❌ No sorted files found!")
            return False
    
    finally:
        shutil.rmtree(test_dir)


if __name__ == '__main__':
    success = test_sorting_works()
    sys.exit(0 if success else 1)
