#!/bin/bash
# FragPicker Analysis Script
# $1: process name (required)
# $2: hotness percentage (optional, default: 100)

set -euo pipefail  # Exit on error, undefined variables, pipe failures

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
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

# Function to print info messages
info() {
    echo -e "${GREEN}Info:${NC} $1"
}

# Validate arguments
if [ $# -lt 1 ]; then
    error "Usage: $0 <process_name> [hotness_percentage]"
    exit 1
fi

PROCESS_NAME="$1"
HOTNESS_PERCENT="${2:-100}"

# Validate process name
if [ -z "$PROCESS_NAME" ]; then
    error "Process name cannot be empty"
fi

# Validate hotness percentage
if ! [[ "$HOTNESS_PERCENT" =~ ^[0-9]+$ ]] || [ "$HOTNESS_PERCENT" -lt 1 ] || [ "$HOTNESS_PERCENT" -gt 100 ]; then
    error "Hotness percentage must be between 1 and 100, got: $HOTNESS_PERCENT"
fi

# Check if required scripts exist
REQUIRED_SCRIPTS=("remove.sh" "trace.sh" "parse.sh" "hotness.sh")
for script in "${REQUIRED_SCRIPTS[@]}"; do
    if [ ! -f "$script" ]; then
        error "Required script not found: $script"
    fi
    if [ ! -x "$script" ]; then
        warning "Script not executable: $script (attempting to fix)"
        chmod +x "$script" || error "Failed to make $script executable"
    fi
done

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

info "Starting FragPicker analysis for process: $PROCESS_NAME"
info "Hotness percentage: $HOTNESS_PERCENT%"

# Step 1: Remove old trace files
info "Step 1: Cleaning up old trace files..."
if ! ./remove.sh; then
    error "Failed to remove old trace files"
fi

# Step 2: Start tracing
info "Step 2: Starting I/O tracing..."
if ! ./trace.sh "$PROCESS_NAME" &; then
    error "Failed to start tracing"
fi

TRACE_PID=$!
sleep 5

# Verify trace process is still running
if ! kill -0 "$TRACE_PID" 2>/dev/null; then
    error "Trace process died unexpectedly"
fi

# Step 3: Wait and stop tracing
sleep 3
info "Step 3: Stopping tracing..."

# Try graceful termination first
if kill -INT "$TRACE_PID" 2>/dev/null; then
    sleep 2
    # Check if process is still running
    if kill -0 "$TRACE_PID" 2>/dev/null; then
        warning "Trace process didn't stop, forcing termination"
        kill -TERM "$TRACE_PID" 2>/dev/null || true
        sleep 1
        kill -KILL "$TRACE_PID" 2>/dev/null || true
    fi
fi

# Clean up any remaining trace processes
sleep 2
TRACE_PROCS=$(pgrep -f "trace.*$PROCESS_NAME" || true)
if [ -n "$TRACE_PROCS" ]; then
    warning "Cleaning up remaining trace processes"
    echo "$TRACE_PROCS" | xargs kill -TERM 2>/dev/null || true
    sleep 1
    echo "$TRACE_PROCS" | xargs kill -KILL 2>/dev/null || true
fi

# Step 4: Parse trace results
info "Step 4: Parsing trace results..."
if ! ./parse.sh; then
    error "Failed to parse trace results"
fi

# Step 5: Process trace files
info "Step 5: Processing trace files..."
if ! python3 ./processing.py; then
    error "Failed to process trace files"
fi

# Step 6: Merge overlapping I/Os
info "Step 6: Merging overlapping I/Os..."
if ! python3 ./merge.py; then
    error "Failed to merge overlapping I/Os"
fi

# Step 7: Apply hotness filtering
info "Step 7: Applying hotness filtering ($HOTNESS_PERCENT%)..."
if ! ./hotness.sh "$HOTNESS_PERCENT"; then
    error "Failed to apply hotness filtering"
fi

info "Analysis complete successfully!"
