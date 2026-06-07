"""Camera platform for Xiaomi isa.camera.hlc6 via Xiaomi Miot action URLs.

This is a narrow proof-of-concept for cameras where Xiaomi Miot Auto can call
MIOT stream actions but its generic CameraEntity stays unavailable.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

CONF_MIOT_ENTITY = "miot_entity"
CONF_QUALITY = "quality"
CONF_ENABLE_STREAM = "enable_stream"
CONF_ENABLE_STREAM_SNAPSHOT = "enable_stream_snapshot"
CONF_STREAM_SNAPSHOT_CACHE_SECONDS = "stream_snapshot_cache_seconds"

DEFAULT_NAME = "Xiaomi HLC6 Camera"
# Keep live streaming disabled by default. Requesting a live stream makes Xiaomi
# Home report that someone is viewing the camera and HA's stream worker can hang
# on this model; snapshots do not need the HLS live-view action.
DEFAULT_ENABLE_STREAM = False
DEFAULT_ENABLE_STREAM_SNAPSHOT = False
DEFAULT_STREAM_SNAPSHOT_CACHE_SECONDS = 600
PLACEHOLDER_SNAPSHOT_MARKERS = ("developer_15414679054o4iwtfd.png",)
# For isa.camera.hlc6, quality 0/auto can produce an empty HLS playlist and
# RTSP fails in Home Assistant's stream worker. Quality 2 returns a valid H.264
# HLS stream in observed tests if enable_stream is explicitly turned on.
DEFAULT_QUALITY = 2  # 0 Auto, 1 1080p, 2 640x360
HLS_STREAM_QUALITY = 2

PLATFORM_SCHEMA = cv.PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_MIOT_ENTITY): cv.entity_id,
        vol.Optional(CONF_QUALITY, default=DEFAULT_QUALITY): vol.In([0, 1, 2]),
        vol.Optional(CONF_ENABLE_STREAM, default=DEFAULT_ENABLE_STREAM): cv.boolean,
        vol.Optional(CONF_ENABLE_STREAM_SNAPSHOT, default=DEFAULT_ENABLE_STREAM_SNAPSHOT): cv.boolean,
        vol.Optional(
            CONF_STREAM_SNAPSHOT_CACHE_SECONDS,
            default=DEFAULT_STREAM_SNAPSHOT_CACHE_SECONDS,
        ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
    }
)


def setup_platform(hass: HomeAssistant, config: dict[str, Any], add_entities, discovery_info=None) -> None:
    """Set up the YAML camera platform."""
    add_entities([
        XiaomiHlc6MiotCamera(
            hass=hass,
            name=config[CONF_NAME],
            miot_entity=config[CONF_MIOT_ENTITY],
            quality=config[CONF_QUALITY],
            enable_stream=config[CONF_ENABLE_STREAM],
            enable_stream_snapshot=config[CONF_ENABLE_STREAM_SNAPSHOT],
            stream_snapshot_cache_seconds=config[CONF_STREAM_SNAPSHOT_CACHE_SECONDS],
        )
    ])


class XiaomiHlc6MiotCamera(Camera):
    """Camera entity backed by Xiaomi Miot HLS/RTSP action outputs."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        miot_entity: str,
        quality: int,
        enable_stream: bool,
        enable_stream_snapshot: bool,
        stream_snapshot_cache_seconds: int,
    ) -> None:
        super().__init__()
        self.hass = hass
        self._attr_name = name
        self._attr_unique_id = f"xiaomi_hlc6_miot_{miot_entity}"
        self._miot_entity = miot_entity
        self._quality = quality
        self._enable_stream = enable_stream
        self._enable_stream_snapshot = enable_stream_snapshot
        self._stream_snapshot_cache_seconds = stream_snapshot_cache_seconds
        self._rtsp_url: str | None = None
        self._snapshot_url: str | None = None
        self._hls_url: str | None = None
        self._expires_at: datetime | None = None
        self._last_image: bytes | None = None
        self._last_image_at: datetime | None = None
        if enable_stream:
            self._attr_supported_features = CameraEntityFeature.STREAM
        else:
            self._attr_supported_features = CameraEntityFeature(0)

    @property
    def available(self) -> bool:
        # The backing Xiaomi Miot camera entity may be unavailable even when
        # actions on button.isa_hlc6_0e54_info work. Keep this entity available.
        return True

    async def _call_miot_action(self, siid: int, aiid: int, params: list[Any] | None = None) -> dict[str, Any]:
        """Call Xiaomi Miot Auto's action service and return its response."""
        data = {
            "entity_id": self._miot_entity,
            "siid": siid,
            "aiid": aiid,
            "params": params or [],
        }
        try:
            response = await self.hass.services.async_call(
                "xiaomi_miot",
                "call_action",
                data,
                blocking=True,
                return_response=True,
            )
        except TypeError:
            # Older HA fallback: no return_response support means this custom
            # platform cannot get the generated URL.
            _LOGGER.exception("Home Assistant service call does not support return_response")
            return {}
        except Exception:
            _LOGGER.exception("Failed to call Xiaomi Miot action siid=%s aiid=%s", siid, aiid)
            return {}

        if isinstance(response, dict):
            # REST wraps it as {service_response: {...}}; internal async_call may
            # return either that wrapper or the direct service response.
            return response.get("service_response") or response
        return {}

    async def _refresh_urls(self) -> None:
        """Refresh cached RTSP/HLS/snapshot URLs from MIOT actions."""
        now = datetime.utcnow()
        if self._expires_at and now < self._expires_at - timedelta(seconds=20):
            return

        if not self._enable_stream:
            # In privacy-first mode, do not call either Alexa RTSP or Google HLS
            # stream actions: both are stream-start actions and can make Xiaomi
            # Home notify that someone is watching. The Alexa "snapshot" output
            # is only a generic Works with Mi Home placeholder on isa.camera.hlc6.
            self._hls_url = None
            self._rtsp_url = None
            self._snapshot_url = None
            self._expires_at = now + timedelta(seconds=self._stream_snapshot_cache_seconds)
            return

        # HLS / Google stream: siid=5 aiid=1 input [quality], output [url].
        # Always request quality 2 for HLS because quality 0/auto can return an
        # empty playlist on isa.camera.hlc6 even if YAML still has quality: 0.
        hls = await self._call_miot_action(5, 1, [HLS_STREAM_QUALITY])
        if hls.get("code") == 0 and hls.get("out"):
            self._hls_url = hls["out"][0]
            _LOGGER.debug("Obtained HLS URL for %s", self.name)
        else:
            _LOGGER.debug("HLS action failed/empty for %s: %s", self.name, hls)

        # RTSP / Alexa stream: siid=4 aiid=1 input [quality], output [rtsp, snapshot, expiration_ms].
        rtsp = await self._call_miot_action(4, 1, [self._quality])
        if rtsp.get("code") == 0 and rtsp.get("out"):
            out = rtsp["out"]
            self._rtsp_url = out[0] if len(out) > 0 else None
            self._snapshot_url = out[1] if len(out) > 1 else None
            if len(out) > 2 and isinstance(out[2], (int, float)):
                self._expires_at = datetime.utcfromtimestamp(out[2] / 1000)
            else:
                self._expires_at = now + timedelta(seconds=60)
            _LOGGER.debug("Obtained RTSP/snapshot URLs for %s; expires at %s", self.name, self._expires_at)
        else:
            _LOGGER.warning("RTSP action failed/empty for %s: %s", self.name, rtsp)
            self._expires_at = now + timedelta(seconds=20)

    async def _async_hls_frame_image(self) -> bytes | None:
        """Capture one JPEG frame from the HLS stream when explicitly enabled."""
        now = datetime.utcnow()
        if (
            self._last_image
            and self._last_image_at
            and now < self._last_image_at + timedelta(seconds=self._stream_snapshot_cache_seconds)
        ):
            return self._last_image

        hls = await self._call_miot_action(5, 1, [HLS_STREAM_QUALITY])
        if hls.get("code") != 0 or not hls.get("out"):
            _LOGGER.warning("HLS action failed/empty for frame snapshot on %s: %s", self.name, hls)
            return None

        hls_url = hls["out"][0]
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                hls_url,
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "pipe:1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            _LOGGER.warning("ffmpeg is not installed; cannot capture HLS frame snapshot for %s", self.name)
            return None
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=45)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            _LOGGER.warning("Timed out capturing HLS frame snapshot for %s", self.name)
            return None

        if proc.returncode != 0 or not stdout:
            _LOGGER.warning(
                "ffmpeg failed capturing HLS frame snapshot for %s: rc=%s stderr=%s",
                self.name,
                proc.returncode,
                stderr.decode(errors="ignore")[:500],
            )
            return None

        self._last_image = stdout
        self._last_image_at = now
        return stdout

    async def stream_source(self) -> str | None:
        """Return a stream URL for Home Assistant stream integration."""
        if not self._enable_stream:
            return None
        await self._refresh_urls()
        # Direct tests showed the HLS action with quality=2 returns a valid H.264
        # playlist, while the RTSP URL opens as a black/broken stream in Home
        # Assistant/FFmpeg. Prefer HLS for playback and keep RTSP only because it
        # also provides the snapshot URL used by async_camera_image().
        return self._hls_url or self._rtsp_url

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        """Return latest snapshot bytes."""
        if self._enable_stream_snapshot:
            return await self._async_hls_frame_image()

        await self._refresh_urls()
        if not self._snapshot_url:
            return None
        if any(marker in self._snapshot_url for marker in PLACEHOLDER_SNAPSHOT_MARKERS):
            _LOGGER.debug("Ignoring generic Xiaomi placeholder snapshot for %s", self.name)
            return None
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(self._snapshot_url, timeout=15) as resp:
                if resp.status != 200:
                    _LOGGER.warning("Snapshot URL returned HTTP %s", resp.status)
                    return None
                return await resp.read()
        except (asyncio.TimeoutError, Exception):
            _LOGGER.exception("Failed to fetch Xiaomi HLC6 snapshot")
            return None
