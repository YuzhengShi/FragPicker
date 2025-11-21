#!/usr/bin/env python3
"""
Multiprocessing-based parallel processor (no GIL)
True parallelism for CPU/IO-bound workloads
"""

import multiprocessing as mp
import time
import os
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from .fiemap import FiemapAnalyzer
from .inode_mapper import build_inode_map, lookup_filepath
from .logger import get_logger
from .config import get_config

logger = get_logger(__name__)


@dataclass
class ProcessingTask:
    """Task for multiprocessing"""
    inode: str
    req_count: int


def process_file_worker(args):
    """
    Worker function for multiprocessing.Pool
    Must be at module level for pickling
    
    Args:
        args: Tuple of (task, inode_map, mount_point)
    
    Returns:
        Dict with processing results
    """
    task, inode_map, mount_point = args
    
    try:
        # Create FiemapAnalyzer in worker process
        fiemap = FiemapAnalyzer(get_config().fiemap)
        
        # Lookup filepath
        filepath = lookup_filepath(task.inode, inode_map, mount_point)
        
        if not filepath:
            return {
                'inode': task.inode,
                'error': 'File not found',
                'success': False
            }
        
        # Check file type
        if os.path.isdir(filepath):
            return {
                'inode': task.inode,
                'error': 'Is directory',
                'success': False
            }
        
        # Get extent information
        extents = fiemap.get_extents(filepath)
        
        if extents is None:
            return {
                'inode': task.inode,
                'filepath': filepath,
                'error': 'FIEMAP failed',
                'success': False
            }
        
        return {
            'inode': task.inode,
            'filepath': filepath,
            'extent_count': len(extents),
            'req_count': task.req_count,
            'extents': extents,
            'success': True
        }
        
    except Exception as e:
        return {
            'inode': task.inode,
            'error': str(e),
            'success': False
        }


class MultiprocessParallelProcessor:
    """
    Multiprocessing-based parallel processor
    
    Advantages over threading:
    - No GIL (Global Interpreter Lock)
    - True CPU parallelism
    - Better scaling on multi-core systems
    
    Disadvantages:
    - Higher memory usage (each process has own memory)
    - Process creation overhead
    - IPC (Inter-Process Communication) overhead
    """
    
    def __init__(self, num_workers: Optional[int] = None,
                 mount_point: str = "/mnt",
                 enable_monitoring: bool = False):
        
        config = get_config()
        
        # Use all CPUs by default, but cap at reasonable limit
        if num_workers is None:
            num_workers = min(mp.cpu_count(), config.parallel.max_workers)
        
        self.num_workers = num_workers
        self.mount_point = mount_point
        self.enable_monitoring = enable_monitoring
        
        self.inode_map = None
    
    def process_files(self, file_list: List[Tuple[str, int]],
                     enable_sorting: bool = True) -> Dict:
        """
        Process files in parallel using multiprocessing
        
        Args:
            file_list: List of (inode, req_count) tuples
            enable_sorting: Enable parallel sorting after processing
        
        Returns:
            Results dictionary with stats
        """
        logger.info(f"Starting multiprocess parallel processing: {len(file_list)} files, "
                   f"{self.num_workers} workers")
        
        start_time = time.time()
        
        # Phase 1: Build inode map (in main process)
        map_start = time.time()
        self.inode_map = build_inode_map(self.mount_point, verbose=True)
        map_time = time.time() - map_start
        
        # Phase 2: Parallel file processing using multiprocessing.Pool
        process_start = time.time()
        
        # Create tasks
        tasks = [ProcessingTask(inode, req_count) for inode, req_count in file_list]
        
        # Prepare arguments for worker function
        # Each worker gets (task, inode_map, mount_point)
        work_items = [(task, self.inode_map, self.mount_point) for task in tasks]
        
        # Use Pool.map for parallel processing
        with mp.Pool(processes=self.num_workers) as pool:
            # Use chunksize for better performance on large datasets
            chunksize = max(1, len(work_items) // (self.num_workers * 4))
            results_list = pool.map(process_file_worker, work_items, chunksize=chunksize)
        
        process_time = time.time() - process_start
        
        # Separate successful results from errors
        results = []
        errors = []
        
        for result in results_list:
            if result.get('success'):
                results.append(result)
            else:
                errors.append(result)
        
        # Phase 3: Parallel sorting (if enabled)
        sort_time = 0
        sorted_files = []
        if enable_sorting and results:
            import tempfile
            from .parallel_sorter import ParallelSorter
            
            sort_start = time.time()
            logger.info("Starting parallel sorting...")
            
            # Create temporary directory for result files
            sort_dir = tempfile.mkdtemp(prefix="fragpicker_sort_mp_")
            
            try:
                # Write extent results to files
                files_to_sort = []
                for result in results:
                    inode = result['inode']
                    filepath = os.path.join(sort_dir, f"{inode}.txt")
                    
                    # Write extent data to file
                    with open(filepath, 'w') as f:
                        for extent in result.get('extents', []):
                            # Write extent info: logical_offset physical_offset length
                            f.write(f"{extent['logical']} {extent['physical']} {extent['length']}\n")
                    
                    files_to_sort.append(filepath)
                
                # Sort the files
                sorter = ParallelSorter(num_workers=self.num_workers // 2 or 1, verbose=False)
                sort_result = sorter.sort_files(files_to_sort, in_place=True)
                
                # Read sorted results back
                for filepath in files_to_sort:
                    if os.path.exists(filepath):
                        sorted_files.append(filepath)
                
                sort_time = time.time() - sort_start
                logger.info(f"Sorting completed: {sort_result['successful']}/{len(files_to_sort)} files "
                          f"in {sort_time:.2f}s")
            
            finally:
                # Cleanup will happen later, keep files for now if needed
                pass
        
        # Calculate statistics
        total_time = time.time() - start_time
        
        stats = {
            'total_files': len(file_list),
            'successful': len(results),
            'failed': len(errors),
            'total_time': total_time,
            'map_time': map_time,
            'process_time': process_time,
            'sort_time': sort_time,
            'files_per_second': len(file_list) / total_time if total_time > 0 else 0,
            'num_workers': self.num_workers,
        }
        
        logger.info(f"Processing completed: {stats['successful']}/{stats['total_files']} "
                   f"files in {total_time:.2f}s ({stats['files_per_second']:.1f} files/sec)")
        
        result_dict = {
            'results': results,
            'stats': stats,
            'errors': errors
        }
        
        # Add sorted files if sorting was enabled
        if enable_sorting and sorted_files:
            result_dict['sorted_files'] = sorted_files
        
        return result_dict


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python multiprocess_processor.py <directory> [num_workers]")
        sys.exit(1)
    
    directory = sys.argv[1]
    num_workers = int(sys.argv[2]) if len(sys.argv) > 2 else None
    
    # Create test file list
    files = []
    for root, dirs, filenames in os.walk(directory):
        for filename in filenames:
            filepath = os.path.join(root, filename)
            try:
                stat = os.stat(filepath)
                files.append((str(stat.st_ino), 1))
            except:
                pass
        
        if len(files) >= 1000:
            break
    
    print(f"Testing Multiprocess Parallel Processor")
    print(f"Files: {len(files)}")
    print(f"Workers: {num_workers or 'auto (all CPUs)'}")
    print(f"CPUs available: {mp.cpu_count()}")
    print("=" * 70)
    
    processor = MultiprocessParallelProcessor(num_workers=num_workers)
    report = processor.process_files(files, enable_sorting=True)
    
    print("\nResults:")
    print(f"  Successful: {report['stats']['successful']}")
    print(f"  Failed: {report['stats']['failed']}")
    print(f"  Total time: {report['stats']['total_time']:.3f}s")
    print(f"  Map time: {report['stats']['map_time']:.3f}s")
    print(f"  Process time: {report['stats']['process_time']:.3f}s")
    print(f"  Throughput: {report['stats']['files_per_second']:.1f} files/sec")
