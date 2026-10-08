from __future__ import annotations

import pytest

from app.core.errors import ProcessingError
from app.core.logging import redact
from app.services.media.probe import parse_probe_output, sniff_container
from app.services.media.render import (
    RenderSpec,
    build_render_command,
    build_video_filter,
    compute_geometry,
)
from app.services.storage.base import validate_key


def test_sniff_container() -> None:
    assert sniff_container(b"\x00\x00\x00\x18ftypmp42\x00\x00") == "video/mp4"
    assert sniff_container(b"\x00\x00\x00\x14ftypqt  \x00\x00") == "video/quicktime"
    assert sniff_container(b"\x1a\x45\xdf\xa3\x01\x00\x00\x00") == "video/webm"
    assert sniff_container(b"<html><body>") is None
    assert sniff_container(b"MZ\x90\x00") is None
    assert sniff_container(b"") is None


def test_parse_probe_rotation_and_audio() -> None:
    info = parse_probe_output(
        {
            "format": {"duration": "61.5", "format_name": "mov,mp4", "bit_rate": "1000"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "30000/1001",
                    "side_data_list": [{"rotation": -90}],
                },
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
    )
    assert (info.width, info.height) == (1080, 1920)  # display orientation
    assert info.fps == 29.97 and info.has_audio and info.duration == 61.5


def test_parse_probe_errors() -> None:
    with pytest.raises(ProcessingError) as e:
        parse_probe_output({"format": {"duration": "5"}, "streams": [{"codec_type": "audio"}]})
    assert e.value.code == "NO_VIDEO_STREAM"
    with pytest.raises(ProcessingError) as e:
        parse_probe_output(
            {"format": {}, "streams": [{"codec_type": "video", "width": 10, "height": 10}]}
        )
    assert e.value.code == "INVALID_DURATION"


@pytest.mark.parametrize(
    ("sw", "sh", "ratio", "expected"),
    [
        (1920, 1080, "9:16", (606, 1080, 657, 0, 606, 1080)),
        (3840, 2160, "9:16", (1214, 2160, 1313, 0, 1080, 1920)),
        (1920, 1080, "1:1", (1080, 1080, 420, 0, 1080, 1080)),
        (1080, 1920, "16:9", (1080, 606, 0, 657, 1080, 606)),
        (1080, 1920, "9:16", (1080, 1920, 0, 0, 1080, 1920)),
    ],
)
def test_geometry(sw: int, sh: int, ratio: str, expected: tuple[int, ...]) -> None:
    g = compute_geometry(
        RenderSpec(start=0, end=1, source_width=sw, source_height=sh, aspect_ratio=ratio)
    )  # type: ignore[arg-type]
    assert (g.crop_w, g.crop_h, g.crop_x, g.crop_y, g.out_w, g.out_h) == expected
    assert g.out_w % 2 == 0 and g.out_h % 2 == 0


def test_crop_position_extremes() -> None:
    left = compute_geometry(RenderSpec(0, 1, 1920, 1080, crop_x=0.0))
    right = compute_geometry(RenderSpec(0, 1, 1920, 1080, crop_x=1.0))
    assert left.crop_x == 0 and right.crop_x == 1920 - right.crop_w


def test_render_command_is_argument_list() -> None:
    spec = RenderSpec(
        start=1.5,
        end=4.25,
        source_width=1920,
        source_height=1080,
        watermark=True,
        normalize_audio=True,
    )
    cmd = build_render_command(
        spec, "/in/source file;rm -rf.mp4", __import__("pathlib").Path("/out/x.mp4")
    )
    assert cmd[0] == "ffmpeg"
    assert "/in/source file;rm -rf.mp4" in cmd  # passed as one argv entry, never via a shell
    assert cmd[cmd.index("-ss") + 1] == "1.500" and cmd[cmd.index("-t") + 1] == "2.750"
    assert "loudnorm" in cmd[cmd.index("-af") + 1]
    vf = cmd[cmd.index("-vf") + 1]
    assert vf.startswith("crop=606:1080:657:0,scale=606:1080,setsar=1")
    assert "drawtext=" in vf
    assert cmd[-1] == "/out/x.mp4"
    with pytest.raises(ValueError):
        build_render_command(RenderSpec(5, 5, 100, 100), "a", __import__("pathlib").Path("b"))


def test_no_audio_command() -> None:
    cmd = build_render_command(
        RenderSpec(0, 2, 640, 360, has_audio=False), "in", __import__("pathlib").Path("out.mp4")
    )
    assert "-an" in cmd and "-c:a" not in cmd


def test_pad_filter() -> None:
    vf = build_video_filter(RenderSpec(0, 1, 1920, 1080, fit="pad"))
    assert vf.startswith("scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920")


@pytest.mark.parametrize(
    "key", ["../etc/passwd", "/abs/path", "a/../../b", "a//b", "a b", "a;rm", ""]
)
def test_storage_key_validation(key: str) -> None:
    with pytest.raises(ValueError):
        validate_key(key)


def test_redaction() -> None:
    text = (
        "GET https://b.r2.dev/k?X-Amz-Signature=abcdef&X-Amz-Credential=AKIA123 "
        "Authorization: Bearer eyJhbGciOi.abc.def sk-proj-abcdefghijklmnopqrstu "
        "/api/v1/storage/local/object?token=eyJvcCI6.sig"
    )
    out = redact(text)
    for secret in ["abcdef", "AKIA123", "eyJhbGciOi", "abcdefghijklmnopqrstu", "eyJvcCI6"]:
        assert secret not in out
