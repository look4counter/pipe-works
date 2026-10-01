# Pipe Works Examples

These examples show the intended SDK developer experience. Most use local
synthetic or descriptor sources so they run without cameras, GPUs, brokers, or
RTSP servers.

Recommended reading order:

1. `01_single_stream_rtsp_style.py` - production-shaped single stream DSL.
2. `02_multistream_batch.py` - nine-channel batch inference declaration.
3. `03_multistage_inference.py` - primary model, crop, secondary model.
4. `04_custom_component.py` - domain-specific processor extension.
5. `05_local_synthetic_config.py` - local source plus YAML configuration.

Legacy NVIDIA hook examples remain for backup/reference while the new SDK grows.
