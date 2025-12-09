#!/usr/bin/env python3
"""
Fragmentation Impact Benchmark

Tests how file fragmentation level affects parallel vs sequential FIEMAP performance.
This addresses the key question: "When does parallel optimization help?"

Creates files with varying extent counts (1, 10, 50, 100, 500+) and measures:
- Sequential processing time
- Parallel processing time (threading and multiprocessing)
- Speedup ratio
- Efficiency
"""

import os
import sys
import time
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Any

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "analysis"))

from parallel_analyzer.fiemap import FiemapAnalyzer
from parallel_analyzer.parallel_processor import EnhancedParallelProcessor
from parallel_analyzer.multiprocess_processor import MultiprocessProcessor


class FragmentationUtility:
    """Create files with specific extent counts for testing"""
    
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    def create_fragmented_file(self, filepath: Path, file_size_mb: int, target_extents: int) -> int:
        """
        Create a file with approximately target_extents number of extents
        
        Args:
            filepath: Path to create file
            file_size_mb: Total file size in MB
            target_extents: Target number of extents
        
        Returns:
            Actual number of extents created
        """
        if target_extents == 1:
            # Create contiguous file (1 extent)
            return self._create_contiguous_file(filepath, file_size_mb)
        else:
            # Create fragmented file
            return self._create_fragmented_file(filepath, file_size_mb, target_extents)
    
    def _create_contiguous_file(self, filepath: Path, size_mb: int) -> int:
        """Create a contiguous file (1 extent)"""
        # Use fallocate for fast contiguous allocation
        size_bytes = size_mb * 1024 * 1024
        
        try:
            # Try fallocate first (fastest)
            subprocess.run(
                ['fallocate', '-l', str(size_bytes), str(filepath)],
                check=True,
                capture_output=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fall back to dd
            with open(filepath, 'wb') as f:
                f.write(b'\0' * size_bytes)
        
        # Verify extent count
        analyzer = FiemapAnalyzer()
        extents = analyzer.get_extents(str(filepath))
        return len(extents) if extents else 0
    
    def _create_fragmented_file(self, filepath: Path, size_mb: int, target_extents: int) -> int:
        """Create a fragmented file by interleaving writes"""
        
        # Calculate chunk size to achieve target extents
        total_size = size_mb * 1024 * 1024
        chunk_size = max(4096, total_size // target_extents)  # At least 4KB per chunk
        num_chunks = total_size // chunk_size
        
        # Create temporary files to cause fragmentation
        temp_files = []
        temp_dir = self.base_dir / "temp_frag"
        temp_dir.mkdir(exist_ok=True)
        
        try:
            # Strategy: Interleave writes with temporary files
            with open(filepath, 'wb') as target:
                for i in range(num_chunks):
                    # Write chunk to target file
                    target.write(os.urandom(chunk_size))
                    target.flush()
                    os.fsync(target.fileno())
                    
                    # Create temporary file to cause fragmentation
                    if i < num_chunks - 1:
                        temp_file = temp_dir / f"temp_{i}.dat"
                        with open(temp_file, 'wb') as tf:
                            tf.write(os.urandom(chunk_size))
                            tf.flush()
                            os.fsync(tf.fileno())
                        temp_files.append(temp_file)
            
            # Verify extent count
            analyzer = FiemapAnalyzer()
            extents = analyzer.get_extents(str(filepath))
            actual_extents = len(extents) if extents else 0
            
            return actual_extents
            
        finally:
            # Cleanup temporary files
            shutil.rmtree(temp_dir, ignore_errors=True)


class FragmentationBenchmark:
    """Benchmark parallel vs sequential performance at different fragmentation levels"""
    
    def __init__(self, results_dir: Path):
        self.results_dir = results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.results = []
        
        # Test configuration
        self.fragmentation_levels = [
            (1, "clean"),           # 1 extent - clean file
            (10, "light"),          # 10 extents - lightly fragmented
            (50, "moderate"),       # 50 extents - moderately fragmented
            (100, "heavy"),         # 100 extents - heavily fragmented
            (500, "extreme")        # 500+ extents - extremely fragmented
        ]
        self.file_size_mb = 10
        self.num_files_per_level = 20  # Number of files to create per fragmentation level
        self.num_runs = 3  # Number of measurement runs
    
    def create_test_files(self, test_dir: Path, target_extents: int) -> List[str]:
        """Create test files with target extent count"""
        print(f"\n  Creating {self.num_files_per_level} files with ~{target_extents} extents each...")
        
        frag_util = FragmentationUtility(test_dir)
        filepaths = []
        actual_extents = []
        
        for i in range(self.num_files_per_level):
            filepath = test_dir / f"file_{i:04d}.dat"
            extents = frag_util.create_fragmented_file(filepath, self.file_size_mb, target_extents)
            filepaths.append(str(filepath))
            actual_extents.append(extents)
            
            if (i + 1) % 5 == 0:
                print(f"    Created {i + 1}/{self.num_files_per_level} files...")
        
        avg_extents = sum(actual_extents) / len(actual_extents)
        print(f"    ✓ Average extents: {avg_extents:.1f}")
        
        return filepaths
    
    def benchmark_sequential(self, filepaths: List[str]) -> Tuple[float, Dict]:
        """Benchmark sequential FIEMAP processing"""
        analyzer = FiemapAnalyzer()
        
        start_time = time.time()
        total_extents = 0
        
        for filepath in filepaths:
            extents = analyzer.get_extents(filepath)
            if extents:
                total_extents += len(extents)
        
        execution_time = time.time() - start_time
        
        return execution_time, {
            'files_processed': len(filepaths),
            'total_extents': total_extents,
            'files_per_second': len(filepaths) / execution_time if execution_time > 0 else 0
        }
    
    def benchmark_parallel(self, filepaths: List[str], num_workers: int, 
                          use_multiprocessing: bool = False) -> Tuple[float, Dict]:
        """Benchmark parallel FIEMAP processing"""
        
        # Build inode map
        inode_map = {}
        for filepath in filepaths:
            try:
                stat = os.stat(filepath)
                inode_map[str(stat.st_ino)] = filepath
            except Exception:
                pass
        
        # Create file list (inode, req_count)
        file_list = [(str(os.stat(fp).st_ino), 1) for fp in filepaths]
        
        if use_multiprocessing:
            processor = MultiprocessProcessor(num_workers=num_workers)
        else:
            processor = EnhancedParallelProcessor(
                num_workers=num_workers,
                enable_monitoring=False,
                enable_profiling=False
            )
        
        processor.inode_map = inode_map
        
        start_time = time.time()
        results = processor.process_files(file_list, enable_sorting=False)
        execution_time = time.time() - start_time
        
        return execution_time, {
            'files_processed': len(filepaths),
            'files_per_second': len(filepaths) / execution_time if execution_time > 0 else 0,
            'workers': num_workers
        }
    
    def run_benchmark_for_level(self, target_extents: int, label: str) -> Dict[str, Any]:
        """Run complete benchmark for one fragmentation level"""
        
        print(f"\n{'='*70}")
        print(f"Fragmentation Level: {target_extents} extents ({label})")
        print(f"{'='*70}")
        
        # Create test directory
        test_dir = self.results_dir / f"test_extents_{target_extents}"
        test_dir.mkdir(exist_ok=True)
        
        try:
            # Create test files
            filepaths = self.create_test_files(test_dir, target_extents)
            
            results = {
                'target_extents': target_extents,
                'label': label,
                'num_files': len(filepaths),
                'file_size_mb': self.file_size_mb,
                'runs': []
            }
            
            # Run benchmarks
            for run_num in range(self.num_runs):
                print(f"\n  Run {run_num + 1}/{self.num_runs}:")
                
                run_result = {
                    'run_number': run_num + 1,
                    'sequential': {},
                    'parallel_threading': {},
                    'parallel_multiprocessing': {}
                }
                
                # Sequential
                print(f"    Sequential...", end=" ", flush=True)
                seq_time, seq_stats = self.benchmark_sequential(filepaths)
                run_result['sequential'] = {
                    'time': seq_time,
                    'stats': seq_stats
                }
                print(f"{seq_time:.3f}s ({seq_stats['files_per_second']:.1f} files/s)")
                
                # Parallel threading (8 workers)
                print(f"    Parallel (threading, 8 workers)...", end=" ", flush=True)
                par_time, par_stats = self.benchmark_parallel(filepaths, 8, False)
                run_result['parallel_threading'] = {
                    'time': par_time,
                    'stats': par_stats,
                    'speedup': seq_time / par_time if par_time > 0 else 0
                }
                print(f"{par_time:.3f}s ({par_stats['files_per_second']:.1f} files/s, {run_result['parallel_threading']['speedup']:.2f}x)")
                
                # Parallel multiprocessing (8 workers)
                print(f"    Parallel (multiprocess, 8 workers)...", end=" ", flush=True)
                mp_time, mp_stats = self.benchmark_parallel(filepaths, 8, True)
                run_result['parallel_multiprocessing'] = {
                    'time': mp_time,
                    'stats': mp_stats,
                    'speedup': seq_time / mp_time if mp_time > 0 else 0
                }
                print(f"{mp_time:.3f}s ({mp_stats['files_per_second']:.1f} files/s, {run_result['parallel_multiprocessing']['speedup']:.2f}x)")
                
                results['runs'].append(run_result)
            
            # Calculate averages
            results['averages'] = self._calculate_averages(results['runs'])
            
            # Print summary
            self._print_summary(results)
            
            return results
            
        finally:
            # Cleanup
            shutil.rmtree(test_dir, ignore_errors=True)
    
    def _calculate_averages(self, runs: List[Dict]) -> Dict:
        """Calculate average metrics across runs"""
        
        n = len(runs)
        if n == 0:
            return {}
        
        avg = {
            'sequential_time': sum(r['sequential']['time'] for r in runs) / n,
            'threading_time': sum(r['parallel_threading']['time'] for r in runs) / n,
            'multiprocessing_time': sum(r['parallel_multiprocessing']['time'] for r in runs) / n,
        }
        
        avg['threading_speedup'] = avg['sequential_time'] / avg['threading_time'] if avg['threading_time'] > 0 else 0
        avg['multiprocessing_speedup'] = avg['sequential_time'] / avg['multiprocessing_time'] if avg['multiprocessing_time'] > 0 else 0
        
        return avg
    
    def _print_summary(self, results: Dict):
        """Print summary for one fragmentation level"""
        
        avg = results['averages']
        print(f"\n  Summary (averaged over {len(results['runs'])} runs):")
        print(f"    Sequential:        {avg['sequential_time']:.3f}s")
        print(f"    Threading:         {avg['threading_time']:.3f}s ({avg['threading_speedup']:.2f}x speedup)")
        print(f"    Multiprocessing:   {avg['multiprocessing_time']:.3f}s ({avg['multiprocessing_speedup']:.2f}x speedup)")
    
    def run_all_benchmarks(self) -> List[Dict]:
        """Run benchmarks for all fragmentation levels"""
        
        print("="*70)
        print("Fragmentation Impact Benchmark")
        print("="*70)
        print(f"Configuration:")
        print(f"  File size: {self.file_size_mb} MB")
        print(f"  Files per level: {self.num_files_per_level}")
        print(f"  Measurement runs: {self.num_runs}")
        print(f"  Fragmentation levels: {len(self.fragmentation_levels)}")
        print("="*70)
        
        all_results = []
        
        for target_extents, label in self.fragmentation_levels:
            result = self.run_benchmark_for_level(target_extents, label)
            all_results.append(result)
        
        return all_results
    
    def save_results(self, all_results: List[Dict]):
        """Save results to JSON file"""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        output = {
            'timestamp': datetime.now().isoformat(),
            'configuration': {
                'file_size_mb': self.file_size_mb,
                'num_files_per_level': self.num_files_per_level,
                'num_runs': self.num_runs,
                'fragmentation_levels': [
                    {'extents': e, 'label': l} for e, l in self.fragmentation_levels
                ]
            },
            'results': all_results,
            'summary': self._generate_summary(all_results)
        }
        
        # Save results
        output_file = self.results_dir / f"fragmentation_impact_{timestamp}.json"
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\n{'='*70}")
        print(f"Results saved to: {output_file}")
        print(f"{'='*70}")
        
        return output_file
    
    def _generate_summary(self, all_results: List[Dict]) -> Dict:
        """Generate summary analysis"""
        
        summary = {
            'key_findings': [],
            'speedup_by_fragmentation': []
        }
        
        for result in all_results:
            avg = result['averages']
            summary['speedup_by_fragmentation'].append({
                'extents': result['target_extents'],
                'label': result['label'],
                'threading_speedup': avg['threading_speedup'],
                'multiprocessing_speedup': avg['multiprocessing_speedup']
            })
        
        # Analyze trends
        speedups = summary['speedup_by_fragmentation']
        if len(speedups) > 0:
            max_threading = max(speedups, key=lambda x: x['threading_speedup'])
            max_multiprocess = max(speedups, key=lambda x: x['multiprocessing_speedup'])
            
            summary['key_findings'].append(
                f"Best threading speedup: {max_threading['threading_speedup']:.2f}x at {max_threading['extents']} extents"
            )
            summary['key_findings'].append(
                f"Best multiprocessing speedup: {max_multiprocess['multiprocessing_speedup']:.2f}x at {max_multiprocess['extents']} extents"
            )
        
        return summary


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Fragmentation Impact Benchmark')
    parser.add_argument(
        '--results-dir',
        type=str,
        default='benchmark_results/fragmentation',
        help='Directory to save results'
    )
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Quick test (fewer files and runs)'
    )
    
    args = parser.parse_args()
    
    # Setup
    results_dir = Path(args.results_dir)
    benchmark = FragmentationBenchmark(results_dir)
    
    if args.quick:
        # Quick test mode
        benchmark.num_files_per_level = 5
        benchmark.num_runs = 2
        benchmark.fragmentation_levels = [
            (1, "clean"),
            (50, "moderate"),
            (100, "heavy")
        ]
        print("\n[Quick Test Mode: Reduced files and runs]\n")
    
    # Run benchmarks
    all_results = benchmark.run_all_benchmarks()
    
    # Save results
    output_file = benchmark.save_results(all_results)
    
    # Print final summary
    print("\n" + "="*70)
    print("BENCHMARK COMPLETE")
    print("="*70)
    print(f"\nTo analyze results, run:")
    print(f"  python benchmarks/analyze_fragmentation.py {output_file}")
    print()


if __name__ == '__main__':
    main()
