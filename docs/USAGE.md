# Usage reference

Back to the [README](../README.md).

## `processing.py` options

Run from `src/analysis`:

```text
python3 processing.py [OPTIONS]

  --parallel              Process files with the parallel engine
  --workers N             Number of workers (auto-tuned when omitted)
  --mount-point PATH      Mount point to search (default: /mnt)
  --dashboard             Show a terminal dashboard while running
  --profile               Collect profiling data
  --benchmark             Compare sequential and parallel on the current trace
  --config FILE           Load a YAML configuration file
  --quiet                 Suppress non-error output
```

Run with no arguments, the script takes the original sequential path on `/mnt`.

Environment variables read in parallel mode: `FRAGPICKER_WORKERS`, `FRAGPICKER_MOUNT_POINT`.

## Configuration file

[`config/default.yaml`](../config/default.yaml) lists every setting with its default, for example:

```yaml
parallel:
  num_workers: 8
  auto_detect_cores: true

fiemap:
  max_extents_per_call: 32
  retry_attempts: 3

logging:
  level: "INFO"
  file_path: null
```

Note: `--config` loads the file, but `--parallel` then builds its configuration from environment variables and `--workers` (`process_trace_parallel` in `src/analysis/processing.py`). A YAML file passed with `--config` does not change a `--parallel` run. Use `--workers` or `FRAGPICKER_WORKERS` for the worker count.

## Using the modules directly

Run from `src/analysis` so that `parallel_analyzer` can be imported.

```python
from parallel_analyzer.fiemap import FiemapAnalyzer
from parallel_analyzer.inode_mapper import build_inode_map
from parallel_analyzer.parallel_processor import EnhancedParallelProcessor

extents = FiemapAnalyzer().get_extents("/path/to/file")

inode_map = build_inode_map("/mnt")        # one find over the mount point

processor = EnhancedParallelProcessor(num_workers=8, mount_point="/mnt")
result = processor.process_files(file_list)   # file_list: (inode, request_count) pairs
```

[`benchmarks/speedup_benchmark.py`](../benchmarks/speedup_benchmark.py) shows a complete call.

## Tools

| Script | Purpose |
|---|---|
| `tools/analyzer.py --filelist FILE` | Summarize a `filelist.txt`; `--compare` and `--export` are also available |
| `tools/dashboard.py --mode web\|terminal` | Dashboard for analysis runs |
| `tools/profiler.py --interactive` or `--demo` | Interactive profiler |

## Troubleshooting

- `Module not found: parallel_analyzer`: run from `src/analysis`.
- FIEMAP errors: the filesystem or kernel may not support FIEMAP (Linux 2.6.28 or later is required). Try ext4.
- `ERROR: Parallel mode requested but optimization modules not found`: an import in `parallel_analyzer` failed, most often PyYAML. Run `pip install pyyaml`.
- Parallel mode is not faster: expected on fast local storage. See the results in the [README](../README.md#results).
