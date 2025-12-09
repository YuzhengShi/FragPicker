#!/usr/bin/env python3
"""
Workload Threshold Benchmark

Finds the crossover point where parallel processing becomes worthwhile.
Tests varying file counts to determine optimal execution model based on workload size.

Answers the question: "How many files needed before parallel helps?"
"""

import os
import sys
import time
import json
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Any

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src" / "analysis"))

from parallel_analyzer.fiemap import FiemapAnalyzer
from parallel_analyzer.parallel_processor import EnhancedParallelProcessor
from parallel_analyzer.multiprocess_processor import MultiprocessProcessor


class WorkloadThresholdBenchmark:
    """
    Find workload threshold where parallel processing becomes beneficial
    """
    
    def __init__(self, results_dir: Path):
        self.results_dir = results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Test configuration
        self.file_counts = [10, 50, 100, 200, 500, 1000, 2000, 5000]
        self.worker_counts = [1, 2, 4, 8]
        self.file_size_kb = 100  # Small files (100KB each)
        self.num_runs = 3
        
        self.results = []
    
    def create_test_files(self, test_dir: Path, num_files: int) -> List[str]:
        """Create test files"""
        print(f"\n  Creating {num_files} test files ({self.file_size_kb}KB each)...", end=" ", flush=True)
        
        filepaths = []
        file_size_bytes = self.file_size_kb * 1024
        
        for i in range(num_files):
            filepath = test_dir / f"file_{i:06d}.dat"
            
            # Use fallocate for speed
            try:
                import subprocess
                subprocess.run(
                    ['fallocate', '-l', str(file_size_bytes), str(filepath)],
                    check=True,
                    capture_output=True
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Fallback: write zeros
                with open(filepath, 'wb') as f:
                    f.write(b'\0' * file_size_bytes)
            
            filepaths.append(str(filepath))
        
        print("✓")
        return filepaths
    
    def benchmark_sequential(self, filepaths: List[str]) -> Tuple[float, Dict]:
        """Benchmark sequential processing"""
        analyzer = FiemapAnalyzer()
        
        start_time = time.time()
        
        for filepath in filepaths:
            extents = analyzer.get_extents(filepath)
        
        execution_time = time.time() - start_time
        
        return execution_time, {
            'files_processed': len(filepaths),
            'files_per_second': len(filepaths) / execution_time if execution_time > 0 else 0
        }
    
    def benchmark_parallel(self, filepaths: List[str], num_workers: int) ->Tuple[float, Dict]:
        """Benchmark parallel processing with threading"""
        
        # Build inode map
        inode_map = {}
        for filepath in filepaths:
            try:
                stat = os.stat(filepath)
                inode_map[str(stat.st_ino)] = filepath
            except Exception:
                pass
        
        # Create file list
        file_list = [(str(os.stat(fp).st_ino), 1) for fp in filepaths]
        
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
    
    def run_benchmark_for_count(self, num_files: int) -> Dict[str, Any]:
        """Run benchmark for specific file count"""
        
        print(f"\n{'='*70}")
        print(f"File Count: {num_files}")
        print(f"{'='*70}")
        
        # Create test directory
        test_dir = self.results_dir / f"test_files_{num_files}"
        test_dir.mkdir(exist_ok=True)
        
        try:
            # Create test files
            filepaths = self.create_test_files(test_dir, num_files)
            
            results = {
                'num_files': num_files,
                'file_size_kb': self.file_size_kb,
                'runs': []
            }
            
            # Run benchmarks
            for run_num in range(self.num_runs):
                print(f"\n  Run {run_num + 1}/{self.num_runs}:")
                
                run_result = {
                    'run_number': run_num + 1,
                    'sequential': {},
                    'parallel': {}
                }
                
                # Sequential (baseline)
                print(f"    Sequential (1 worker)...", end=" ", flush=True)
                seq_time, seq_stats = self.benchmark_sequential(filepaths)
                run_result['sequential'] = {
                    'time': seq_time,
                    'stats': seq_stats
                }
                print(f"{seq_time:.3f}s ({seq_stats['files_per_second']:.1f} files/s)")
                
                # Parallel with different worker counts
                for num_workers in self.worker_counts:
                    if num_workers == 1:
                        continue  # Skip, already did sequential
                    
                    print(f"    Parallel ({num_workers} workers)...", end=" ", flush=True)
                    par_time, par_stats = self.benchmark_parallel(filepaths, num_workers)
                    
                    speedup = seq_time / par_time if par_time > 0 else 0
                    efficiency = speedup / num_workers if num_workers > 0 else 0
                    
                    run_result['parallel'][num_workers] = {
                        'time': par_time,
                        'stats': par_stats,
                        'speedup': speedup,
                        'efficiency': efficiency
                    }
                    print(f"{par_time:.3f}s ({par_stats['files_per_second']:.1f} files/s, {speedup:.2f}x, {efficiency*100:.1f}% eff)")
                
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
        """Calculate average metrics"""
        
        n = len(runs)
        if n == 0:
            return {}
        
        avg = {
            'sequential_time': sum(r['sequential']['time'] for r in runs) / n,
            'parallel': {}
        }
        
        # Average for each worker count
        if runs and 'parallel' in runs[0]:
            for num_workers in runs[0]['parallel'].keys():
                times = [r['parallel'][num_workers]['time'] for r in runs]
                speedups = [r['parallel'][num_workers]['speedup'] for r in runs]
                efficiencies = [r['parallel'][num_workers]['efficiency'] for r in runs]
                
                avg['parallel'][num_workers] = {
                    'time': sum(times) / n,
                    'speedup': sum(speedups) / n,
                    'efficiency': sum(efficiencies) / n
                }
        
        return avg
    
    def _print_summary(self, results: Dict):
        """Print summary for one file count"""
        
        avg = results['averages']
        print(f"\n  Summary (averaged over {len(results['runs'])} runs):")
        print(f"    Sequential (1 worker):  {avg['sequential_time']:.3f}s (baseline)")
        
        for num_workers in sorted(avg['parallel'].keys()):
            data = avg['parallel'][num_workers]
            print(f"    Parallel ({num_workers} workers):    {data['time']:.3f}s ({data['speedup']:.2f}x speedup, {data['efficiency']*100:.1f}% efficiency)")
    
    def run_all_benchmarks(self) -> List[Dict]:
        """Run benchmarks for all file counts"""
        
        print("="*70)
        print("Workload Threshold Benchmark")
        print("="*70)
        print(f"Configuration:")
        print(f"  File size: {self.file_size_kb} KB")
        print(f"  File counts: {self.file_counts}")
        print(f"  Worker counts: {self.worker_counts}")
        print(f"  Measurement runs: {self.num_runs}")
        print("="*70)
        
        all_results = []
        
        for num_files in self.file_counts:
            result = self.run_benchmark_for_count(num_files)
            all_results.append(result)
        
        return all_results
    
    def save_results(self, all_results: List[Dict]):
        """Save results to JSON"""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        output = {
            'timestamp': datetime.now().isoformat(),
            'configuration': {
                'file_size_kb': self.file_size_kb,
                'file_counts': self.file_counts,
                'worker_counts': self.worker_counts,
                'num_runs': self.num_runs
            },
            'results': all_results,
            'analysis': self._analyze_threshold(all_results)
        }
        
        # Save results
        output_file = self.results_dir / f"workload_threshold_{timestamp}.json"
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\n{'='*70}")
        print(f"Results saved to: {output_file}")
        print(f"{'='*70}")
        
        return output_file
    
    def _analyze_threshold(self, all_results: List[Dict]) -> Dict:
        """Analyze threshold where parallel becomes worthwhile"""
        
        analysis = {
            'crossover_points': {},
            'optimal_workers': {},
            'recommendations': []
        }
        
        # Find crossover point for each worker count
        for num_workers in self.worker_counts:
            if num_workers == 1:
                continue
            
            crossover_files = None
            
            for result in all_results:
                num_files = result['num_files']
                avg = result['averages']
                
                if num_workers in avg['parallel']:
                    speedup = avg['parallel'][num_workers]['speedup']
                    
                    # Found where speedup > 1.1 (10% faster)
                    if speedup > 1.1 and crossover_files is None:
                        crossover_files = num_files
                        analysis['crossover_points'][num_workers] = {
                            'num_files': num_files,
                            'speedup': speedup
                        }
                        break
            
            if crossover_files is None:
                analysis['crossover_points'][num_workers] = {
                    'num_files': None,
                    'note': 'No significant speedup observed'
                }
        
        # Find optimal worker count for each file count
        for result in all_results:
            num_files = result['num_files']
            avg = result['averages']
            
            best_workers = 1
            best_speedup = 1.0
            
            for num_workers, data in avg['parallel'].items():
                if data['speedup'] > best_speedup:
                    best_speedup = data['speedup']
                    best_workers = num_workers
            
            analysis['optimal_workers'][num_files] = {
                'workers': best_workers,
                'speedup': best_speedup
            }
        
        # Generate recommendations
        if analysis['crossover_points']:
            min_crossover = min(
                (v['num_files'] for v in analysis['crossover_points'].values() if v['num_files'] is not None),
                default=None
            )
            
            if min_crossover:
                analysis['recommendations'].append(
                    f"Use parallel processing when file count >= {min_crossover}"
                )
        
        return analysis


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Workload Threshold Benchmark')
    parser.add_argument(
        '--results-dir',
        type=str,
        default='benchmark_results/workload_threshold',
        help='Directory to save results'
    )
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Quick test (fewer file counts)'
    )
    
    args = parser.parse_args()
    
    # Setup
    results_dir = Path(args.results_dir)
    benchmark = WorkloadThresholdBenchmark(results_dir)
    
    if args.quick:
        # Quick test
        benchmark.file_counts = [10, 100, 500, 1000]
        benchmark.num_runs = 2
        print("\n[Quick Test Mode]\n")
    
    # Run benchmarks
    all_results = benchmark.run_all_benchmarks()
    
    # Save results
    output_file = benchmark.save_results(all_results)
    
    # Print analysis
    print("\n" + "="*70)
    print("THRESHOLD ANALYSIS")
    print("="*70)
    
    with open(output_file, 'r') as f:
        data = json.load(f)
        analysis = data['analysis']
    
    print("\nCrossover Points (where parallel becomes >10% faster):")
    for workers, info in analysis['crossover_points'].items():
        if info['num_files']:
            print(f"  {workers} workers: {info['num_files']} files ({info['speedup']:.2f}x speedup)")
        else:
            print(f"  {workers} workers: {info.get('note', 'N/A')}")
    
    print("\nRecommendations:")
    for rec in analysis['recommendations']:
        print(f"  • {rec}")
    
    print("\n" + "="*70)
    print("BENCHMARK COMPLETE")
    print("="*70)
    print()


if __name__ == '__main__':
    main()
