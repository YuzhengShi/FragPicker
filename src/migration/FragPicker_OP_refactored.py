#!/usr/bin/env python3
"""
FragPicker_OP.py - Refactored version using base class
Out-of-place update filesystem defragmentation (e.g., F2FS, Btrfs)

Enhancements:
- FIEMAP ioctl for fast extent detection
- Batch inode mapping
- Parallel-ready architecture
- Proper resource management with context managers
- Configurable paths
- Better error handling
"""

import os
import sys

# Allow both standalone execution and module import
try:
    from fragpicker_base import FragPickerBase, FragPickerConfig
except ImportError:
    # Fallback for relative import
    from .fragpicker_base import FragPickerBase, FragPickerConfig


def defrag_func_outplace(target_file, start: int, end: int):
    """
    Defragment file region (out-of-place)
    
    For out-of-place filesystems, we simply read and rewrite the data.
    The filesystem handles reallocation automatically.
    
    Args:
        target_file: File object opened in rb+ mode
        start: Start byte offset
        end: End byte offset (inclusive)
    """
    target_file.seek(start, 0)
    size = end - start + 1
    data = target_file.read(size)
    
    if len(data) < size:
        # Handle partial read
        raise IOError(f"Read incomplete data: expected {size} bytes, got {len(data)}")
    
    target_file.seek(start, 0)
    target_file.write(data)


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
    fragpicker = FragPickerBase(config, defrag_func_outplace)
    
    # Run defragmentation
    fragpicker.run()


if __name__ == "__main__":
    main()

