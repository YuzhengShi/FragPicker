#!/usr/bin/env python3
"""
Interactive profiler for FragPicker
Real-time performance monitoring and analysis
"""

import sys
import os
import time
import threading
from typing import Optional, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src', 'analysis'))

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from parallel_analyzer.performance_analyzer import PerformanceAnalyzer


class InteractiveProfiler:
    """
    Interactive profiler with real-time monitoring
    
    Features:
    - Live CPU/memory monitoring
    - Function call tracking
    - Bottleneck detection
    - Export reports
    """
    
    def __init__(self):
        self.analyzer = PerformanceAnalyzer()
        self.monitor_thread: Optional[threading.Thread] = None
        self.monitoring = False
        
        self.samples = []
        
        if not PSUTIL_AVAILABLE:
            print("Warning: psutil not available, resource monitoring disabled")
    
    def start_monitoring(self):
        """Start background resource monitoring"""
        if not PSUTIL_AVAILABLE:
            return
        
        self.monitoring = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_resources,
            daemon=True
        )
        self.monitor_thread.start()
        
        print("Resource monitoring started")
    
    def stop_monitoring(self):
        """Stop background monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        
        print("Resource monitoring stopped")
    
    def _monitor_resources(self):
        """Background monitoring loop"""
        process = psutil.Process()
        
        while self.monitoring:
            try:
                sample = {
                    'timestamp': time.time(),
                    'cpu_percent': process.cpu_percent(interval=0.1),
                    'memory_mb': process.memory_info().rss / (1024 * 1024),
                    'num_threads': process.num_threads()
                }
                
                self.samples.append(sample)
                
                time.sleep(0.5)
            
            except Exception as e:
                print(f"Monitoring error: {e}")
                break
    
    def profile_function(self, func, *args, **kwargs):
        """Profile a function call"""
        print(f"\nProfiling: {func.__name__}")
        print("-" * 60)
        
        # Start monitoring
        self.start_monitoring()
        
        # Time function
        start = time.time()
        
        with self.analyzer.time_block(func.__name__):
            result = func(*args, **kwargs)
        
        elapsed = time.time() - start
        
        # Stop monitoring
        self.stop_monitoring()
        
        print(f"Execution time: {elapsed:.2f}s")
        
        return result
    
    def print_resource_summary(self):
        """Print resource usage summary"""
        if not self.samples:
            print("No resource samples collected")
            return
        
        cpu_values = [s['cpu_percent'] for s in self.samples]
        mem_values = [s['memory_mb'] for s in self.samples]
        
        print("\n" + "=" * 60)
        print("RESOURCE USAGE SUMMARY")
        print("=" * 60)
        
        print(f"\nCPU Usage:")
        print(f"  Average: {sum(cpu_values) / len(cpu_values):.1f}%")
        print(f"  Peak:    {max(cpu_values):.1f}%")
        print(f"  Min:     {min(cpu_values):.1f}%")
        
        print(f"\nMemory Usage:")
        print(f"  Average: {sum(mem_values) / len(mem_values):.1f} MB")
        print(f"  Peak:    {max(mem_values):.1f} MB")
        print(f"  Min:     {min(mem_values):.1f} MB")
        
        print(f"\nSamples: {len(self.samples)}")
        print("=" * 60)
    
    def print_performance_report(self):
        """Print detailed performance report"""
        self.analyzer.print_report()
    
    def export_chrome_trace(self, filename: str = "trace.json"):
        """Export Chrome trace"""
        self.analyzer.export_chrome_trace(filename)
        print(f"\nChrome trace exported to {filename}")
        print("View at chrome://tracing")
    
    def interactive_session(self):
        """Run interactive profiling session"""
        print("\n" + "=" * 60)
        print("FRAGPICKER INTERACTIVE PROFILER")
        print("=" * 60)
        print("\nCommands:")
        print("  start     - Start monitoring")
        print("  stop      - Stop monitoring")
        print("  report    - Print performance report")
        print("  resources - Print resource summary")
        print("  export    - Export Chrome trace")
        print("  quit      - Exit")
        print()
        
        while True:
            try:
                cmd = input("profiler> ").strip().lower()
                
                if cmd == 'start':
                    self.start_monitoring()
                
                elif cmd == 'stop':
                    self.stop_monitoring()
                
                elif cmd == 'report':
                    self.print_performance_report()
                
                elif cmd == 'resources':
                    self.print_resource_summary()
                
                elif cmd == 'export':
                    filename = input("Filename (trace.json): ").strip() or "trace.json"
                    self.export_chrome_trace(filename)
                
                elif cmd == 'quit' or cmd == 'exit':
                    break
                
                elif cmd == 'help':
                    print("\nCommands: start, stop, report, resources, export, quit")
                
                elif cmd:
                    print(f"Unknown command: {cmd}")
            
            except KeyboardInterrupt:
                print("\n\nExiting...")
                break
            except EOFError:
                break
        
        # Cleanup
        self.stop_monitoring()


def profile_processing_py():
    """Profile processing.py execution"""
    profiler = InteractiveProfiler()
    
    print("Profiling processing.py...")
    
    # This would actually run processing.py
    # For demo, we'll simulate
    profiler.start_monitoring()
    
    print("Simulating processing...")
    time.sleep(5)  # Simulate work
    
    profiler.stop_monitoring()
    profiler.print_resource_summary()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='FragPicker profiler')
    parser.add_argument('--interactive', action='store_true',
                       help='Run interactive session')
    parser.add_argument('--demo', action='store_true',
                       help='Run demo profiling')
    
    args = parser.parse_args()
    
    if not PSUTIL_AVAILABLE:
        print("Warning: psutil not installed, some features disabled")
        print("Install with: pip install psutil")
    
    profiler = InteractiveProfiler()
    
    if args.interactive:
        profiler.interactive_session()
    elif args.demo:
        profile_processing_py()
    else:
        print("Usage: profiler.py --interactive  (or --demo)")