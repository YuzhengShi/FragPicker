#!/bin/bash
# FragPicker Trace Script
# $1: process name (required)
# Uses BCC tools to trace vfs_read and vfs_write system calls

set -euo pipefail  # Exit on error, undefined variables, pipe failures

# Color codes for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print error messages
error() {
    echo -e "${RED}Error:${NC} $1" >&2
    exit 1
}

# Function to print warning messages
warning() {
    echo -e "${YELLOW}Warning:${NC} $1" >&2
}

# Validate arguments
if [ $# -lt 1 ]; then
    error "Usage: $0 <process_name>"
    exit 1
fi

PROCESS_NAME="$1"

# Validate process name
if [ -z "$PROCESS_NAME" ]; then
    error "Process name cannot be empty"
fi

# Check if BCC tools are available
BCC_TRACE="/usr/share/bcc/tools/trace"
if [ ! -f "$BCC_TRACE" ]; then
    error "BCC trace tool not found at: $BCC_TRACE"
fi

if [ ! -x "$BCC_TRACE" ]; then
    error "BCC trace tool is not executable: $BCC_TRACE"
fi

# Check if process exists (optional check)
if ! pgrep -f "$PROCESS_NAME" > /dev/null 2>&1; then
    warning "No running process found matching: $PROCESS_NAME"
    warning "Tracing will start when the process appears"
fi

# Get script directory and set output file
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_FILE="$SCRIPT_DIR/trace.result"

cd "$SCRIPT_DIR"

# Ensure output file is writable
touch "$OUTPUT_FILE" || error "Cannot write to trace.result"
chmod 644 "$OUTPUT_FILE" || true

# Sanitize process name for safety (basic check)
if [[ "$PROCESS_NAME" =~ [;&|`\$] ]]; then
    error "Invalid characters in process name (security check failed)"
fi

# Start tracing vfs_read
# Trace format: ino = inode | size = size | pos = position | direct = O_DIRECT flag | type = 0 (read)
if ! "$BCC_TRACE" -n "$PROCESS_NAME" \
    'vfs_read(struct file *file, char __user *buf, size_t count, loff_t *pos) \
    "ino = %llu | size = %llu | pos = %u | direct = %d | type = 0", \
    file->f_inode->i_ino, count, *pos, file->f_flags & O_DIRECT' \
    >> "$OUTPUT_FILE" 2>&1 &; then
    
    error "Failed to start vfs_read tracing"
fi

READ_TRACE_PID=$!

# Start tracing vfs_write
# Trace format: ino = inode | size = size | pos = position | direct = O_DIRECT flag | type = 1 (write)
if ! "$BCC_TRACE" -n "$PROCESS_NAME" \
    'vfs_write(struct file *file, char __user *buf, size_t count, loff_t *pos) \
    "ino = %llu | size = %llu | pos = %u | direct = %d | type = 1", \
    file->f_inode->i_ino, count, *pos, file->f_flags & O_DIRECT' \
    >> "$OUTPUT_FILE" 2>&1 &; then
    
    # Clean up read trace if write trace fails
    kill "$READ_TRACE_PID" 2>/dev/null || true
    error "Failed to start vfs_write tracing"
fi

WRITE_TRACE_PID=$!

# Wait a moment and verify both processes are running
sleep 1
if ! kill -0 "$READ_TRACE_PID" 2>/dev/null; then
    kill "$WRITE_TRACE_PID" 2>/dev/null || true
    error "Read trace process died unexpectedly"
fi

if ! kill -0 "$WRITE_TRACE_PID" 2>/dev/null; then
    kill "$READ_TRACE_PID" 2>/dev/null || true
    error "Write trace process died unexpectedly"
fi

# Both traces are running successfully
# The parent script (analyze.sh) will handle stopping these processes
