#!/usr/bin/env python3
"""
I/O Request Merging Module
Merges overlapping I/O requests from trace files into contiguous windows.

This module processes per-file trace data and merges overlapping I/O requests
to create consolidated I/O windows with request counts.
"""

import sys
import subprocess
import os
from typing import List, Tuple, Optional
from pathlib import Path


class MergeWindow:
    """Represents a merge window for I/O requests"""
    
    def __init__(self, start: int, end: int, count: int):
        self.start = start
        self.end = end
        self.count = count
    
    def __repr__(self):
        return f"MergeWindow(start={self.start}, end={self.end}, count={self.count})"


def parse_trace_line(line: str) -> Optional[Tuple[int, int, int]]:
    """
    Parse a trace line into (start, end, count) tuple
    
    Args:
        line: Trace line in format "start end count"
    
    Returns:
        Tuple of (start, end, count) or None if parsing fails
    """
    if not line or not line.strip():
        return None
    
    parts = line.strip().split()
    if len(parts) < 3:
        return None
    
    try:
        start = int(parts[0])
        end = int(parts[1])
        count = int(parts[2])
        return (start, end, count)
    except (ValueError, IndexError):
        return None


def merge_io_requests(trace_lines: List[str]) -> List[MergeWindow]:
    """
    Merge overlapping I/O requests into contiguous windows
    
    Algorithm:
    1. Process requests in order
    2. If request doesn't overlap current window, finalize window and start new one
    3. If request is within window, increment count
    4. If request overlaps but extends window, extend window and increment count
    
    Args:
        trace_lines: List of trace lines in format "start end count"
    
    Returns:
        List of MergeWindow objects
    """
    windows = []
    current_window: Optional[MergeWindow] = None
    
    for line in trace_lines:
        parsed = parse_trace_line(line)
        if parsed is None:
            continue
        
        start, end, count = parsed
        
        # If no current window, start a new one
        if current_window is None:
            current_window = MergeWindow(start, end, count)
            continue
        
        # If request doesn't overlap, finalize current window and start new one
        if current_window.end < start:
            windows.append(current_window)
            current_window = MergeWindow(start, end, count)
            continue
        
        # Request overlaps with current window
        # If request is fully within window, just increment count
        if current_window.end >= end:
            current_window.count += count
        else:
            # Request extends window, extend window and increment count
            current_window.count += count
            current_window.end = end
    
    # Finalize last window
    if current_window is not None:
        windows.append(current_window)
    
    return windows


def process_file(inode: str, input_dir: Path = Path("."), output_dir: Path = Path(".")) -> bool:
    """
    Process a single file's trace data and merge I/O requests
    
    Args:
        inode: File inode (used as filename)
        input_dir: Directory containing input trace files
        output_dir: Directory for output merged files
    
    Returns:
        True if successful, False otherwise
    """
    input_file = input_dir / f"{inode}.txt"
    output_file = output_dir / f"{inode}.merged"
    temp_file = output_dir / "tmp.txt"
    
    try:
        # Read input trace file
        if not input_file.exists():
            print(f"Warning: Trace file not found: {input_file}")
            return False
        
        with open(input_file, "r") as trace_file:
            trace_lines = trace_file.readlines()
        
        # Merge I/O requests
        windows = merge_io_requests(trace_lines)
        
        if not windows:
            print(f"Warning: No valid I/O requests found in {input_file}")
            return False
        
        # Write merged results to temporary file
        with open(temp_file, "w") as result_file:
            for window in windows:
                result_file.write(f"{window.start} {window.end} {window.count}\n")
        
        # Atomic move to final location
        temp_file.replace(output_file)
        
        return True
        
    except IOError as e:
        print(f"Error processing {inode}: I/O error - {e}")
        return False
    except Exception as e:
        print(f"Error processing {inode}: {e}")
        return False


def main():
    """Main entry point"""
    filelist_path = Path("./filelist.txt")
    
    if not filelist_path.exists():
        print(f"Error: File list not found: {filelist_path}")
        sys.exit(1)
    
    try:
        # Read file list
        with open(filelist_path, "r") as filelist_f:
            lines = filelist_f.readlines()
        
        processed = 0
        failed = 0
        
        # Process each file
        for line_num, line in enumerate(lines, 1):
            if not line.strip():
                continue
            
            parts = line.strip().split()
            if not parts:
                continue
            
            inode = parts[0]
            
            # Validate inode is numeric
            try:
                int(inode)
            except ValueError:
                print(f"Warning: Skipping invalid inode on line {line_num}: {inode}")
                continue
            
            if process_file(inode):
                processed += 1
            else:
                failed += 1
            
            # Progress reporting
            if line_num % 100 == 0:
                print(f"Processed: {processed}/{line_num} files", flush=True)
        
        print(f"\nMerge complete: {processed} files processed, {failed} failed")
        
        if failed > 0:
            sys.exit(1)
            
    except IOError as e:
        print(f"Error: Failed to read file list: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: Unexpected error - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
