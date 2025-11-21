#!/usr/bin/env python3
"""
Batch inode-to-filepath mapping
Replaces N×find calls with 1×find call
"""

import subprocess
import time
from typing import Dict

def build_inode_map(mount_point: str = "/mnt", verbose: bool = True) -> Dict[str, str]:
    """
    Build inode-to-filepath mapping with single find command
    
    Returns:
        {inode: filepath, ...}
    """
    if verbose:
        print(f"[INodeMapper] Building inode map for {mount_point}...", flush=True)
    
    start_time = time.time()
    inode_map = {}
    
    try:
        # Single find command: find /mnt -type f -printf "%i %p\n"
        result = subprocess.check_output(
            ["find", mount_point, "-type", "f", "-printf", "%i %p\\n"],
            text=True,
            stderr=subprocess.DEVNULL
        )
        
        for line in result.strip().split('\n'):
            if line:
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    inode, path = parts
                    inode_map[inode] = path.strip()
        
        elapsed = time.time() - start_time
        if verbose:
            print(f"[INodeMapper] Built map with {len(inode_map)} files in {elapsed:.2f}s", 
                  flush=True)
        
    except subprocess.CalledProcessError as e:
        if verbose:
            print(f"[INodeMapper] WARNING: find failed: {e}", flush=True)
    
    return inode_map


def lookup_filepath(inode: str, inode_map: Dict[str, str], mount_point: str = None) -> str:
    """
    Look up filepath by inode using prebuilt map
    
    Args:
        inode: The inode number as a string
        inode_map: Dictionary mapping inode to filepath
        mount_point: Optional mount point (not used, for compatibility)
    
    Returns:
        Filepath for the given inode, or None if not found
    """
    return inode_map.get(inode)


if __name__ == '__main__':
    # Test
    inode_map = build_inode_map("/mnt")
    print(f"Sample entries:")
    for inode, path in list(inode_map.items())[:5]:
        print(f"  {inode} -> {path}")