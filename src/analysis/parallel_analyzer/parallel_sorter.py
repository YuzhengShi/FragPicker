#!/usr/bin/env python3
"""
Parallel file sorting optimization
Replaces sequential sort operations with parallel multi-threaded sorting
"""

import os
import subprocess
import tempfile
import threading
import queue
import time
from typing import List, Dict, Optional
from pathlib import Path

from .logger import get_logger
from .config import get_config

logger = get_logger(__name__)


class SortTask:
    """Represents a single file sorting task"""
    
    def __init__(self, input_file: str, output_file: str, 
                 numeric: bool = True, unique: bool = False):
        self.input_file = input_file
        self.output_file = output_file
        self.numeric = numeric
        self.unique = unique
        self.start_time = None
        self.end_time = None
        self.success = False
        self.error = None


class SortWorker(threading.Thread):
    """Worker thread for parallel sorting"""
    
    def __init__(self, worker_id: int, task_queue: queue.Queue, 
                 result_queue: queue.Queue):
        super().__init__(name=f"SortWorker-{worker_id}")
        self.worker_id = worker_id
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.files_sorted = 0
    
    def run(self):
        """Worker main loop"""
        while True:
            task = None
            try:
                task = self.task_queue.get(timeout=1)
                
                if task is None:  # Poison pill
                    self.task_queue.task_done()
                    break
                
                # Execute sort
                task.start_time = time.time()
                self._sort_file(task)
                task.end_time = time.time()
                
                self.result_queue.put(task)
                self.files_sorted += 1
                
                self.task_queue.task_done()
                
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"Sort worker {self.worker_id} error: {e}")
                if task is not None:
                    self.task_queue.task_done()
    
    def _sort_file(self, task: SortTask):
        """Execute sort operation"""
        try:
            # Build sort command
            cmd = ['sort']
            
            if task.numeric:
                cmd.append('-g')  # General numeric sort
            
            if task.unique:
                cmd.append('-u')  # Unique lines only
            
            cmd.append(task.input_file)
            
            # Execute sort
            with open(task.output_file, 'w') as outf:
                result = subprocess.run(
                    cmd,
                    stdout=outf,
                    stderr=subprocess.PIPE,
                    timeout=60  # 1 minute timeout
                )
            
            if result.returncode == 0:
                task.success = True
            else:
                task.error = result.stderr.decode('utf-8')
                logger.warning(f"Sort failed for {task.input_file}: {task.error}")
        
        except subprocess.TimeoutExpired:
            task.error = "Sort timeout (>60s)"
            logger.error(f"Sort timeout for {task.input_file}")
        except Exception as e:
            task.error = str(e)
            logger.error(f"Sort exception for {task.input_file}: {e}")


class ParallelSorter:
    """
    Parallel file sorting coordinator
    
    Replaces sequential sort operations in processing.py with parallel sorting
    for significant speedup on multi-core systems.
    
    Usage:
        sorter = ParallelSorter(num_workers=8)
        results = sorter.sort_files(file_list)
    """
    
    def __init__(self, num_workers: int = 4, verbose: bool = True):
        self.num_workers = num_workers
        self.verbose = verbose
        
        self.task_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.workers = []
    
    def log(self, message: str):
        """Log message if verbose"""
        if self.verbose:
            logger.info(message)
    
    def sort_files(self, file_list: List[str], 
                   output_dir: Optional[str] = None,
                   numeric: bool = True,
                   unique: bool = False,
                   in_place: bool = True) -> Dict:
        """
        Sort multiple files in parallel
        
        Args:
            file_list: List of input files to sort
            output_dir: Output directory (uses temp if None)
            numeric: Use numeric sort (-g)
            unique: Remove duplicate lines (-u)
            in_place: Overwrite input files with sorted output
        
        Returns:
            {
                'successful': int,
                'failed': int,
                'total_time': float,
                'throughput': float,
                'results': [...]
            }
        """
        start_time = time.time()
        
        # Setup output directory
        if output_dir is None:
            output_dir = tempfile.mkdtemp(prefix="sort_")
            cleanup_dir = True
        else:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            cleanup_dir = False
        
        self.log(f"Parallel sorting {len(file_list)} files with {self.num_workers} workers")
        
        # Create tasks
        for input_file in file_list:
            if in_place:
                # Create temp file, will replace original after sort
                output_file = os.path.join(output_dir, 
                                          f"{Path(input_file).name}.sorted")
            else:
                output_file = os.path.join(output_dir, Path(input_file).name)
            
            task = SortTask(input_file, output_file, numeric, unique)
            self.task_queue.put(task)
        
        # Start workers
        self._start_workers()
        
        # Add poison pills
        for _ in range(self.num_workers):
            self.task_queue.put(None)
        
        # Wait for completion
        self.task_queue.join()
        
        # Wait for workers to exit
        for worker in self.workers:
            worker.join()
        
        # Collect results
        results = []
        successful = 0
        failed = 0
        
        while not self.result_queue.empty():
            task = self.result_queue.get()
            
            if task.success:
                successful += 1
                
                # Replace original file if in_place
                if in_place:
                    try:
                        os.replace(task.output_file, task.input_file)
                    except OSError as e:
                        logger.error(f"Failed to replace {task.input_file}: {e}")
                        task.success = False
                        task.error = str(e)
                        successful -= 1
                        failed += 1
            else:
                failed += 1
            
            results.append({
                'input': task.input_file,
                'output': task.output_file,
                'success': task.success,
                'error': task.error,
                'duration': task.end_time - task.start_time if task.end_time else None
            })
        
        total_time = time.time() - start_time
        
        # Cleanup temp directory
        if cleanup_dir:
            import shutil
            try:
                shutil.rmtree(output_dir)
            except:
                pass
        
        self.log(f"Sorted {successful}/{len(file_list)} files in {total_time:.2f}s")
        
        return {
            'successful': successful,
            'failed': failed,
            'total_files': len(file_list),
            'total_time': total_time,
            'throughput': len(file_list) / total_time if total_time > 0 else 0,
            'results': results
        }
    
    def _start_workers(self):
        """Start worker threads"""
        for i in range(self.num_workers):
            worker = SortWorker(i, self.task_queue, self.result_queue)
            worker.start()
            self.workers.append(worker)


# Convenience function for processing.py integration
def parallel_sort_directory(directory: str, pattern: str = "*.txt",
                           num_workers: int = 4) -> Dict:
    """
    Sort all files matching pattern in directory
    
    This is a drop-in replacement for sequential sorting in processing.py
    
    Usage:
        # Instead of:
        for file in files:
            subprocess.call(['sort', '-g', file], stdout=open('tmp.txt', 'w'))
            os.rename('tmp.txt', file)
        
        # Use:
        parallel_sort_directory('.', '*.txt', num_workers=8)
    """
    from glob import glob
    
    file_list = glob(os.path.join(directory, pattern))
    
    if not file_list:
        logger.warning(f"No files found matching {pattern} in {directory}")
        return {'successful': 0, 'failed': 0, 'total_files': 0}
    
    sorter = ParallelSorter(num_workers=num_workers)
    return sorter.sort_files(file_list, in_place=True)


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python parallel_sorter.py <directory> [num_workers]")
        print("       Sorts all .txt files in directory")
        sys.exit(1)
    
    directory = sys.argv[1]
    num_workers = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    
    print(f"Parallel sorting files in {directory}")
    print(f"Workers: {num_workers}")
    print("=" * 60)
    
    result = parallel_sort_directory(directory, "*.txt", num_workers)
    
    print(f"\nResults:")
    print(f"  Successful: {result['successful']}")
    print(f"  Failed: {result['failed']}")
    print(f"  Time: {result['total_time']:.2f}s")
    print(f"  Throughput: {result['throughput']:.1f} files/sec")