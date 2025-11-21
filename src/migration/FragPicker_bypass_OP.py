#!/usr/bin/env python3
"""
FragPicker Bypass Version - Out-of-Place Filesystems
Bypass version for testing without actual migration.

This version performs the same analysis but skips actual data migration.
"""

import sys
import subprocess
import os
from pathlib import Path
from typing import Optional


# Constants
BLOCK_SIZE = 4096
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
        print("Usage: FragPicker_bypass_OP.py <filepath> <defragsize>")
        print("  filepath: Path to file to analyze")
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
    """Parse filefrag output to extract fragment sizes"""
    try:
        with open(filefrag_path, "r") as f:
            lines = f.readlines()
        
        if len(lines) < 4:
            return None
        
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


def analyze_file(filepath: str, defragsize_kb: int) -> bool:
    """
    Analyze file fragmentation (bypass version - no actual migration)
    
    Args:
        filepath: Path to file to analyze
        defragsize_kb: Defragmentation size in KB
    
    Returns:
        True if successful, False otherwise
    """
    analysis_dir = Path("../analysis")
    frag_degree_path = analysis_dir / "frag_degree"
    defragsize_bytes = defragsize_kb * KB
    
    try:
        # Ensure analysis directory exists
        analysis_dir.mkdir(parents=True, exist_ok=True)
        
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
        
        # Analyze without migrating (bypass version)
        print(f"[BYPASS] Analyzing {filepath}")
        print(f"[BYPASS] Fragments: {len(fragment_sizes)}")
        print(f"[BYPASS] Defrag size: {defragsize_kb} KB")
        
        # Calculate what would be migrated
        total_bytes = sum(frag * BLOCK_SIZE for frag in fragment_sizes)
        print(f"[BYPASS] Total size: {total_bytes / KB:.2f} KB")
        print(f"[BYPASS] Would migrate in chunks of {defragsize_kb} KB")
        
        # In bypass mode, we just report what would be done
        with open(filepath, "rb+") as target_file:
            bufsize = 0
            need_write = False
            
            for fragsize in fragment_sizes:
                bufsize += fragsize * BLOCK_SIZE
                
                while bufsize >= defragsize_bytes:
                    if need_write:
                        # In bypass mode, just seek without reading/writing
                        target_file.seek(defragsize_bytes, 1)
                        need_write = False
                        target_file.seek(-defragsize_bytes, 1)
                    
                    target_file.seek(defragsize_bytes, 1)
                    bufsize -= defragsize_bytes
                
                if bufsize > 0:
                    need_write = True
            
            if need_write and bufsize > 0:
                target_file.seek(bufsize, 1)
        
        print(f"[BYPASS] Analysis complete (no data migrated)")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"Error: filefrag failed: {e}")
        return False
    except IOError as e:
        print(f"Error: I/O error: {e}")
        return False
    except PermissionError as e:
        print(f"Error: Permission denied: {e}")
        return False
    except Exception as e:
        print(f"Error: Unexpected error: {e}")
        return False
    finally:
        # Cleanup temporary file
        if frag_degree_path.exists():
            frag_degree_path.unlink()


def main():
    """Main entry point"""
    try:
        filepath, defragsize = validate_args()
        
        if analyze_file(filepath, defragsize):
            sys.exit(0)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
