#!/usr/bin/env python3
"""
Performance visualization tools
Generate charts and graphs from benchmark results
"""

import sys
import os
import json
from typing import Dict, List

# Try to import matplotlib
try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    MPL_AVAILABLE = True
except ImportError:
    MPL_AVAILABLE = False
    print("Warning: matplotlib not available. Install with: pip install matplotlib")


class PerformanceVisualizer:
    """
    Generate performance visualizations
    
    Creates:
    - Speedup charts
    - Throughput plots
    - Efficiency graphs
    - Memory usage charts
    """
    
    def __init__(self, results_file: str):
        if not MPL_AVAILABLE:
            raise RuntimeError("matplotlib required for visualization")
        
        with open(results_file, 'r') as f:
            self.results = json.load(f)
        
        # Set style
        plt.style.use('seaborn-v0_8-darkgrid')
    
    def plot_strong_scaling(self, output_file: str = 'strong_scaling.png'):
        """Plot strong scaling results"""
        # Filter results for fixed file count
        file_counts = set(r['num_files'] for r in self.results)
        
        # Use most common file count
        target_count = max(file_counts, key=lambda c: 
                          sum(1 for r in self.results if r['num_files'] == c))
        
        data = [r for r in self.results if r['num_files'] == target_count]
        data.sort(key=lambda r: r['num_workers'])
        
        if not data:
            print("No strong scaling data found")
            return
        
        workers = [r['num_workers'] for r in data]
        times = [r['median_time'] for r in data]
        
        # Calculate speedup
        baseline = times[0]
        speedups = [baseline / t for t in times]
        ideal_speedup = workers
        
        # Create figure
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
        
        # Plot 1: Speedup
        ax1.plot(workers, speedups, 'o-', linewidth=2, markersize=8, 
                label='Actual Speedup')
        ax1.plot(workers, ideal_speedup, '--', linewidth=2, alpha=0.7,
                label='Ideal Speedup')
        ax1.set_xlabel('Number of Workers', fontsize=12)
        ax1.set_ylabel('Speedup', fontsize=12)
        ax1.set_title(f'Strong Scaling Speedup\n({target_count} files)', fontsize=14)
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Plot 2: Efficiency
        efficiency = [s / w * 100 for s, w in zip(speedups, workers)]
        ax2.plot(workers, efficiency, 's-', linewidth=2, markersize=8,
                color='orangered')
        ax2.axhline(y=100, color='gray', linestyle='--', alpha=0.7)
        ax2.set_xlabel('Number of Workers', fontsize=12)
        ax2.set_ylabel('Parallel Efficiency (%)', fontsize=12)
        ax2.set_title(f'Parallel Efficiency\n({target_count} files)', fontsize=14)
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Strong scaling plot saved to {output_file}")
        plt.close()
    
    def plot_throughput(self, output_file: str = 'throughput.png'):
        """Plot throughput across different configurations"""
        # Group by worker count
        worker_groups = {}
        for r in self.results:
            workers = r['num_workers']
            if workers not in worker_groups:
                worker_groups[workers] = []
            worker_groups[workers].append(r)
        
        # Create plot
        fig, ax = plt.subplots(figsize=(10, 6))
        
        colors = plt.cm.viridis(np.linspace(0, 1, len(worker_groups)))
        
        for i, (workers, data) in enumerate(sorted(worker_groups.items())):
            data.sort(key=lambda r: r['num_files'])
            files = [r['num_files'] for r in data]
            throughput = [r['median_throughput'] for r in data]
            
            ax.plot(files, throughput, 'o-', linewidth=2, markersize=6,
                   label=f'{workers} workers', color=colors[i])
        
        ax.set_xlabel('Number of Files', fontsize=12)
        ax.set_ylabel('Throughput (files/sec)', fontsize=12)
        ax.set_title('Processing Throughput', fontsize=14)
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.set_xscale('log')
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Throughput plot saved to {output_file}")
        plt.close()
    
    def plot_memory_usage(self, output_file: str = 'memory_usage.png'):
        """Plot memory usage"""
        # Filter results with memory data
        data = [r for r in self.results if 'median_memory_mb' in r]
        
        if not data:
            print("No memory usage data found")
            return
        
        data.sort(key=lambda r: r['num_files'])
        
        files = [r['num_files'] for r in data]
        memory = [r['median_memory_mb'] for r in data]
        workers = [r['num_workers'] for r in data]
        
        # Create plot
        fig, ax = plt.subplots(figsize=(10, 6))
        
        scatter = ax.scatter(files, memory, c=workers, s=100, cmap='viridis',
                           edgecolors='black', linewidth=1, alpha=0.7)
        
        ax.set_xlabel('Number of Files', fontsize=12)
        ax.set_ylabel('Memory Usage (MB)', fontsize=12)
        ax.set_title('Memory Usage vs. Workload Size', fontsize=14)
        ax.grid(True, alpha=0.3)
        
        # Add colorbar
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label('Number of Workers', fontsize=11)
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Memory usage plot saved to {output_file}")
        plt.close()
    
    def create_dashboard(self, output_file: str = 'performance_dashboard.png'):
        """Create comprehensive dashboard"""
        fig = plt.figure(figsize=(16, 10))
        
        # Create grid
        gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)
        
        # Plot 1: Speedup (top-left)
        ax1 = fig.add_subplot(gs[0, 0])
        self._plot_speedup_subplot(ax1)
        
        # Plot 2: Throughput (top-right)
        ax2 = fig.add_subplot(gs[0, 1])
        self._plot_throughput_subplot(ax2)
        
        # Plot 3: Efficiency (bottom-left)
        ax3 = fig.add_subplot(gs[1, 0])
        self._plot_efficiency_subplot(ax3)
        
        # Plot 4: Memory (bottom-right)
        ax4 = fig.add_subplot(gs[1, 1])
        self._plot_memory_subplot(ax4)
        
        # Title
        fig.suptitle('FragPicker Parallel Analysis - Performance Dashboard',
                    fontsize=16, fontweight='bold')
        
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Dashboard saved to {output_file}")
        plt.close()
    
    def _plot_speedup_subplot(self, ax):
        """Helper: plot speedup"""
        # Get strong scaling data
        file_counts = [r['num_files'] for r in self.results]
        target = max(set(file_counts), key=file_counts.count)
        
        data = [r for r in self.results if r['num_files'] == target]
        data.sort(key=lambda r: r['num_workers'])
        
        workers = [r['num_workers'] for r in data]
        times = [r['median_time'] for r in data]
        speedups = [times[0] / t for t in times]
        
        ax.plot(workers, speedups, 'o-', linewidth=2, markersize=8)
        ax.plot(workers, workers, '--', alpha=0.5, label='Ideal')
        ax.set_xlabel('Workers')
        ax.set_ylabel('Speedup')
        ax.set_title('Strong Scaling')
        ax.legend()
        ax.grid(True, alpha=0.3)
    
    def _plot_throughput_subplot(self, ax):
        """Helper: plot throughput"""
        data = sorted(self.results, key=lambda r: r['num_files'])
        files = [r['num_files'] for r in data]
        throughput = [r['median_throughput'] for r in data]
        
        ax.plot(files, throughput, 'o-', linewidth=2, markersize=6)
        ax.set_xlabel('Number of Files')
        ax.set_ylabel('Files/sec')
        ax.set_title('Throughput')
        ax.grid(True, alpha=0.3)
    
    def _plot_efficiency_subplot(self, ax):
        """Helper: plot efficiency"""
        file_counts = [r['num_files'] for r in self.results]
        target = max(set(file_counts), key=file_counts.count)
        
        data = [r for r in self.results if r['num_files'] == target]
        data.sort(key=lambda r: r['num_workers'])
        
        workers = [r['num_workers'] for r in data]
        times = [r['median_time'] for r in data]
        speedups = [times[0] / t for t in times]
        efficiency = [s / w * 100 for s, w in zip(speedups, workers)]
        
        ax.bar(range(len(workers)), efficiency, tick_label=workers)
        ax.axhline(y=100, color='red', linestyle='--', alpha=0.5)
        ax.set_xlabel('Workers')
        ax.set_ylabel('Efficiency (%)')
        ax.set_title('Parallel Efficiency')
        ax.grid(True, alpha=0.3, axis='y')
    
    def _plot_memory_subplot(self, ax):
        """Helper: plot memory"""
        data = [r for r in self.results if 'median_memory_mb' in r]
        
        if not data:
            ax.text(0.5, 0.5, 'No memory data', ha='center', va='center')
            return
        
        data.sort(key=lambda r: r['num_files'])
        files = [r['num_files'] for r in data]
        memory = [r['median_memory_mb'] for r in data]
        
        ax.plot(files, memory, 'o-', linewidth=2, markersize=6, color='orangered')
        ax.set_xlabel('Number of Files')
        ax.set_ylabel('Memory (MB)')
        ax.set_title('Memory Usage')
        ax.grid(True, alpha=0.3)


# Add numpy for some calculations
try:
    import numpy as np
except ImportError:
    np = None
    print("Warning: numpy not available")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Performance visualization')
    parser.add_argument('results_file', help='JSON results file')
    parser.add_argument('--plot', choices=['speedup', 'throughput', 'memory', 'dashboard', 'all'],
                       default='all',
                       help='Plot type to generate')
    
    args = parser.parse_args()
    
    if not MPL_AVAILABLE:
        print("ERROR: matplotlib not installed")
        print("Install with: pip install matplotlib")
        sys.exit(1)
    
    if not os.path.exists(args.results_file):
        print(f"ERROR: Results file not found: {args.results_file}")
        sys.exit(1)
    
    viz = PerformanceVisualizer(args.results_file)
    
    if args.plot == 'all':
        viz.plot_strong_scaling()
        viz.plot_throughput()
        viz.plot_memory_usage()
        viz.create_dashboard()
    elif args.plot == 'speedup':
        viz.plot_strong_scaling()
    elif args.plot == 'throughput':
        viz.plot_throughput()
    elif args.plot == 'memory':
        viz.plot_memory_usage()
    elif args.plot == 'dashboard':
        viz.create_dashboard()