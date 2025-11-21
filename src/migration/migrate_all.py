#!/usr/bin/env python3
"""
Full File Migration Tool
Performs migration of the entire file contents (conventional defragmentation).

This script reads file fragmentation information and migrates all data
to create a contiguous file layout.
"""

import sys
import subprocess
import os
from pathlib import Path
from typing import Optional


# Constants
BLOCK_SIZE = 4096  # Filesystem block size in bytes
KB = 1024


def validate_args() -> tuple[str, int]:
    """
    Validate and parse command-line arguments
    
    Returns:
        Tuple of (filepath, defragsize)
    
    Raises:
        SystemExit: If arguments are invalid
    """
    if len(sys.argv) < 3:
        print("Usage: migrate_all.py <filepath> <defragsize>")
        print("  filepath: Path to file to migrate")
        print("  defragsize: Defragmentation size in KB (must be positive)")
        sys.exit(1)
    
    filepath = sys.argv[1]
    
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
    
    if not os.path.isfile(filepath):
        print(f"Error: Not a regular file: {filepath}")
        sys.exit(1)
    
    try:
        defragsize = int(sys.argv[2])
        if defragsize <= 0:
            raise ValueError("defragsize must be positive")
    except ValueError as e:
        print(f"Error: Invalid defragsize '{sys.argv[2]}': {e}")
        sys.exit(1)
    
    return filepath, defragsize


def parse_filefrag_output(filefrag_path: Path) -> Optional[list[int]]:
    """
    Parse filefrag output to extract fragment sizes
    
    Args:
        filefrag_path: Path to filefrag output file
    
    Returns:
        List of fragment sizes in blocks, or None on error
    """
    try:
        with open(filefrag_path, "r") as f:
            lines = f.readlines()
        
        # Skip header lines (first 3 lines)
        if len(lines) < 4:
            return None
        
        # Parse fragment sizes
        fragment_sizes = []
        for line in lines[3:-1]:  # Skip header and last line
            parts = line.split(':')
            if len(parts) >= 4:
                try:
                    frag_size = int(parts[3])
                    fragment_sizes.append(frag_size)
                except (ValueError, IndexError):
                    continue
        
        return fragment_sizes
        
    except IOError as e:
        print(f"Error reading filefrag output: {e}")
        return None
    except Exception as e:
        print(f"Error parsing filefrag output: {e}")
        return None


def migrate_file(filepath: str, defragsize_kb: int) -> bool:
    """
    Migrate entire file contents
    
    Args:
        filepath: Path to file to migrate
        defragsize_kb: Defragmentation size in KB
    
    Returns:
        True if successful, False otherwise
    """
    frag_degree_path = Path("frag_degree")
    defragsize_bytes = defragsize_kb * KB
    
    try:
        # Run filefrag to get fragmentation information
        with open(frag_degree_path, "w+") as frag_degree:
            subprocess.check_call(
                ["filefrag", "-v", filepath],
                stdout=frag_degree,
                stderr=subprocess.DEVNULL
            )
        
        # Parse fragmentation information
        fragment_sizes = parse_filefrag_output(frag_degree_path)
        if fragment_sizes is None or not fragment_sizes:
            print(f"Warning: Could not parse fragmentation info for {filepath}")
            return False
        
        # Perform migration
        with open(filepath, "rb+") as target_file:
            bufsize = 0  # Buffer size in blocks * block_size
            need_write = False
            
            for fragsize in fragment_sizes:
                # Convert fragment size from blocks to bytes
                bufsize += fragsize * BLOCK_SIZE
                
                # If buffer is large enough, perform defragmentation
                while bufsize >= defragsize_bytes:
                    if need_write:
                        # Read data
                        data = target_file.read(defragsize_bytes)
                        read_size = len(data)
                        
                        if read_size == 0:
                            break
                        
                        # Seek back and write
                        target_file.seek(-read_size, 1)
                        target_file.write(data)
                        need_write = False
                        
                        # Seek back to starting position
                        target_file.seek(-defragsize_bytes, 1)
                    
                    # Move forward
                    target_file.seek(defragsize_bytes, 1)
                    bufsize -= defragsize_bytes
                
                # Mark that we need to write remaining buffer
                if bufsize > 0:
                    need_write = True
            
            # Handle remaining buffer
            if need_write and bufsize > 0:
                data = target_file.read(bufsize)
                read_size = len(data)
                
                if read_size > 0:
                    target_file.seek(-read_size, 1)
                    target_file.write(data)
            
            # Ensure data is written to disk
            target_file.flush()
            os.fsync(target_file.fileno())
        
        # Cleanup temporary file
        if frag_degree_path.exists():
            frag_degree_path.unlink()
        
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Error: filefrag failed: {e}")
        return False
    except IOError as e:
        print(f"Error: I/O error during migration: {e}")
        return False
    except PermissionError as e:
        print(f"Error: Permission denied: {e}")
        return False
    except Exception as e:
        print(f"Error: Unexpected error during migration: {e}")
        return False


def main():
    """Main entry point"""
    try:
        filepath, defragsize = validate_args()
        
        if migrate_file(filepath, defragsize):
            print(f"Successfully migrated: {filepath}")
            sys.exit(0)
        else:
            print(f"Failed to migrate: {filepath}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
