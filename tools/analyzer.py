#!/usr/bin/env python3
"""
Results analysis tool
Analyze and compare FragPicker analysis results
"""

import sys
import os
import json
from typing import Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass


@dataclass
class FileAnalysis:
    """Analysis results for a single file"""
    inode: str
    filepath: str
    extent_count: int
    size: int
    fragmentation_score: float
    is_fragmented: bool


class ResultAnalyzer:
    """
    Analyze FragPicker results
    
    Features:
    - Parse filelist.txt
    - Statistical analysis
    - Fragmentation patterns
    - Comparison with previous runs
    """
    
    def __init__(self, filelist_path: str = "./filelist.txt"):
        self.filelist_path = filelist_path
        self.files: List[FileAnalysis] = []
    
    def load_results(self):
        """Load analysis results from filelist.txt"""
        if not os.path.exists(self.filelist_path):
            print(f"Error: {self.filelist_path} not found")
            return False
        
        with open(self.filelist_path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2:
                    inode = parts[0]
                    req_count = int(parts[1])
                    
                    # Try to get file info
                    try:
                        filepath = self._get_filepath(inode)
                        size = self._get_filesize(filepath)
                        extent_count = self._get_extent_count(inode)
                        
                        frag_score = self._calculate_fragmentation(
                            extent_count, size
                        )
                        
                        file_analysis = FileAnalysis(
                            inode=inode,
                            filepath=filepath,
                            extent_count=extent_count,
                            size=size,
                            fragmentation_score=frag_score,
                            is_fragmented=extent_count > 1
                        )
                        
                        self.files.append(file_analysis)
                    
                    except Exception as e:
                        print(f"Warning: Could not analyze inode {inode}: {e}")
        
        return len(self.files) > 0
    
    def _get_filepath(self, inode: str) -> str:
        """Get filepath from inode"""
        import subprocess
        try:
            result = subprocess.check_output(
                ["find", "/mnt", "-inum", inode],
                text=True,
                stderr=subprocess.DEVNULL
            )
            return result.strip()
        except:
            return f"<unknown:{inode}>"
    
    def _get_filesize(self, filepath: str) -> int:
        """Get file size"""
        try:
            return os.path.getsize(filepath)
        except:
            return 0
    
    def _get_extent_count(self, inode: str) -> int:
        """Get extent count from trace file"""
        trace_file = f"./{inode}.txt"
        if os.path.exists(trace_file):
            with open(trace_file, 'r') as f:
                return sum(1 for _ in f)
        return 0
    
    def _calculate_fragmentation(self, extent_count: int, size: int) -> float:
        """Calculate fragmentation score"""
        if extent_count <= 1:
            return 0.0
        
        if size == 0:
            return 0.0
        
        # Simple scoring: more extents = higher fragmentation
        return min(1.0, (extent_count - 1) * 4096 / size)
    
    def get_statistics(self) -> Dict:
        """Get statistical summary"""
        if not self.files:
            return {}
        
        total_files = len(self.files)
        fragmented_files = sum(1 for f in self.files if f.is_fragmented)
        
        extent_counts = [f.extent_count for f in self.files]
        sizes = [f.size for f in self.files]
        frag_scores = [f.fragmentation_score for f in self.files]
        
        stats = {
            'total_files': total_files,
            'fragmented_files': fragmented_files,
            'fragmentation_rate': fragmented_files / total_files * 100,
            
            'extent_stats': {
                'total': sum(extent_counts),
                'avg': sum(extent_counts) / len(extent_counts),
                'min': min(extent_counts),
                'max': max(extent_counts),
                'median': sorted(extent_counts)[len(extent_counts) // 2]
            },
            
            'size_stats': {
                'total_mb': sum(sizes) / (1024 * 1024),
                'avg_kb': sum(sizes) / len(sizes) / 1024,
                'min': min(sizes),
                'max': max(sizes)
            },
            
            'fragmentation_stats': {
                'avg_score': sum(frag_scores) / len(frag_scores),
                'max_score': max(frag_scores)
            }
        }
        
        return stats
    
    def get_top_fragmented(self, n: int = 10) -> List[FileAnalysis]:
        """Get top N most fragmented files"""
        return sorted(self.files, 
                     key=lambda f: f.fragmentation_score, 
                     reverse=True)[:n]
    
    def get_distribution(self) -> Dict[str, int]:
        """Get extent count distribution"""
        distribution = {}
        
        for file in self.files:
            count = file.extent_count
            
            # Bucket by extent count
            if count == 1:
                bucket = "1 (not fragmented)"
            elif count <= 5:
                bucket = "2-5 (lightly fragmented)"
            elif count <= 10:
                bucket = "6-10 (moderately fragmented)"
            elif count <= 50:
                bucket = "11-50 (heavily fragmented)"
            else:
                bucket = ">50 (severely fragmented)"
            
            distribution[bucket] = distribution.get(bucket, 0) + 1
        
        return distribution
    
    def print_report(self):
        """Print comprehensive analysis report"""
        stats = self.get_statistics()
        
        print("\n" + "=" * 70)
        print("FRAGPICKER ANALYSIS REPORT")
        print("=" * 70)
        
        print(f"\nOverall Statistics:")
        print(f"  Total files analyzed:    {stats['total_files']:,}")
        print(f"  Fragmented files:        {stats['fragmented_files']:,} "
              f"({stats['fragmentation_rate']:.1f}%)")
        
        print(f"\nExtent Statistics:")
        es = stats['extent_stats']
        print(f"  Total extents:           {es['total']:,}")
        print(f"  Average per file:        {es['avg']:.1f}")
        print(f"  Median:                  {es['median']}")
        print(f"  Range:                   {es['min']} - {es['max']}")
        
        print(f"\nFile Size Statistics:")
        ss = stats['size_stats']
        print(f"  Total size:              {ss['total_mb']:.1f} MB")
        print(f"  Average size:            {ss['avg_kb']:.1f} KB")
        
        print(f"\nFragmentation Distribution:")
        dist = self.get_distribution()
        for bucket, count in sorted(dist.items()):
            pct = count / stats['total_files'] * 100
            bar = "█" * int(pct / 2)
            print(f"  {bucket:30s} {count:6,} ({pct:5.1f}%) {bar}")
        
        print(f"\nTop 10 Most Fragmented Files:")
        for i, file in enumerate(self.get_top_fragmented(10), 1):
            print(f"  {i:2d}. {file.extent_count:4d} extents "
                  f"(score: {file.fragmentation_score:.3f}) - {file.filepath}")
        
        print("=" * 70)
    
    def export_json(self, output_file: str = "analysis_report.json"):
        """Export analysis to JSON"""
        data = {
            'statistics': self.get_statistics(),
            'distribution': self.get_distribution(),
            'top_fragmented': [
                {
                    'inode': f.inode,
                    'filepath': f.filepath,
                    'extent_count': f.extent_count,
                    'size': f.size,
                    'fragmentation_score': f.fragmentation_score
                }
                for f in self.get_top_fragmented(50)
            ]
        }
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\nAnalysis exported to {output_file}")
    
    def compare_with(self, other_filelist: str):
        """Compare with another analysis run"""
        print(f"\nComparing with {other_filelist}...")
        
        other = ResultAnalyzer(other_filelist)
        if not other.load_results():
            print("Failed to load comparison file")
            return
        
        stats1 = self.get_statistics()
        stats2 = other.get_statistics()
        
        print("\n" + "=" * 70)
        print("COMPARISON REPORT")
        print("=" * 70)
        
        print(f"\n{'Metric':<30} {'Current':<15} {'Previous':<15} {'Change':<15}")
        print("-" * 70)
        
        # File counts
        print(f"{'Total files':<30} {stats1['total_files']:<15,} "
              f"{stats2['total_files']:<15,} "
              f"{stats1['total_files'] - stats2['total_files']:+15,}")
        
        print(f"{'Fragmented files':<30} {stats1['fragmented_files']:<15,} "
              f"{stats2['fragmented_files']:<15,} "
              f"{stats1['fragmented_files'] - stats2['fragmented_files']:+15,}")
        
        # Averages
        print(f"{'Avg extents/file':<30} {stats1['extent_stats']['avg']:<15.1f} "
              f"{stats2['extent_stats']['avg']:<15.1f} "
              f"{stats1['extent_stats']['avg'] - stats2['extent_stats']['avg']:+15.1f}")
        
        print("=" * 70)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='FragPicker results analyzer')
    parser.add_argument('--filelist', default='./filelist.txt',
                       help='Path to filelist.txt')
    parser.add_argument('--compare', help='Compare with another filelist.txt')
    parser.add_argument('--export', help='Export to JSON file')
    
    args = parser.parse_args()
    
    analyzer = ResultAnalyzer(args.filelist)
    
    if not analyzer.load_results():
        print("Failed to load results")
        sys.exit(1)
    
    analyzer.print_report()
    
    if args.compare:
        analyzer.compare_with(args.compare)
    
    if args.export:
        analyzer.export_json(args.export)