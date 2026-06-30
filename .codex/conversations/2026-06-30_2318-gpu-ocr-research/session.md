# Session 2026-06-30_2318-gpu-ocr-research

## Task

Investigate whether MaaCore GPU OCR can be enabled in this Linux MAA environment, test availability locally, and summarize Docker packaging implications.

## Running Notes

- Session started at 2026-06-30 23:18 UTC.
- Existing project history says the local runtime is `maa-cli v0.7.5` with `MaaCore v6.12.2`, and the default profile currently uses CPU OCR.
- `scripts/maa-env maa version` now reports `maa-cli v0.7.5` and `MaaCore v6.13.0`.
- The current host has both:
  - NVIDIA GeForce RTX 2080 Ti at PCI `0000:0A:00.0`; `nvidia-smi` works with driver `580.126.20`, CUDA version `13.0`, and `/dev/nvidia0`/`/dev/nvidia-uvm` are present.
  - Intel Alder Lake-P integrated GPU at PCI `0000:00:02.0`; `/dev/dri/renderD128` points to it, vendor `0x8086`, device `0x46a6`, driver `i915`.
- Current MaaCore Linux runtime libraries under `runtime/maa/data/maa/lib/` include `libonnxruntime.so.1` and `libfastdeploy_ppocr.so`, but no separate CUDA/OpenVINO/TensorRT ONNX Runtime provider libraries.
- `nm -D runtime/maa/data/maa/lib/libonnxruntime.so.1` shows only `OrtSessionOptionsAppendExecutionProvider_CPU`; no exported CUDA/DML/OpenVINO/TensorRT append provider symbols were found.
- Temporary maa-cli configs were created under `scratch/maa-config/`:
  - `profiles/cpu.toml`: `cpu_ocr = true`
  - `profiles/gpu0.toml`: `cpu_ocr = false`, `gpu_ocr = 0`
  - `profiles/gpu1.toml`: `cpu_ocr = false`, `gpu_ocr = 1`
  - `tasks/startup-smoke.toml`: StartUp with `start_game_enabled = false`
- Dry-run tests:
  - CPU: `maa run startup-smoke --batch --dry-run --profile cpu -vvv --log-file=scratch/logs/dryrun-cpu.log` succeeded; maa-cli log says `Using CPU OCR`; MaaCore log says `CPU OCR enabled with 4 threads`.
  - GPU 0: same command with `--profile gpu0` succeeded at config/CLI layer; maa-cli log says `Using GPU OCR with GPU ID 0`; MaaCore log says `set_static_option | key 2 value 0` followed by `use_gpu No GPU execution provider available`.
  - GPU 1: same command with `--profile gpu1` succeeded at config/CLI layer; MaaCore log says `set_static_option | key 2 value 1` followed by `use_gpu No GPU execution provider available`.
- Scratch evidence files:
  - `scratch/logs/dryrun-cpu.log`
  - `scratch/logs/dryrun-gpu0.log`
  - `scratch/logs/dryrun-gpu1.log`
  - `scratch/asst-cpu-dryrun.log`
  - `scratch/asst-gpu0-dryrun.log`

## Conclusion Draft

- The static config supports GPU OCR syntax, but the current Linux MaaCore runtime cannot actually enable GPU OCR on either the NVIDIA GPU or Intel iGPU.
- Failure reason is not GPU absence: both GPUs are visible to the host. The current packaged ONNX/FastDeploy stack does not expose a usable GPU execution provider to MaaCore.
