# Repository layout

Back to the [README](../README.md).

```text
src/analysis/
  processing.py                 per-file analysis; --parallel mode added in this fork
  parallel_analyzer/            added in this fork
    fiemap.py                   FIEMAP ioctl wrapper (ctypes) with retry and error handling
    inode_mapper.py             one find to build an inode-to-path map
    parallel_processor.py       thread engine
    multiprocess_processor.py   process engine
    parallel_sorter.py          parallel sort of per-file results
    config.py, logger.py        configuration and structured logging
    performance_analyzer.py     profiling
    progress_monitor.py         progress bars and resource monitor
  trace.sh, parse.sh, merge.py, hotness.sh, ...   upstream scripts
src/migration/                  upstream migration phase (FragPicker_OP.py, FragPicker_IP.py, ...)
tests/                          unit, correctness, stress and slow-I/O tests
benchmarks/                     benchmark scripts
benchmark_results/              raw JSON and charts from the runs in the README
tools/                          analyzer.py, dashboard.py, profiler.py
config/default.yaml             default configuration
requirements.txt                Python packages (PyYAML and psutil needed, others optional)
evaluation/, etc/, slides/      upstream experiments, macOS notes and slides
```

## Benchmark scripts

| Script | Measures |
|---|---|
| `speedup_benchmark.py` | speedup without added delay |
| `speedup_slow_io_benchmark.py` | speedup with 1 ms added per file |
| `scalability_test.py` | strong, weak, file-size and load scaling (`--test`) |
| `scalability_slow_io_test.py` | scaling with 1 ms added per file |
| `overhead_profiling_benchmark.py` | time per component |
| `memory_profiler.py` | memory use |
| `fragmentation_impact_benchmark.py` | effect of fragmentation level |
| `workload_threshold_benchmark.py` | where parallelism starts to pay |
| `end_to_end_workflow_benchmark.py` | whole analysis workflow |
| `analyze_fragmentation.py` | plots from the fragmentation-impact results |

## Tests

| File | Covers |
|---|---|
| `test_fiemap.py` | FIEMAP wrapper |
| `test_parallel.py`, `test_multiprocess_comparison.py` | parallel engines, threads against processes |
| `test_correctness.py`, `test_correctness_validation.py`, `test_sorting_verification.py` | parallel output against sequential |
| `test_stress.py`, `test_stress_slow_io.py`, `test_slow_io_proof.py` | large workloads and added delay |
| `test_edge_cases.py`, `test_filesystem_compatibility.py` | edge cases and filesystems |
| `test_integration_e2e.py`, `test_realistic_workload.py` | end to end |
| `test_adaptive_parallelism.py` | a worker-count selector defined inside the test file |
