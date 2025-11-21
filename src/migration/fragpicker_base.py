#!/usr/bin/env python3
"""
FragPicker Base Module
Shared functionality for both in-place and out-of-place defragmentation
"""

import os
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Callable
from contextlib import contextmanager

# Constants
BLOCK_SIZE = 4096
PROGRESS_REPORT_INTERVAL = 100
DEFAULT_MOUNT_POINT = "/mnt"
DEFAULT_ANALYSIS_DIR = "../analysis"
FILESYSTEM_BLOCK_SIZE = 4096

# Try to import parallel analyzer
PARALLEL_AVAILABLE = False
try:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../analysis'))
    from parallel_analyzer.fiemap import FiemapAnalyzer
    from parallel_analyzer.inode_mapper import build_inode_map
    PARALLEL_AVAILABLE = True
except ImportError:
    pass


class FragPickerConfig:
    """Configuration for FragPicker operations"""
    
    def __init__(self, 
                 mount_point: str = DEFAULT_MOUNT_POINT,
                 analysis_dir: str = DEFAULT_ANALYSIS_DIR,
                 use_fiemap: Optional[bool] = None,
                 progress_interval: int = PROGRESS_REPORT_INTERVAL):
        self.mount_point = mount_point
        self.analysis_dir = Path(analysis_dir)
        self.progress_interval = progress_interval
        
        # Auto-detect FIEMAP availability if not specified
        if use_fiemap is None:
            self.use_fiemap = PARALLEL_AVAILABLE
        else:
            self.use_fiemap = use_fiemap and PARALLEL_AVAILABLE
        
        self.filelist_path = self.analysis_dir / "filelist.txt"
        self.frag_degree_path = self.analysis_dir / "frag_degree.txt"


class ExtentRange:
    """Represents a file extent range"""
    
    def __init__(self, start: int, end: int):
        self.start = start
        self.end = end
    
    def contains(self, other_start: int, other_end: int) -> bool:
        """Check if this extent contains another range"""
        return self.start <= other_start and self.end >= other_end
    
    def overlaps(self, other_start: int, other_end: int) -> bool:
        """Check if this extent overlaps with another range"""
        return not (self.end < other_start or self.start > other_end)
    
    def __repr__(self):
        return f"ExtentRange({self.start}, {self.end})"


class TargetRange:
    """Represents a target defragmentation range"""
    
    def __init__(self, start: int, end: int):
        self.start = start
        self.end = end
    
    @classmethod
    def from_line(cls, line: str) -> Optional['TargetRange']:
        """Parse target range from file line"""
        if not line or not line.strip():
            return None
        
        parts = line.strip().split()
        if len(parts) < 2:
            return None
        
        try:
            start = int(parts[0])
            end = int(parts[1])
            return cls(start, end)
        except ValueError:
            return None
    
    def __repr__(self):
        return f"TargetRange({self.start}, {self.end})"


class FragPickerBase:
    """Base class for FragPicker defragmentation"""
    
    def __init__(self, config: FragPickerConfig, defrag_func: Callable):
        """
        Initialize FragPicker base
        
        Args:
            config: Configuration object
            defrag_func: Function to perform defragmentation
                        Signature: defrag_func(file_obj, start: int, end: int)
        """
        self.config = config
        self.defrag_func = defrag_func
        self.fiemap_analyzer: Optional[FiemapAnalyzer] = None
        self.inode_map: Optional[Dict[str, str]] = None
        self.stats = {
            'total_files': 0,
            'processed': 0,
            'errors': 0,
            'skipped': 0
        }
    
    def initialize(self):
        """Initialize FIEMAP and inode mapping if available"""
        if self.config.use_fiemap:
            print("Using FIEMAP ioctl for extent detection (fast)")
            self.fiemap_analyzer = FiemapAnalyzer()
            
            # Build inode map for fast lookup
            print("Building inode map...")
            self.inode_map = build_inode_map(self.config.mount_point, verbose=False)
            print(f"Inode map built: {len(self.inode_map)} files")
        else:
            print("Using filefrag subprocess (traditional method)")
        
        print()
    
    def get_extent_ranges_fiemap(self, filepath: str) -> List[ExtentRange]:
        """Get extent ranges using FIEMAP ioctl"""
        if not self.fiemap_analyzer:
            return []
        
        try:
            extents = self.fiemap_analyzer.get_extents(filepath)
            if not extents:
                return []
            
            ranges = []
            for ext in extents:
                start = ext['logical']
                end = ext['logical'] + ext['length'] - 1
                ranges.append(ExtentRange(start, end))
            
            return ranges
        except Exception as e:
            print(f"Warning: FIEMAP failed for {filepath}: {e}")
            return []
    
    def get_extent_ranges_filefrag(self, filepath: str) -> List[ExtentRange]:
        """Get extent ranges using filefrag (traditional method)"""
        frag_degree_path = self.config.frag_degree_path
        
        try:
            # Run filefrag
            with open(frag_degree_path, "w+") as filefrag_f:
                subprocess.check_call(
                    ["filefrag", "-v", filepath],
                    stdout=filefrag_f,
                    stderr=subprocess.DEVNULL
                )
            
            # Remove header lines using sed
            subprocess.check_call(
                ["sed", "-i", "1,3d", str(frag_degree_path)],
                stderr=subprocess.DEVNULL
            )
            subprocess.check_call(
                ["sed", "-i", "$d", str(frag_degree_path)],
                stderr=subprocess.DEVNULL
            )
            
            # Parse results
            ranges = []
            current_end = -1
            
            with open(frag_degree_path, "r") as filefrag_f:
                for line in filefrag_f:
                    parts = line.split(':')
                    if len(parts) < 4:
                        continue
                    
                    try:
                        length = int(parts[3]) * FILESYSTEM_BLOCK_SIZE
                        current_start = current_end + 1
                        current_end = current_start + length - 1
                        ranges.append(ExtentRange(current_start, current_end))
                    except (ValueError, IndexError):
                        continue
            
            return ranges
            
        except subprocess.CalledProcessError as e:
            print(f"Warning: filefrag failed for {filepath}: {e}")
            return []
        except Exception as e:
            print(f"Warning: Error parsing filefrag output for {filepath}: {e}")
            return []
    
    def get_extent_ranges(self, filepath: str) -> List[ExtentRange]:
        """Get extent ranges using best available method"""
        if self.config.use_fiemap and self.fiemap_analyzer:
            return self.get_extent_ranges_fiemap(filepath)
        else:
            return self.get_extent_ranges_filefrag(filepath)
    
    def get_filepath_from_inode(self, inode: str) -> Optional[str]:
        """Get filepath from inode using fastest available method"""
        # Fast lookup using inode map
        if self.inode_map and inode in self.inode_map:
            return self.inode_map[inode]
        
        # Fallback to traditional find
        try:
            filepath_bytes = subprocess.check_output(
                ["find", self.config.mount_point, "-inum", inode],
                stderr=subprocess.DEVNULL
            )
            filepath = filepath_bytes.decode('ascii').strip()
            return filepath if filepath else None
        except subprocess.CalledProcessError:
            return None
    
    @contextmanager
    def open_file_safe(self, filepath: str, mode: str = "rb+"):
        """Context manager for safely opening files"""
        f = None
        try:
            f = open(filepath, mode)
            yield f
            f.flush()
            os.fsync(f.fileno())
        except Exception as e:
            if f:
                try:
                    f.flush()
                    os.fsync(f.fileno())
                except:
                    pass
            raise
        finally:
            if f:
                f.close()
    
    def should_defragment(self, extent: ExtentRange, target: TargetRange) -> bool:
        """
        Determine if a target range should be defragmented based on extent
        
        Matches original logic: defrag if extent starts at or before target start,
        ends before target end, but ends after target start.
        
        This means the extent partially overlaps with the target from the beginning,
        but doesn't fully contain it.
        
        Args:
            extent: Current file extent
            target: Target range that needs to be contiguous
        
        Returns:
            True if defragmentation is needed
        """
        # Original condition: currentStart <= startRange and currentEnd < endRange and currentEnd > startRange
        return (extent.start <= target.start and 
                extent.end < target.end and 
                extent.end > target.start)
    
    def process_file(self, inode: str, filepath: str) -> bool:
        """
        Process a single file for defragmentation
        
        Args:
            inode: File inode number
            filepath: Path to the file
        
        Returns:
            True if processing succeeded, False otherwise
        """
        try:
            # Get extent ranges
            extent_ranges = self.get_extent_ranges(filepath)
            if not extent_ranges:
                self.stats['skipped'] += 1
                return False
            
            # Open target file and range file
            sorted_file_path = self.config.analysis_dir / f"{inode}.sorted"
            
            if not sorted_file_path.exists():
                self.stats['skipped'] += 1
                return False
            
            with self.open_file_safe(filepath) as target_file:
                with open(sorted_file_path, "r") as range_file:
                    # Read first target range
                    target_line = range_file.readline()
                    if not target_line:
                        self.stats['skipped'] += 1
                        return True
                    
                    target = TargetRange.from_line(target_line)
                    if not target:
                        self.stats['skipped'] += 1
                        return True
                    
                    # Check each extent against target ranges
                    # This matches the original logic: for each extent, check all targets
                    for extent in extent_ranges:
                        while target:
                            # If extent fully contains target, target is already contiguous
                            if extent.contains(target.start, target.end):
                                target_line = range_file.readline()
                                target = TargetRange.from_line(target_line) if target_line else None
                                continue
                            
                            # If extent ends before target starts, move to next extent
                            if extent.end < target.start:
                                break
                            
                            # Check if defragmentation is needed
                            # (extent partially overlaps from start but doesn't fully contain target)
                            if self.should_defragment(extent, target):
                                self.defrag_func(target_file, target.start, target.end)
                            
                            # Move to next target range
                            target_line = range_file.readline()
                            target = TargetRange.from_line(target_line) if target_line else None
            
            return True
            
        except FileNotFoundError:
            print(f"Warning: File not found: {filepath}")
            self.stats['skipped'] += 1
            return False
        except PermissionError:
            print(f"Warning: Permission denied: {filepath}")
            self.stats['skipped'] += 1
            return False
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
            self.stats['errors'] += 1
            return False
    
    def run(self):
        """Main defragmentation loop"""
        print("=" * 60)
        
        # Initialize
        self.initialize()
        
        # Read file list
        if not self.config.filelist_path.exists():
            print(f"Error: File list not found: {self.config.filelist_path}")
            return
        
        with open(self.config.filelist_path, "r") as filelist_f:
            filename_lines = filelist_f.readlines()
        
        self.stats['total_files'] = len(filename_lines)
        
        # Process each file
        for line_num, filename_line in enumerate(filename_lines, 1):
            line = filename_line.strip()
            if not line:
                continue
            
            parts = line.split()
            if not parts:
                continue
            
            inode = parts[0]
            
            # Get filepath
            filepath = self.get_filepath_from_inode(inode)
            if not filepath or not os.path.exists(filepath):
                self.stats['skipped'] += 1
                continue
            
            # Process file
            if self.process_file(inode, filepath):
                self.stats['processed'] += 1
            
            # Progress reporting
            if filename_line and line_num % self.config.progress_interval == 0:
                print(f"Processing: {self.stats['processed']}/{self.stats['total_files']} files", 
                      flush=True)
        
        # Print summary
        print(f"\nDefragmentation complete: {self.stats['processed']}/{self.stats['total_files']} files processed")
        print(f"  Skipped: {self.stats['skipped']}")
        print(f"  Errors: {self.stats['errors']}")
        
        # Print FIEMAP statistics if used
        if self.config.use_fiemap and self.fiemap_analyzer:
            print("\nFIEMAP Statistics:")
            stats = self.fiemap_analyzer.get_stats()
            print(f"  Files analyzed: {stats['files_analyzed']}")
            print(f"  IOCTL calls: {stats['ioctl_calls']}")
            print(f"  Errors: {stats['errors']}")

