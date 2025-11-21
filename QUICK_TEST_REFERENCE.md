# Quick Test Reference - FragPicker Parallel

Quick commands to run all tests and benchmarks.

---

## 🧪 Core Test Suites

```bash
# Run all core tests
python tests/test_correctness.py      # 13 tests - Core functionality
python tests/test_parallel.py         # 13 tests - Threading parallelism  
python tests/test_stress.py           # 9 tests  - High-load scenarios
python tests/test_fiemap.py           # 5 tests  - FIEMAP validation
python tests/test_edge_cases.py       # 8 tests  - Boundary conditions
```

## 🆕 New Integration Tests

```bash
# End-to-end workflows (8 tests)
python tests/test_integration_e2e.py

# Adaptive worker selection (7 tests)
python tests/test_adaptive_parallelism.py
```

## 📊 Performance Benchmarks

```bash
# Fast I/O benchmarks (your SSD)
python benchmarks/speedup_benchmark.py
python benchmarks/scalability_test.py
python benchmarks/memory_profiler.py

# Slow I/O benchmarks (1ms delay simulation)
python benchmarks/speedup_slow_io_benchmark.py
python benchmarks/scalability_slow_io_test.py
```

## 🚀 Run Everything

```bash
# All tests at once
python tests/test_correctness.py && \
python tests/test_parallel.py && \
python tests/test_stress.py && \
python tests/test_fiemap.py && \
python tests/test_edge_cases.py && \
python tests/test_integration_e2e.py && \
python tests/test_adaptive_parallelism.py

echo "✅ All tests passed!"
```

## 📈 Quick Benchmark Run

```bash
# Fast comparison (2 min)
python benchmarks/speedup_benchmark.py
python benchmarks/speedup_slow_io_benchmark.py

# Full comparison (10 min)
python benchmarks/scalability_test.py
python benchmarks/scalability_slow_io_test.py
```

---

## 📋 Test Results Summary

### Expected Results:

**Fast I/O (SSD)**:
- Single-thread: ~11,000 files/sec ⚡
- 8 workers: ~4,000 files/sec (0.38x speedup)
- Conclusion: Overhead dominates

**Slow I/O (1ms delay)**:
- Single-thread: ~400 files/sec
- 8 workers threading: ~1,700 files/sec (4.2x speedup) 🚀
- 8 workers multiprocess: ~2,900 files/sec (6.6x speedup) 🎉
- Conclusion: Parallelism wins!

**Memory**:
- Per file: 5.4 KB
- 1000 files: 22.7 MB
- No leaks detected ✅

---

## 🎯 What Each Test Does

### Core Tests:
- **test_correctness.py**: Basic functionality validation
- **test_parallel.py**: Worker count scaling (1-16 workers)
- **test_stress.py**: Large datasets (5000 files)
- **test_fiemap.py**: FIEMAP ioctl correctness
- **test_edge_cases.py**: Empty files, large files, edge cases

### New Integration Tests:
- **test_integration_e2e.py**: Real-world scenarios
  - Nested directories
  - Mixed file sizes
  - Error recovery
  - Concurrent processing
  
- **test_adaptive_parallelism.py**: Smart optimization
  - I/O speed measurement
  - Worker recommendation
  - Speedup prediction

### Benchmarks:
- **speedup_benchmark.py**: Fast I/O speedup analysis
- **speedup_slow_io_benchmark.py**: Slow I/O speedup analysis
- **scalability_test.py**: Comprehensive scaling (fast I/O)
- **scalability_slow_io_test.py**: Comprehensive scaling (slow I/O)
- **memory_profiler.py**: Memory usage profiling

---

## 💡 Tips

### Quick Validation:
```bash
# Just test correctness (30 sec)
python tests/test_correctness.py
```

### Full Validation:
```bash
# All tests + benchmarks (15 min)
python tests/test_correctness.py && \
python tests/test_parallel.py && \
python tests/test_integration_e2e.py && \
python benchmarks/speedup_slow_io_benchmark.py
```

### Performance Comparison:
```bash
# Compare fast vs slow I/O (5 min)
echo "=== Fast I/O (your SSD) ==="
python benchmarks/speedup_benchmark.py

echo ""
echo "=== Slow I/O (simulated HDD) ==="
python benchmarks/speedup_slow_io_benchmark.py
```

---

## ✅ Expected Test Output

All tests should show:
```
----------------------------------------------------------------------
Ran N tests in X.XXXs

OK
```

If you see `FAILED` or `ERROR`, check:
1. Virtual environment activated
2. All dependencies installed
3. Sufficient disk space
4. No permission issues

---

## 🐛 Troubleshooting

### Tests hanging?
- Check for deadlock in worker threads
- Verify poison pill handling
- Check queue.task_done() calls

### Tests failing?
- Ensure .venv is activated
- Check Python version (3.10+)
- Verify filesystem supports FIEMAP

### Slow performance?
- Check disk I/O (use `iostat`)
- Verify no background processes
- Check CPU usage

---

## 📚 Documentation

- **ADDITIONAL_TESTING_RECOMMENDATIONS.md**: Full testing strategy
- **TEST_SUMMARY_REPORT.md**: Comprehensive results
- **PARALLEL_PERFORMANCE_ANALYSIS.md**: Performance deep dive
- **TESTING_STRATEGY.md**: Test suite comparison

---

Ready to test! 🚀
