#!/usr/bin/env python3
"""
FragPicker_IP.py - Refactored version using base class
In-place update filesystem defragmentation (e.g., ext4)

Enhancements:
- FIEMAP ioctl for fast extent detection
- Batch inode mapping
- Parallel-ready architecture
- Proper resource management with context managers
- Configurable paths
- Better error handling
- Block allocation for in-place updates
"""

import os
import sys
import fallocate
import fcntl

# Allow both standalone execution and module import
try:
    from fragpicker_base import FragPickerBase, FragPickerConfig
except ImportError:
    # Fallback for relative import
    from .fragpicker_base import FragPickerBase, FragPickerConfig


def reallocation_func(target_file, start: int, size: int):
    """
    Allocate blocks for in-place update filesystem
    
    This creates a hole and then allocates new contiguous blocks,
    forcing the filesystem to move the data.
    
    Args:
        target_file: File object
        start: Start byte offset
        size: Size in bytes
    """
    try:
        # Punch hole (create gap) while keeping file size
        fallocate.fallocate(
            target_file, 
            start, 
            size,
            mode=fallocate.FALLOC_FL_PUNCH_HOLE | fallocate.FALLOC_FL_KEEP_SIZE
        )
        # Allocate new contiguous blocks
        fallocate.fallocate(target_file, start, size, mode=0)
    except Exception as e:
        raise IOError(f"Block allocation failed at offset {start}: {e}")


def defrag_func_inplace(target_file, start: int, end: int):
    """
    Defragment file region with block reallocation (in-place)
    
    For in-place filesystems like ext4, we need to:
    1. Lock the file region
    2. Read the data
    3. Reallocate blocks (punch hole + allocate)
    4. Write the data back
    5. Unlock the file region
    
    Args:
        target_file: File object opened in rb+ mode
        start: Start byte offset
        end: End byte offset (inclusive)
    """
    size = end - start + 1
    
    try:
        # Lock file region for exclusive access
        fcntl.lockf(target_file, fcntl.LOCK_EX, size, start, 0)
        
        # Read data
        target_file.seek(start, 0)
        data = target_file.read(size)
        
        if len(data) < size:
            raise IOError(f"Read incomplete data: expected {size} bytes, got {len(data)}")
        
        # Reallocate blocks (creates hole, then allocates new contiguous blocks)
        reallocation_func(target_file, start, size)
        
        # Write data back
        target_file.seek(start, 0)
        target_file.write(data)
        
    finally:
        # Always unlock, even on error
        try:
            fcntl.lockf(target_file, fcntl.LOCK_UN, size, start, 0)
        except:
            pass  # Ignore unlock errors


def main():
    """Main defragmentation entry point"""
    # Configuration can be customized
    config = FragPickerConfig(
        mount_point=os.getenv("FRAGPICKER_MOUNT_POINT", "/mnt"),
        analysis_dir=os.getenv("FRAGPICKER_ANALYSIS_DIR", "../analysis"),
        use_fiemap=None,  # Auto-detect
        progress_interval=100
    )
    
    # Create FragPicker instance
    fragpicker = FragPickerBase(config, defrag_func_inplace)
    
    # Run defragmentation
    fragpicker.run()


if __name__ == "__main__":
    main()

