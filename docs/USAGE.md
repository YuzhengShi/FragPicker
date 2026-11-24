# Usage reference

Back to the [README](../README.md).

## `processing.py` options

Run from `src/analysis`:

```text
python3 processing.py [OPTIONS]

  --parallel              Process files with the parallel engine
  --workers N             Number of workers (auto-tuned when omitted)
  --mount-point PATH      Mount point to search (default: /mnt)
  --dashboard             Show a terminal dashboard while running (needs tools/dashboard.py)
  --profile               Collect profiling data
  --benchmark             Compare sequential and parallel on the current trace
  --config FILE           Load a YAML configuration file
  --quiet                 Suppress non-error output
```

Run with no arguments, the script takes the original sequential path on `/mnt`.

Environment variables: `FRAGPICKER_LOG_LEVEL` sets the log level. `FRAGPICKER_WORKERS` and `FRAGPICKER_MOUNT_POINT` are read into the configuration but change nothing in `processing.py`; use `--workers` and `--mount-point`. (The migration scripts read `FRAGPICKER_MOUNT_POINT` themselves.)

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

`--config` applies to `--parallel` and `--benchmark` runs; a sequential run reads no configuration. The file is the base configuration of the run. Without `--config`, the base is the defaults plus the `FRAGPICKER_*` environment variables, which a file replaces. `--workers N` overrides `parallel.num_workers`. Without `--workers`, auto-tuning runs (`Config.auto_tune`): while `parallel.auto_detect_cores` is true (the default) it sets the worker count from the CPU count and ignores `num_workers`, so set `auto_detect_cores: false` to use the value in the file; it also lowers `queue_size` to 1000 when under 4 GB of memory is available.

The code reads only some of the keys: `parallel` (`num_workers`, `auto_detect_cores`, `max_workers`, `enable_hyperthreading`, `queue_size`) and `fiemap` (`max_extents_per_call`, `retry_attempts`, `retry_delay_ms`). The other keys in `config/default.yaml` have no effect on a run. That includes `mount_point` (use `--mount-point`) and the `logging` section, because the loggers are created when the modules are imported, before the file is read (use `FRAGPICKER_LOG_LEVEL`).

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
- `ERROR: Parallel mode requested but optimization modules not found`: an import in `parallel_analyzer` failed, most often a missing package (PyYAML or psutil). Run `pip install -r requirements.txt`.
- Parallel mode is not faster: expected on fast local storage. See the results in the [README](../README.md#results).
