#!/usr/bin/env python3
"""
Enhanced parallel processor with progress monitoring and performance analysis
Production-ready version with all optimizations
"""

import threading
import queue
import time
import os
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from .fiemap import FiemapAnalyzer, FiemapError
from .inode_mapper import build_inode_map, lookup_filepath
from .parallel_sorter import ParallelSorter
from .progress_monitor import ProgressMonitor, BackgroundMonitor
from .performance_analyzer import get_analyzer
from .logger import get_logger
from .config import get_config

logger = get_logger(__name__)


@dataclass
class ProcessingTask:
    """Enhanced task with metadata"""
    inode: str
    req_count: int
    filepath: Optional[str] = None
    priority: int = 0  # For priority queue


class EnhancedProcessingWorker(threading.Thread):
    """
    Enhanced worker with:
    - Error recovery
    - Performance tracking
    - Progress reporting
    """
    
    def __init__(self, worker_id: int, task_queue: queue.Queue,
                 result_queue: queue.Queue, inode_map: Optional[Dict],
                 mount_point: str, progress_callback=None):
        super().__init__(name=f"EnhancedWorker-{worker_id}")
        self.worker_id = worker_id
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.inode_map = inode_map
        self.mount_point = mount_point
        self.progress_callback = progress_callback
        
        self.fiemap = FiemapAnalyzer(get_config().fiemap)
        self.files_processed = 0
        self.errors = 0
        
        self.analyzer = get_analyzer()
    
    def run(self):
        """Enhanced worker loop with performance tracking"""
        logger.debug(f"Worker {self.worker_id} started")
        
        while True:
            task = None
            try:
                task = self.task_queue.get(timeout=1)
                
                if task is None:
                    self.task_queue.task_done()
                    break
                
                # Process with performance tracking
                with self.analyzer.time_block(f'worker_{self.worker_id}_process'):
                    result = self._process_task(task)
                
                self.result_queue.put(result)
                self.files_processed += 1
                
                # Report progress
                if self.progress_callback:
                    self.progress_callback(increment=1)
                
                self.task_queue.task_done()
                
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"Worker {self.worker_id} unexpected error: {e}")
                self.errors += 1
                if task is not None:
                    self.task_queue.task_done()
        
        logger.debug(f"Worker {self.worker_id} finished: "
                    f"{self.files_processed} files, {self.errors} errors")
    
    def _process_task(self, task: ProcessingTask) -> Dict:
        """Process single task with retry logic"""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                return self._process_file(task)
            except FiemapError as e:
                if attempt < max_retries - 1:
                    logger.debug(f"Retry {attempt+1} for inode {task.inode}: {e}")
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                else:
                    return {
                        'inode': task.inode,
                        'error': f'FIEMAP failed after {max_retries} attempts: {e}',
                        'worker_id': self.worker_id
                    }
            except Exception as e:
                return {
                    'inode': task.inode,
                    'error': str(e),
                    'worker_id': self.worker_id
                }
    
    def _process_file(self, task: ProcessingTask) -> Dict:
        """Process single file"""
        # Lookup filepath
        with self.analyzer.time_block('filepath_lookup'):
            filepath = lookup_filepath(task.inode, self.inode_map, self.mount_point)
        
        if not filepath:
            return {
                'inode': task.inode,
                'error': 'File not found',
                'worker_id': self.worker_id
            }
        
        # Check file type
        if os.path.isdir(filepath):
            return {
                'inode': task.inode,
                'error': 'Is directory',
                'worker_id': self.worker_id
            }
        
        # Get extent information
        with self.analyzer.time_block('fiemap_analysis'):
            extents = self.fiemap.get_extents(filepath)
        
        if extents is None:
            return {
                'inode': task.inode,
                'filepath': filepath,
                'error': 'FIEMAP failed',
                'worker_id': self.worker_id
            }
        
        return {
            'inode': task.inode,
            'filepath': filepath,
            'extent_count': len(extents),
            'req_count': task.req_count,
            'extents': extents,
            'worker_id': self.worker_id,
            'success': True
        }


class EnhancedParallelProcessor:
    """
    Production-ready parallel processor with all features:
    - Progress monitoring
    - Performance analysis
    - Parallel sorting
    - Resource monitoring
    - Adaptive threading
    """
    
    def __init__(self, num_workers: Optional[int] = None,
                 mount_point: str = "/mnt",
                 enable_monitoring: bool = True,
                 enable_profiling: bool = True):
        
        config = get_config()
        
        self.num_workers = num_workers or config.parallel.num_workers
        self.mount_point = mount_point
        self.enable_monitoring = enable_monitoring
        self.enable_profiling = enable_profiling
        
        self.task_queue = queue.Queue(maxsize=config.parallel.queue_size)
        self.result_queue = queue.Queue()
        self.workers = []
        
        self.inode_map = None
        self.progress_monitor = ProgressMonitor() if enable_monitoring else None
        self.resource_monitor = None
        self.analyzer = get_analyzer() if enable_profiling else None
    
    def process_files(self, file_list: List[Tuple[str, int]],
                     enable_sorting: bool = True) -> Dict:
        """
        Complete file processing with all optimizations
        
        Args:
            file_list: List of (inode, req_count) tuples
            enable_sorting: Enable parallel sorting after processing
        
        Returns:
            Comprehensive results dictionary
        """
        logger.info(f"Starting parallel processing: {len(file_list)} files, "
                   f"{self.num_workers} workers")
        
        start_time = time.time()
        
        # Start resource monitoring
        if self.enable_monitoring:
            self.resource_monitor = BackgroundMonitor()
            self.resource_monitor.start()
        
        # Phase 1: Build inode map
        with (self.analyzer.time_block('inode_mapping') 
              if self.analyzer else self._dummy_context()):
            if self.progress_monitor:
                bar = self.progress_monitor.create_stage(
                    'inode_map', 1, 'Building inode map: '
                )
            
            self.inode_map = build_inode_map(self.mount_point, verbose=True)
            
            if self.progress_monitor:
                bar.update(completed=1)
                bar.finish()
        
        # Phase 2: Parallel file processing
        with (self.analyzer.time_block('parallel_processing') 
              if self.analyzer else self._dummy_context()):
            
            if self.progress_monitor:
                process_bar = self.progress_monitor.create_stage(
                    'processing', len(file_list), 'Processing files: '
                )
                progress_callback = process_bar.update
            else:
                progress_callback = None
            
            # Fill task queue
            for inode, req_count in file_list:
                task = ProcessingTask(inode, req_count)
                self.task_queue.put(task)
            
            # Start workers
            self._start_workers(progress_callback)
            
            # Add poison pills
            for _ in range(self.num_workers):
                self.task_queue.put(None)
            
            # Wait for completion
            self.task_queue.join()
            
            for worker in self.workers:
                worker.join()
            
            if self.progress_monitor:
                process_bar.finish()
        
        # Collect results
        results = []
        errors = []
        
        while not self.result_queue.empty():
            result = self.result_queue.get()
            if result.get('success'):
                results.append(result)
            else:
                errors.append(result)
        
        # Phase 3: Parallel sorting (if enabled)
        sort_time = 0
        sorted_files = []
        if enable_sorting and results:
            with (self.analyzer.time_block('parallel_sorting') 
                  if self.analyzer else self._dummy_context()):
                
                logger.info("Starting parallel sorting...")
                
                # Create temporary directory for result files
                import tempfile
                sort_dir = tempfile.mkdtemp(prefix="fragpicker_sort_")
                
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
                    
                    sort_time = sort_result['total_time']
                    logger.info(f"Sorting completed: {sort_result['successful']}/{len(files_to_sort)} files "
                              f"in {sort_time:.2f}s")
                
                finally:
                    # Cleanup will happen later, keep files for now if needed
                    pass
        
        # Stop resource monitoring
        resource_stats = {}
        if self.resource_monitor:
            resource_stats = self.resource_monitor.stop()
        
        # Calculate final statistics
        total_time = time.time() - start_time
        
        stats = {
            'total_files': len(file_list),
            'successful': len(results),
            'failed': len(errors),
            'total_time': total_time,
            'sort_time': sort_time,
            'files_per_second': len(file_list) / total_time if total_time > 0 else 0,
            'num_workers': self.num_workers,
            'resource_usage': resource_stats
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
    
    def _start_workers(self, progress_callback):
        """Start worker threads"""
        for i in range(self.num_workers):
            worker = EnhancedProcessingWorker(
                i, self.task_queue, self.result_queue,
                self.inode_map, self.mount_point,
                progress_callback
            )
            worker.start()
            self.workers.append(worker)
    
    def _dummy_context(self):
        """Dummy context manager when profiling disabled"""
        from contextlib import nullcontext
        return nullcontext()
    
    def print_performance_report(self):
        """Print comprehensive performance report"""
        if self.analyzer:
            self.analyzer.print_report()
        
        # Print FIEMAP statistics from all workers
        print("\nFIEMAP Statistics (aggregated):")
        total_stats = {
            'files_analyzed': 0,
            'total_extents': 0,
            'ioctl_calls': 0,
            'errors': 0
        }
        
        for worker in self.workers:
            worker_stats = worker.fiemap.get_stats()
            for key in total_stats:
                if key in worker_stats:
                    total_stats[key] += worker_stats[key]
        
        print(f"  Files analyzed:  {total_stats['files_analyzed']:,}")
        print(f"  Total extents:   {total_stats['total_extents']:,}")
        print(f"  IOCTL calls:     {total_stats['ioctl_calls']:,}")
        print(f"  Errors:          {total_stats['errors']}")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python parallel_processor.py <directory> [num_workers]")
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
    
    print(f"Testing Enhanced Parallel Processor")
    print(f"Files: {len(files)}")
    print(f"Workers: {num_workers or 'auto'}")
    print("=" * 70)
    
    processor = EnhancedParallelProcessor(num_workers=num_workers)
    report = processor.process_files(files, enable_sorting=True)
    
    print("\nResults:")
    print(f"  Successful: {report['stats']['successful']}")
    print(f"  Failed: {report['stats']['failed']}")
    print(f"  Time: {report['stats']['total_time']:.2f}s")
    print(f"  Throughput: {report['stats']['files_per_second']:.1f} files/sec")
    
    # Print performance report
    processor.print_performance_report()