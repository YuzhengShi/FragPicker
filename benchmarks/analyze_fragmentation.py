#!/usr/bin/env python3
"""
Analyze Fragmentation Impact Benchmark Results

Analyzes and visualizes the relationship between fragmentation level and parallel speedup.
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Dict, List


def load_results(json_file: Path) -> Dict:
    """Load benchmark results from JSON file"""
    with open(json_file, 'r') as f:
        return json.load(f)


def analyze_fragmentation_impact(results: Dict):
    """Analyze and print fragmentation impact results"""
    
    print("="*80)
    print("FRAGMENTATION IMPACT ANALYSIS")
    print("="*80)
    
    # Configuration
    print("\nConfiguration:")
    config = results['configuration']
    print(f"  File size: {config['file_size_mb']} MB")
    print(f"  Files per level: {config['num_files_per_level']}")
    print(f"  Measurement runs: {config['num_runs']}")
    
    # Results by fragmentation level
    print("\n" + "="*80)
    print("RESULTS BY FRAGMENTATION LEVEL")
    print("="*80)
    print(f"\n{'Extents':>10} {'Label':>12} {'Sequential':>12} {'Threading':>12} {'Speedup':>10} {'MultiProc':>12} {'Speedup':>10}")
    print("-"*80)
    
    for result in results['results']:
        extents = result['target_extents']
        label = result['label']
        avg = result['averages']
        
        seq_time = avg['sequential_time']
        thr_time = avg['threading_time']
        thr_speedup = avg['threading_speedup']
        mp_time = avg['multiprocessing_time']
        mp_speedup = avg['multiprocessing_speedup']
        
        print(f"{extents:>10} {label:>12} {seq_time:>11.3f}s {thr_time:>11.3f}s {thr_speedup:>9.2f}x {mp_time:>11.3f}s {mp_speedup:>9.2f}x")
    
    # Key findings
    print("\n" + "="*80)
    print("KEY FINDINGS")
    print("="*80)
    
    summary = results.get('summary', {})
    findings = summary.get('key_findings', [])
    
    for finding in findings:
        print(f"  • {finding}")
    
    # Analyze trends
    print("\n" + "="*80)
    print("TREND ANALYSIS")
    print("="*80)
    
    speedup_data = summary.get('speedup_by_fragmentation', [])
    
    if len(speedup_data) > 1:
        first = speedup_data[0]
        last = speedup_data[-1]
        
        thr_improvement = last['threading_speedup'] / first['threading_speedup'] if first['threading_speedup'] > 0 else 0
        mp_improvement = last['multiprocessing_speedup'] / first['multiprocessing_speedup'] if first['multiprocessing_speedup'] > 0 else 0
        
        print(f"\nFrom {first['extents']} to {last['extents']} extents:")
        print(f"  Threading speedup:      {first['threading_speedup']:.2f}x → {last['threading_speedup']:.2f}x ({thr_improvement:.2f}x improvement)")
        print(f"  Multiprocessing speedup: {first['multiprocessing_speedup']:.2f}x → {last['multiprocessing_speedup']:.2f}x ({mp_improvement:.2f}x improvement)")
    
    # Recommendations
    print("\n" + "="*80)
    print("RECOMMENDATIONS")
    print("="*80)
    
    # Find crossover point where parallel becomes worthwhile
    for i, data in enumerate(speedup_data):
        if data['multiprocessing_speedup'] > 1.2:  # 20% faster threshold
            print(f"\n  Use parallel processing when:")
            print(f"    • Files have {data['extents']}+ extents ({data['label']} fragmentation)")
            print(f"    • Expected speedup: {data['multiprocessing_speedup']:.2f}x")
            break
    else:
        print("\n  Note: Parallel processing overhead may outweigh benefits for all tested")
        print("  fragmentation levels on this system (fast SSD).")
    
    print("\n  Best execution model by fragmentation level:")
    for data in speedup_data:
        best_model = "Multiprocessing" if data['multiprocessing_speedup'] > data['threading_speedup'] else "Threading"
        best_speedup = max(data['multiprocessing_speedup'], data['threading_speedup'])
        
        if best_speedup < 1.0:
            recommendation = f"Sequential (parallel is {1/best_speedup:.2f}x slower)"
        else:
            recommendation = f"{best_model} ({best_speedup:.2f}x speedup)"
        
        print(f"    {data['extents']:>4} extents ({data['label']:>10}): {recommendation}")


def export_csv(results: Dict, output_file: Path):
    """Export results to CSV format for plotting"""
    
    import csv
    
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        
        # Header
        writer.writerow([
            'Extents', 'Label', 'Run',
            'Sequential_Time', 'Threading_Time', 'MultiProcessing_Time',
            'Threading_Speedup', 'MultiProcessing_Speedup'
        ])
        
        # Data rows
        for result in results['results']:
            extents = result['target_extents']
            label = result['label']
            
            for run in result['runs']:
                run_num = run['run_number']
                seq_time = run['sequential']['time']
                thr_time = run['parallel_threading']['time']
                mp_time = run['parallel_multiprocessing']['time']
                thr_speedup = run['parallel_threading']['speedup']
                mp_speedup = run['parallel_multiprocessing']['speedup']
                
                writer.writerow([
                    extents, label, run_num,
                    seq_time, thr_time, mp_time,
                    thr_speedup, mp_speedup
                ])
    
    print(f"\n✓ CSV exported to: {output_file}")


def plot_results(results: Dict, output_dir: Path):
    """Generate visualization plots"""
    
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("\n! matplotlib not installed, skipping visualization")
        print("  Install with: pip install matplotlib")
        return
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Extract data
    extent_counts = []
    labels = []
    threading_speedups = []
    multiprocessing_speedups = []
    
    for result in results['results']:
        extent_counts.append(result['target_extents'])
        labels.append(result['label'])
        threading_speedups.append(result['averages']['threading_speedup'])
        multiprocessing_speedups.append(result['averages']['multiprocessing_speedup'])
    
    # Plot 1: Speedup vs Fragmentation
    plt.figure(figsize=(12, 6))
    
    x = np.arange(len(extent_counts))
    width = 0.35
    
    plt.bar(x - width/2, threading_speedups, width, label='Threading', alpha=0.8)
    plt.bar(x + width/2, multiprocessing_speedups, width, label='Multiprocessing', alpha=0.8)
    
    # Baseline line at 1.0x
    plt.axhline(y=1.0, color='r', linestyle='--', alpha=0.5, label='Baseline (1.0x)')
    
    plt.xlabel('Fragmentation Level', fontsize=12)
    plt.ylabel('Speedup (vs Sequential)', fontsize=12)
    plt.title('Parallel Speedup vs File Fragmentation Level', fontsize=14, fontweight='bold')
    plt.xticks(x, [f"{e}\n({l})" for e, l in zip(extent_counts, labels)])
    plt.legend()
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    
    plot_file = output_dir / 'fragmentation_speedup.png'
    plt.savefig(plot_file, dpi=300)
    print(f"\n✓ Speedup plot saved to: {plot_file}")
    plt.close()
    
    # Plot 2: Execution Time vs Fragmentation
    plt.figure(figsize=(12, 6))
    
    seq_times = [r['averages']['sequential_time'] for r in results['results']]
    thr_times = [r['averages']['threading_time'] for r in results['results']]
    mp_times = [r['averages']['multiprocessing_time'] for r in results['results']]
    
    x_pos = np.arange(len(extent_counts))
    
    plt.plot(x_pos, seq_times, 'o-', label='Sequential', linewidth=2, markersize=8)
    plt.plot(x_pos, thr_times, 's-', label='Threading (8 workers)', linewidth=2, markersize=8)
    plt.plot(x_pos, mp_times, '^-', label='Multiprocessing (8 workers)', linewidth=2, markersize=8)
    
    plt.xlabel('Fragmentation Level', fontsize=12)
    plt.ylabel('Execution Time (seconds)', fontsize=12)
    plt.title('Execution Time vs File Fragmentation Level', fontsize=14, fontweight='bold')
    plt.xticks(x_pos, [f"{e}\n({l})" for e, l in zip(extent_counts, labels)])
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    
    plot_file = output_dir / 'fragmentation_execution_time.png'
    plt.savefig(plot_file, dpi=300)
    print(f"✓ Execution time plot saved to: {plot_file}")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description='Analyze fragmentation impact benchmark')
    parser.add_argument(
        'json_file',
        type=str,
        help='Path to benchmark results JSON file'
    )
    parser.add_argument(
        '--csv',
        type=str,
        help='Export results to CSV file'
    )
    parser.add_argument(
        '--plot',
        action='store_true',
        help='Generate visualization plots'
    )
    
    args = parser.parse_args()
    
    # Load results
    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"Error: File not found: {json_path}")
        sys.exit(1)
    
    print(f"Loading results from: {json_path}")
    results = load_results(json_path)
    
    # Analyze
    analyze_fragmentation_impact(results)
    
    # Export CSV
    if args.csv:
        csv_path = Path(args.csv)
        export_csv(results, csv_path)
    
    # Generate plots
    if args.plot:
        plot_dir = json_path.parent / 'plots'
        plot_results(results, plot_dir)
    
    print("\n" + "="*80)
    print("Analysis complete!")
    print("="*80 + "\n")


if __name__ == '__main__':
    main()
