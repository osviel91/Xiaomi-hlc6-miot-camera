# Xiaomi HLC6 Miot Camera

Proof-of-concept Home Assistant custom integration for Xiaomi `isa.camera.hlc6` cameras.

It uses an existing Xiaomi Miot Auto entity and calls MIOT stream actions to expose a `camera.*` entity.

## Current status

Experimental. Built specifically after testing one `isa.camera.hlc6` camera where:

- Xiaomi Home exposed controls but no usable `camera.*` entity.
- Xiaomi Miot Auto created `camera.isa_hlc6_0e54_camera_control`, but it stayed `unavailable`.
- Direct MIOT actions returned:
  - HLS URL via `siid=5`, `aiid=1`.
  - RTSP URL + snapshot URL via `siid=4`, `aiid=1`.
  - Snapshot URL responded as `image/png`.

## Requirements

- Home Assistant 2026.6 or newer tested.
- Xiaomi Miot Auto installed and configured.
- A working Xiaomi Miot entity for the camera, e.g. `button.isa_hlc6_0e54_info`.

## HACS installation

Add this repository as a custom repository in HACS:

1. HACS → Integrations → three-dot menu → Custom repositories.
2. Repository: this repository URL.
3. Category: Integration.
4. Install `Xiaomi HLC6 Miot Camera`.
5. Restart Home Assistant.

## YAML configuration

Add to `configuration.yaml`:

```yaml
camera:
  - platform: xiaomi_hlc6_miot
    name: Cámara Xiaomi HLC6 prueba
    miot_entity: button.isa_hlc6_0e54_info
    quality: 0
    enable_stream: true
```

Quality values:

- `0`: Auto
- `1`: 1080p 20 fps
- `2`: 640x360 20 fps

If stream does not work, try snapshot-only mode:

```yaml
camera:
  - platform: xiaomi_hlc6_miot
    name: Cámara Xiaomi HLC6 prueba
    miot_entity: button.isa_hlc6_0e54_info
    quality: 0
    enable_stream: false
```

## Notes

This integration does not implement Xiaomi login. It depends on Xiaomi Miot Auto's existing authenticated service calls.
