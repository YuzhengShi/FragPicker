#!/usr/bin/env python3
"""
End-to-End FragPicker Workflow Benchmark

Measures complete FragPicker workflow performance comparing sequential vs parallel analysis.
This shows the real-world impact of parallel optimization in the full pipeline.

Workflow stages:
1. Inode mapping
2. File processing (FIEMAP analysis)
3. Sorting results

Compares:
- Original approach (sequential)
- Enhanced approach (parallel threading)
- Enhanced approach (parallel multiprocessing)
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
from parallel_analyzer.inode_mapper import build_inode_map
from parallel_analyzer.parallel_processor import EnhancedParallelProcessor
from parallel_analyzer.multiprocess_processor import MultiprocessProcessor
from parallel_analyzer.parallel_sorter import ParallelSorter


class EndToEndBenchmark:
    """End-to-end FragPicker workflow benchmark"""
    
    def __init__(self, results_dir: Path):
        self.results_dir = results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # Configuration
        self.num_files = 1000
        self.file_size_kb = 100
        self.num_runs = 3
        
        self.results = []
    
    def create_test_filesystem(self, test_dir: Path) -> List[str]:
        """Create a test filesystem with files"""
        print(f"\n  Creating test filesystem ({self.num_files} files)...", end=" ", flush=True)
        
        filepaths = []
        file_size_bytes = self.file_size_kb * 1024
        
        for i in range(self.num_files):
            filepath = test_dir / f"file_{i:06d}.dat"
            
            # Create file
            try:
                subprocess.run(
                    ['fallocate', '-l', str(file_size_bytes), str(filepath)],
                    check=True,
                    capture_output=True
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                with open(filepath, 'wb') as f:
                    f.write(b'\0' * file_size_bytes)
            
            filepaths.append(str(filepath))
        
        print("✓")
        return filepaths
    
    def benchmark_sequential_workflow(self, mount_point: str) -> Dict[str, Any]:
        """Benchmark sequential workflow (original FragPicker approach)"""
        
        timing = {}
        
        # Stage 1: Inode mapping
        start = time.time()
        inode_map = build_inode_map(mount_point)
        timing['inode_mapping'] = time.time() - start
        
        # Create file list (simulate from trace data)
        file_list = [(inode, 1) for inode in inode_map.keys()]
        
        # Stage 2: Sequential file processing
        start = time.time()
        analyzer = FiemapAnalyzer()
        file_results = []
        
        for inode, req_count in file_list:
            filepath = inode_map.get(inode)
            if filepath:
                extents = analyzer.get_extents(filepath)
                if extents:
                    file_results.append({
                        'inode': inode,
                        'extents': len(extents),
                        'filepath': filepath
                    })
        
        timing['file_processing'] = time.time() - start
        
        # Stage 3: Sorting (Python built-in)
        start = time.time()
        sorted_results = sorted(file_results, key=lambda x: x['inode'])
        timing['sorting'] = time.time() - start
        
        timing['total'] = sum(timing.values())
        
        return {
            'timing': timing,
            'files_processed': len(file_results),
            'throughput': len(file_results) / timing['total'] if timing['total'] > 0 else 0
        }
    
    def benchmark_parallel_threading_workflow(self, mount_point: str) -> Dict[str, Any]:
        """Benchmark parallel workflow with threading"""
        
        timing = {}
        
        # Stage 1: Inode mapping (batch - single find)
        start = time.time()
        inode_map = build_inode_map(mount_point)
        timing['inode_mapping'] = time.time() - start
        
        # Create file list
        file_list = [(inode, 1) for inode in inode_map.keys()]
        
        # Stage 2: Parallel file processing (threading)
        processor = EnhancedParallelProcessor(
            num_workers=8,
            mount_point=mount_point,
            enable_monitoring=False,
            enable_profiling=False
        )
        processor.inode_map = inode_map
        
        start = time.time()
        results = processor.process_files(file_list, enable_sorting=False)
        timing['file_processing'] = time.time() - start
        
        # Stage 3: Parallel sorting
        start = time.time()
        sorter = ParallelSorter(num_workers=4)
        sorted_results = sorter.sort_files(results.get('files', []))
        timing['sorting'] = time.time() - start
        
        timing['total'] = sum(timing.values())
        
        return {
            'timing': timing,
            'files_processed': results.get('stats', {}).get('files_processed', 0),
            'throughput': results.get('stats', {}).get('files_per_second', 0)
        }
    
    def benchmark_parallel_multiprocess_workflow(self, mount_point: str) -> Dict[str, Any]:
        """Benchmark parallel workflow with multiprocessing"""
        
        timing = {}
        
        # Stage 1: Inode mapping
        start = time.time()
        inode_map = build_inode_map(mount_point)
        timing['inode_mapping'] = time.time() - start
        
        # Create file list
        file_list = [(inode, 1) for inode in inode_map.keys()]
        
        # Stage 2: Parallel file processing (multiprocessing)
        processor = MultiprocessProcessor(num_workers=8)
        processor.inode_map = inode_map
        processor.mount_point = mount_point
        
        start = time.time()
        results = processor.process_files(file_list, enable_sorting=False)
        timing['file_processing'] = time.time() - start
        
        # Stage 3: Parallel sorting
        start = time.time()
        sorter = ParallelSorter(num_workers=4)
        sorted_results = sorter.sort_files(results.get('files', []))
        timing['sorting'] = time.time() - start
        
        timing['total'] = sum(timing.values())
        
        return {
            'timing': timing,
            'files_processed': results.get('stats', {}).get('files_processed', 0),
            'throughput': results.get('stats', {}).get('files_per_second', 0)
        }
    
    def run_benchmark(self) -> List[Dict]:
        """Run complete end-to-end benchmark"""
        
        print("="*70)
        print("End-to-End FragPicker Workflow Benchmark")
        print("="*70)
        print(f"Configuration:")
        print(f"  Files: {self.num_files}")
        print(f"  File size: {self.file_size_kb} KB")
        print(f"  Runs: {self.num_runs}")
        print("="*70)
        
        # Create test filesystem
        test_dir = self.results_dir / "test_filesystem"
        test_dir.mkdir(exist_ok=True)
        
        try:
            filepaths = self.create_test_filesystem(test_dir)
            mount_point = str(test_dir)
            
            all_results = []
            
            # Run benchmarks
            for run_num in range(self.num_runs):
                print(f"\n{'='*70}")
                print(f"Run {run_num + 1}/{self.num_runs}")
                print(f"{'='*70}")
                
                run_result = {
                    'run_number': run_num + 1,
                    'sequential': {},
                    'parallel_threading': {},
                    'parallel_multiprocessing': {}
                }
                
                # Sequential workflow
                print(f"\n  Sequential workflow...")
                seq_result = self.benchmark_sequential_workflow(mount_point)
                run_result['sequential'] = seq_result
                print(f"    Total: {seq_result['timing']['total']:.3f}s")
                print(f"    Inode mapping: {seq_result['timing']['inode_mapping']:.3f}s")
                print(f"    File processing: {seq_result['timing']['file_processing']:.3f}s")
                print(f"    Sorting: {seq_result['timing']['sorting']:.3f}s")
                
                # Parallel threading workflow
                print(f"\n  Parallel workflow (threading)...")
                par_thr_result = self.benchmark_parallel_threading_workflow(mount_point)
                run_result['parallel_threading'] = par_thr_result
                threading_speedup = seq_result['timing']['total'] / par_thr_result['timing']['total'] if par_thr_result['timing']['total'] > 0 else 0
                print(f"    Total: {par_thr_result['timing']['total']:.3f}s ({threading_speedup:.2f}x speedup)")
                print(f"    Inode mapping: {par_thr_result['timing']['inode_mapping']:.3f}s")
                print(f"    File processing: {par_thr_result['timing']['file_processing']:.3f}s")
                print(f"    Sorting: {par_thr_result['timing']['sorting']:.3f}s")
                
                # Parallel multiprocessing workflow
                print(f"\n  Parallel workflow (multiprocessing)...")
                par_mp_result = self.benchmark_parallel_multiprocess_workflow(mount_point)
                run_result['parallel_multiprocessing'] = par_mp_result
                mp_speedup = seq_result['timing']['total'] / par_mp_result['timing']['total'] if par_mp_result['timing']['total'] > 0 else 0
                print(f"    Total: {par_mp_result['timing']['total']:.3f}s ({mp_speedup:.2f}x speedup)")
                print(f"    Inode mapping: {par_mp_result['timing']['inode_mapping']:.3f}s")
                print(f"    File processing: {par_mp_result['timing']['file_processing']:.3f}s")
                print(f"    Sorting: {par_mp_result['timing']['sorting']:.3f}s")
                
                all_results.append(run_result)
            
            return all_results
            
        finally:
            # Cleanup
            shutil.rmtree(test_dir, ignore_errors=True)
    
    def save_results(self, all_results: List[Dict]):
        """Save results to JSON"""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Calculate averages
        averages = self._calculate_averages(all_results)
        
        output = {
            'timestamp': datetime.now().isoformat(),
            'configuration': {
                'num_files': self.num_files,
                'file_size_kb': self.file_size_kb,
                'num_runs': self.num_runs
            },
            'results': all_results,
            'averages': averages,
            'summary': self._generate_summary(averages)
        }
        
        # Save
        output_file = self.results_dir / f"end_to_end_workflow_{timestamp}.json"
        with open(output_file, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\n{'='*70}")
        print(f"Results saved to: {output_file}")
        print(f"{'='*70}")
        
        return output_file
    
    def _calculate_averages(self, runs: List[Dict]) -> Dict:
        """Calculate averages across runs"""
        
        n = len(runs)
        if n == 0:
            return {}
        
        avg = {}
        
        for workflow_type in ['sequential', 'parallel_threading', 'parallel_multiprocessing']:
            timing_avg = {}
            
            for stage in ['inode_mapping', 'file_processing', 'sorting', 'total']:
                times = [r[workflow_type]['timing'][stage] for r in runs]
                timing_avg[stage] = sum(times) / n
            
            avg[workflow_type] = {'timing': timing_avg}
        
        # Calculate speedups
        seq_total = avg['sequential']['timing']['total']
        avg['parallel_threading']['speedup'] = seq_total / avg['parallel_threading']['timing']['total'] if avg['parallel_threading']['timing']['total'] > 0 else 0
        avg['parallel_multiprocessing']['speedup'] = seq_total / avg['parallel_multiprocessing']['timing']['total'] if avg['parallel_multiprocessing']['timing']['total'] > 0 else 0
        
        return avg
    
    def _generate_summary(self, averages: Dict) -> Dict:
        """Generate summary analysis"""
        
        seq = averages['sequential']['timing']
        par_thr = averages['parallel_threading']['timing']
        par_mp = averages['parallel_multiprocessing']['timing']
        
        summary = {
            'total_speedup': {
                'threading': averages['parallel_threading']['speedup'],
                'multiprocessing': averages['parallel_multiprocessing']['speedup']
            },
            'stage_improvements': {
                'inode_mapping': {
                    'sequential': seq['inode_mapping'],
                    'parallel': par_thr['inode_mapping'],
                    'improvement': (seq['inode_mapping'] - par_thr['inode_mapping']) / seq['inode_mapping'] * 100 if seq['inode_mapping'] > 0 else 0
                },
                'file_processing': {
                    'sequential': seq['file_processing'],
                    'parallel_threading': par_thr['file_processing'],
                    'parallel_multiprocessing': par_mp['file_processing'],
                    'threading_speedup': seq['file_processing'] / par_thr['file_processing'] if par_thr['file_processing'] > 0 else 0,
                    'multiprocessing_speedup': seq['file_processing'] / par_mp['file_processing'] if par_mp['file_processing'] > 0 else 0
                },
                'sorting': {
                    'sequential': seq['sorting'],
                    'parallel': par_thr['sorting'],
                    'speedup': seq['sorting'] / par_thr['sorting'] if par_thr['sorting'] > 0 else 0
                }
            }
        }
        
        return summary


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='End-to-End Workflow Benchmark')
    parser.add_argument(
        '--results-dir',
        type=str,
        default='benchmark_results/end_to_end',
        help='Directory to save results'
    )
    parser.add_argument(
        '--files',
        type=int,
        default=1000,
        help='Number of test files'
    )
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Quick test (fewer files and runs)'
    )
    
    args = parser.parse_args()
    
    # Setup
    results_dir = Path(args.results_dir)
    benchmark = EndToEndBenchmark(results_dir)
    
    benchmark.num_files = args.files
    
    if args.quick:
        benchmark.num_files = 100
        benchmark.num_runs = 2
        print("\n[Quick Test Mode]\n")
    
    # Run
    all_results = benchmark.run_benchmark()
    
    # Save
    output_file = benchmark.save_results(all_results)
    
    # Print summary
    with open(output_file, 'r') as f:
        data = json.load(f)
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    summary = data['summary']
    print(f"\nOverall Speedup:")
    print(f"  Threading:       {summary['total_speedup']['threading']:.2f}x")
    print(f"  Multiprocessing: {summary['total_speedup']['multiprocessing']:.2f}x")
    
    print(f"\nFile Processing Stage:")
    fp = summary['stage_improvements']['file_processing']
    print(f"  Sequential:        {fp['sequential']:.3f}s")
    print(f"  Threading:         {fp['parallel_threading']:.3f}s ({fp['threading_speedup']:.2f}x speedup)")
    print(f"  Multiprocessing:   {fp['parallel_multiprocessing']:.3f}s ({fp['multiprocessing_speedup']:.2f}x speedup)")
    
    print("\n" + "="*70)
    print("BENCHMARK COMPLETE")
    print("="*70)
    print()


if __name__ == '__main__':
    main()
