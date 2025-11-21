#!/usr/bin/env python3
"""
Enhanced FIEMAP implementation with retry logic and error handling
Production-ready version with comprehensive error handling
"""

import ctypes
import os
import fcntl
import time
import errno
from typing import List, Dict, Optional, Tuple
from enum import Enum

from .config import get_config
from .logger import get_logger

logger = get_logger(__name__)

# Constants
FIEMAP_MAX_OFFSET = ctypes.c_uint64(-1).value
FIEMAP_EXTENT_LAST = 0x00000001
FIEMAP_EXTENT_UNKNOWN = 0x00000002
FIEMAP_EXTENT_DELALLOC = 0x00000004
FIEMAP_EXTENT_ENCODED = 0x00000008
FIEMAP_EXTENT_UNWRITTEN = 0x00000200


class FiemapError(Exception):
    """Base exception for FIEMAP operations"""
    pass


class FileTypeError(FiemapError):
    """File type not supported"""
    pass


class FilesystemError(FiemapError):
    """Filesystem doesn't support FIEMAP"""
    pass


class FileType(Enum):
    """Supported file types"""
    REGULAR = 1
    DIRECTORY = 2
    SYMLINK = 3
    BLOCK_DEVICE = 4
    CHAR_DEVICE = 5
    FIFO = 6
    SOCKET = 7
    UNKNOWN = 99


# C structures
class FiemapExtent(ctypes.Structure):
    _fields_ = [
        ("fe_logical", ctypes.c_uint64),
        ("fe_physical", ctypes.c_uint64),
        ("fe_length", ctypes.c_uint64),
        ("fe_reserved64", ctypes.c_uint64 * 2),
        ("fe_flags", ctypes.c_uint32),
        ("fe_reserved", ctypes.c_uint32 * 3),
    ]


class Fiemap(ctypes.Structure):
    _fields_ = [
        ("fm_start", ctypes.c_uint64),
        ("fm_length", ctypes.c_uint64),
        ("fm_flags", ctypes.c_uint32),
        ("fm_mapped_extents", ctypes.c_uint32),
        ("fm_extent_count", ctypes.c_uint32),
        ("fm_reserved", ctypes.c_uint32),
    ]


class FiemapRequest(ctypes.Structure):
    _fields_ = [
        ("fiemap", Fiemap),
        ("extents", FiemapExtent * 32)
    ]


class FiemapAnalyzer:
    """
    Enhanced FIEMAP analyzer with:
    - Retry logic for transient failures
    - File type detection
    - Comprehensive error handling
    - Performance statistics
    """
    
    FS_IOC_FIEMAP = 0xC020660B
    
    def __init__(self, config=None):
        self.config = config or get_config().fiemap
        self.stats = {
            'files_analyzed': 0,
            'total_extents': 0,
            'ioctl_calls': 0,
            'ioctl_retries': 0,
            'errors': 0,
            'by_error_type': {}
        }
    
    def get_file_type(self, filepath: str) -> FileType:
        """Detect file type"""
        try:
            stat = os.stat(filepath)
            mode = stat.st_mode
            
            import stat as stat_module
            if stat_module.S_ISREG(mode):
                return FileType.REGULAR
            elif stat_module.S_ISDIR(mode):
                return FileType.DIRECTORY
            elif stat_module.S_ISLNK(mode):
                return FileType.SYMLINK
            elif stat_module.S_ISBLK(mode):
                return FileType.BLOCK_DEVICE
            elif stat_module.S_ISCHR(mode):
                return FileType.CHAR_DEVICE
            elif stat_module.S_ISFIFO(mode):
                return FileType.FIFO
            elif stat_module.S_ISSOCK(mode):
                return FileType.SOCKET
            else:
                return FileType.UNKNOWN
        except OSError:
            return FileType.UNKNOWN
    
    def get_extents(self, filepath: str, validate: bool = True) -> Optional[List[Dict]]:
        """
        Get file extents with validation and error handling
        
        Args:
            filepath: Path to file
            validate: Validate file type before analysis
        
        Returns:
            List of extents or None on error
        """
        if validate:
            file_type = self.get_file_type(filepath)
            if file_type != FileType.REGULAR:
                logger.debug(f"Skipping {filepath}: not a regular file (type={file_type.name})")
                self._record_error("not_regular_file")
                return None
        
        try:
            fd = os.open(filepath, os.O_RDONLY)
            try:
                extents = self._get_extents_with_retry(fd, filepath)
                self.stats['files_analyzed'] += 1
                self.stats['total_extents'] += len(extents)
                return extents
            finally:
                os.close(fd)
        
        except OSError as e:
            self._record_error(f"os_error_{e.errno}")
            logger.debug(f"Failed to open {filepath}: {e}")
            return None
        except Exception as e:
            self._record_error("unexpected")
            logger.error(f"Unexpected error for {filepath}: {e}")
            return None
    
    def _get_extents_with_retry(self, fd: int, filepath: str) -> List[Dict]:
        """Get extents with retry logic"""
        for attempt in range(self.config.retry_attempts):
            try:
                return self._get_extents_fd(fd)
            except IOError as e:
                if e.errno == errno.EOPNOTSUPP:
                    # Filesystem doesn't support FIEMAP
                    raise FilesystemError(f"FIEMAP not supported for {filepath}")
                
                if attempt < self.config.retry_attempts - 1:
                    # Transient error, retry
                    self.stats['ioctl_retries'] += 1
                    logger.debug(f"FIEMAP retry {attempt+1} for {filepath}")
                    time.sleep(self.config.retry_delay_ms / 1000.0)
                else:
                    # Final attempt failed
                    raise
        
        return []
    
    def _get_extents_fd(self, fd: int) -> List[Dict]:
        """Internal: get all extents via file descriptor"""
        all_extents = []
        start_offset = 0
        iterations = 0
        max_iterations = 10000  # Safety limit
        
        while iterations < max_iterations:
            req = FiemapRequest()
            req.fiemap.fm_start = start_offset
            req.fiemap.fm_length = FIEMAP_MAX_OFFSET
            req.fiemap.fm_flags = 0
            req.fiemap.fm_extent_count = self.config.max_extents_per_call
            req.fiemap.fm_mapped_extents = 0
            
            fcntl.ioctl(fd, self.FS_IOC_FIEMAP, req)
            self.stats['ioctl_calls'] += 1
            
            num_extents = req.fiemap.fm_mapped_extents
            
            if num_extents == 0:
                break
            
            for i in range(num_extents):
                extent = req.extents[i]
                
                all_extents.append({
                    'logical': extent.fe_logical,
                    'physical': extent.fe_physical,
                    'length': extent.fe_length,
                    'flags': extent.fe_flags
                })
                
                if extent.fe_flags & FIEMAP_EXTENT_LAST:
                    return all_extents
            
            last_extent = req.extents[num_extents - 1]
            start_offset = last_extent.fe_logical + last_extent.fe_length
            iterations += 1
        
        if iterations >= max_iterations:
            logger.warning(f"FIEMAP reached max iterations ({max_iterations})")
        
        return all_extents
    
    def get_extent_ranges(self, filepath: str) -> Optional[List[Tuple[int, int]]]:
        """
        Get extent byte ranges for FragPicker compatibility
        
        Returns:
            List of (start, end) tuples
        """
        extents = self.get_extents(filepath)
        if extents is None:
            return None
        
        ranges = []
        for ext in extents:
            start = ext['logical']
            end = ext['logical'] + ext['length'] - 1
            ranges.append((start, end))
        
        return ranges
    
    def _record_error(self, error_type: str):
        """Record error statistics"""
        self.stats['errors'] += 1
        if error_type not in self.stats['by_error_type']:
            self.stats['by_error_type'][error_type] = 0
        self.stats['by_error_type'][error_type] += 1
    
    def get_stats(self) -> Dict:
        """Get comprehensive statistics"""
        stats = self.stats.copy()
        
        if stats['files_analyzed'] > 0:
            stats['avg_extents_per_file'] = stats['total_extents'] / stats['files_analyzed']
            stats['avg_ioctl_per_file'] = stats['ioctl_calls'] / stats['files_analyzed']
        
        if stats['ioctl_calls'] > 0:
            stats['retry_rate'] = stats['ioctl_retries'] / stats['ioctl_calls']
        
        return stats
    
    def print_stats(self):
        """Print formatted statistics"""
        stats = self.get_stats()
        
        print("\n" + "=" * 60)
        print("FIEMAP Statistics")
        print("=" * 60)
        print(f"Files analyzed:       {stats['files_analyzed']:,}")
        print(f"Total extents:        {stats['total_extents']:,}")
        print(f"IOCTL calls:          {stats['ioctl_calls']:,}")
        print(f"IOCTL retries:        {stats['ioctl_retries']}")
        print(f"Errors:               {stats['errors']}")
        
        if stats['files_analyzed'] > 0:
            print(f"Avg extents/file:     {stats['avg_extents_per_file']:.1f}")
            print(f"Avg ioctl/file:       {stats['avg_ioctl_per_file']:.1f}")
        
        if stats['by_error_type']:
            print("\nErrors by type:")
            for error_type, count in sorted(stats['by_error_type'].items()):
                print(f"  {error_type:20s}: {count}")
        
        print("=" * 60)


def compare_with_filefrag(filepath: str) -> Dict:
    """
    Compare FIEMAP output with filefrag command
    
    Args:
        filepath: Path to file to analyze
    
    Returns:
        Dictionary with comparison results:
        - fiemap_count: Number of extents from FIEMAP
        - filefrag_count: Number of extents from filefrag
        - match: Whether counts match
    """
    import subprocess
    import re
    
    # Get FIEMAP extents
    analyzer = FiemapAnalyzer()
    fiemap_extents = analyzer.get_extents(filepath)
    fiemap_count = len(fiemap_extents) if fiemap_extents else 0
    
    # Get filefrag extents
    try:
        result = subprocess.run(
            ['filefrag', '-v', filepath],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Parse filefrag output
        # Look for lines with extent information (format: ext: logical_offset: physical_offset: length: flags)
        extent_pattern = r'^\s*\d+:'
        filefrag_count = 0
        
        for line in result.stdout.split('\n'):
            if re.match(extent_pattern, line):
                filefrag_count += 1
        
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.warning(f"filefrag failed for {filepath}: {e}")
        filefrag_count = -1
    
    return {
        'fiemap_count': fiemap_count,
        'filefrag_count': filefrag_count,
        'match': fiemap_count == filefrag_count if filefrag_count >= 0 else False
    }