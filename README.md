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
  - The Alexa snapshot URL responds as `image/png`, but on the tested HLC6 it is
    a generic "Works with Mi Home" placeholder rather than a real still image.
  - Capturing one frame from HLS quality `2` returns a real image, but it starts
    the livestream and may trigger Xiaomi Home's live-view notification.

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
    quality: 2
    enable_stream: false
    enable_stream_snapshot: false
    stream_snapshot_cache_seconds: 600
```

Quality values:

- `0`: Auto
- `1`: 1080p 20 fps
- `2`: 640x360 20 fps

Default privacy-first mode does not call Xiaomi stream actions and will not show
the generic placeholder image. To generate a real still image by briefly opening
the HLS stream, opt in explicitly:

```yaml
camera:
  - platform: xiaomi_hlc6_miot
    name: Cámara Xiaomi HLC6 prueba
    miot_entity: button.isa_hlc6_0e54_info
    quality: 2
    enable_stream: false
    enable_stream_snapshot: true
    stream_snapshot_cache_seconds: 600
```

`enable_stream_snapshot: true` requires `ffmpeg` in the Home Assistant runtime
and can make Xiaomi Home notify that someone is viewing the livestream. Captured
frames are cached for `stream_snapshot_cache_seconds` seconds to reduce repeated
stream starts. The default is 600 seconds (10 minutes); allowed values are
10-3600 seconds.

To refresh immediately from Lovelace or an automation, call:

```yaml
service: homeassistant.update_entity
target:
  entity_id: camera.camara_xiaomi_hlc6_prueba
```

This clears the cached frame and captures a new one on demand.

## Notes

This integration does not implement Xiaomi login. It depends on Xiaomi Miot Auto's existing authenticated service calls.
