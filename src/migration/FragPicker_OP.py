#!/usr/bin/env python3
"""
FragPicker_OP.py - Enhanced with parallel FIEMAP support
Out-of-place update filesystem defragmentation (e.g., F2FS, Btrfs)

Enhancements:
- FIEMAP ioctl for fast extent detection
- Batch inode mapping
- Parallel-ready architecture
"""

import sys
import subprocess
import os

# Try to import parallel analyzer
PARALLEL_AVAILABLE = False
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../analysis'))
    from parallel_analyzer.fiemap import FiemapAnalyzer
    from parallel_analyzer.inode_mapper import build_inode_map
    PARALLEL_AVAILABLE = True
except ImportError:
    print("Warning: Parallel analyzer not available, using traditional method")


# Data Migration without block allocation
def defrag_func(targetFile_f, start, end):
    """
    Defragment file region (out-of-place)
    
    Args:
        targetFile_f: File object
        start: Start offset
        end: End offset
    """
    targetFile_f.seek(start, 0)
    size = end - start + 1
    data = targetFile_f.read(size)
    targetFile_f.seek(start, 0)
    targetFile_f.write(data)


def get_extent_ranges_fiemap(filepath, fiemap_analyzer):
    """
    Get extent ranges using FIEMAP ioctl
    
    Args:
        filepath: Path to file
        fiemap_analyzer: FiemapAnalyzer instance
    
    Returns:
        List of (start_byte, end_byte) tuples
    """
    extents = fiemap_analyzer.get_extents(filepath)
    
    if not extents:
        return []
    
    ranges = []
    for ext in extents:
        start = ext['logical']
        end = ext['logical'] + ext['length'] - 1
        ranges.append((start, end))
    
    return ranges


def get_extent_ranges_filefrag(filepath):
    """
    Get extent ranges using filefrag (traditional method)
    
    Args:
        filepath: Path to file
    
    Returns:
        List of (start_byte, end_byte) tuples
    """
    filefrag_f = open("../analysis/frag_degree.txt", "w+")
    subprocess.check_call(["filefrag", "-v", filepath], stdout=filefrag_f)
    subprocess.check_call(["sed", "-i", "1,3d", "../analysis/frag_degree.txt"])
    subprocess.check_call(["sed", "-i", "$d", "../analysis/frag_degree.txt"])
    filefrag_f.close()
    
    filefrag_f = open("../analysis/frag_degree.txt", "r+")
    filefrag_f.seek(0)
    filefrag_lines = filefrag_f.readlines()
    filefrag_f.close()
    
    ranges = []
    currentEnd = -1
    
    for line in filefrag_lines:
        currentStart = currentEnd + 1
        length = int(line.split(':')[3]) * 4096
        currentEnd = currentStart + length - 1
        ranges.append((currentStart, currentEnd))
    
    return ranges


def main():
    """Main defragmentation logic"""
    print("FragPicker OP (Out-of-place) - Enhanced Version")
    print("=" * 60)
    
    # Initialize FIEMAP if available
    use_fiemap = PARALLEL_AVAILABLE
    fiemap_analyzer = None
    inode_map = None
    
    if use_fiemap:
        print("Using FIEMAP ioctl for extent detection (fast)")
        fiemap_analyzer = FiemapAnalyzer()
        
        # Build inode map for fast lookup
        print("Building inode map...")
        inode_map = build_inode_map("/mnt", verbose=False)
        print(f"Inode map built: {len(inode_map)} files")
    else:
        print("Using filefrag subprocess (traditional method)")
    
    print()
    
    # Open the file list to defrag
    filelist_f = open("../analysis/filelist.txt", "r+")
    filename_lines = filelist_f.readlines()
    
    total_files = len(filename_lines)
    processed = 0
    
    for filename_line in filename_lines:
        if str(filename_line.split()[0]) == '':
            continue
        
        inode = filename_line.split()[0]
        
        # Get filepath (fast lookup if inode map available)
        if inode_map and inode in inode_map:
            filename = inode_map[inode]
        else:
            # Fallback to traditional find
            try:
                filename = subprocess.check_output(
                    ["find", "/mnt", "-inum", inode]
                ).decode('ascii').strip()
            except subprocess.CalledProcessError:
                print(f"Warning: Could not find file with inode {inode}")
                continue
        
        if not filename:
            continue
        
        processed += 1
        if processed % 100 == 0:
            print(f"Processing: {processed}/{total_files} files", flush=True)
        
        try:
            # Get extent ranges (FIEMAP or filefrag)
            if use_fiemap and fiemap_analyzer:
                extent_ranges = get_extent_ranges_fiemap(filename, fiemap_analyzer)
            else:
                extent_ranges = get_extent_ranges_filefrag(filename)
            
            if not extent_ranges:
                continue
            
            # Open target file
            targetFile_f = open(filename, "rb+")
            targetRange_f = open("../analysis/" + inode + ".sorted", "r")
            
            targetRange = targetRange_f.readline()
            if not targetRange:
                targetFile_f.close()
                targetRange_f.close()
                continue
            
            startRange = int(targetRange.split()[0])
            endRange = int(targetRange.split()[1])
            
            # Check fragmentation and defrag
            for currentStart, currentEnd in extent_ranges:
                while targetRange != '':
                    if currentStart <= startRange and currentEnd >= endRange:
                        targetRange = targetRange_f.readline()
                        if targetRange == '':
                            break
                        startRange = int(targetRange.split()[0])
                        endRange = int(targetRange.split()[1])
                    
                    elif currentEnd <= startRange:
                        break
                    
                    elif currentStart <= startRange and currentEnd < endRange and currentEnd > startRange:
                        # Defragmentation needed
                        defrag_func(targetFile_f, startRange, endRange)
                        
                        targetRange = targetRange_f.readline()
                        if targetRange == '':
                            break
                        
                        startRange = int(targetRange.split()[0])
                        endRange = int(targetRange.split()[1])
            
            targetFile_f.flush()
            os.fsync(targetFile_f.fileno())
            targetFile_f.close()
            targetRange_f.close()
        
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            continue
    
    print(f"\nDefragmentation complete: {processed}/{total_files} files processed")
    
    # Print FIEMAP statistics if used
    if use_fiemap and fiemap_analyzer:
        print("\nFIEMAP Statistics:")
        stats = fiemap_analyzer.get_stats()
        print(f"  Files analyzed: {stats['files_analyzed']}")
        print(f"  IOCTL calls: {stats['ioctl_calls']}")
        print(f"  Errors: {stats['errors']}")


if __name__ == "__main__":
    main()