"""The ComfyUI adapter against a mocked server.

Submit, poll, download, and turn the result into what the stage needs: a PNG
for a still, a directory of frames for a clip. The server is respx; ffmpeg is
real, because extracting frames is the one step with a tool in it.
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest

respx = pytest.importorskip("respx")

BASE = "http://comfy.test:8188"
WORKFLOWS = Path(__file__).parent.parent / "app" / "workflows"


def _png_bytes(colour=(200, 120, 60)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 96), colour).save(buf, "PNG")
    return buf.getvalue()


def _provider(**extra):
    from app.providers.visuals.comfyui import ComfyUIProvider

    settings = {"base_url": BASE, "image_workflow": str(WORKFLOWS / "image_qwen_image_2512.json"),
                "video_workflow": str(WORKFLOWS / "video_ltx2_5_t2v.json"),
                "request_timeout": 30, "lightning": True}
    settings.update(extra)
    return ComfyUIProvider(settings)


@respx.mock
def test_a_still_is_submitted_polled_downloaded_and_saved_as_png(tmp_path, monkeypatch):
    from app.providers.visuals import comfyui

    monkeypatch.setattr(comfyui, "POLL_SECONDS", 0.0)
    submitted = {}

    def on_prompt(request):
        submitted["body"] = json.loads(request.content)
        return httpx.Response(200, json={"prompt_id": "p1", "number": 1, "node_errors": {}})

    respx.post(f"{BASE}/prompt").mock(side_effect=on_prompt)
    history = respx.get(f"{BASE}/history/p1").mock(side_effect=[
        httpx.Response(200, json={}),                      # still running
        httpx.Response(200, json={"p1": {"outputs": {"60": {"images": [
            {"filename": "reelforge_00001_.png", "subfolder": "reelforge", "type": "output"}]}},
            "status": {"status_str": "success", "completed": True}}}),
    ])
    respx.get(f"{BASE}/view").mock(return_value=httpx.Response(200, content=_png_bytes()))

    out = tmp_path / "still-1.png"
    result = _provider().still("a lighthouse at dusk", out, width=1152, height=1536, seed=7)

    assert out.exists() and result.width == 64 and result.seed == 7
    assert history.call_count == 2
    nodes = submitted["body"]["prompt"]
    assert nodes["238:227"]["inputs"]["text"] == "a lighthouse at dusk"
    assert nodes["238:232"]["inputs"] == {"width": 1152, "height": 1536, "batch_size": 1}
    assert nodes["238:230"]["inputs"]["seed"] == 7
    assert nodes["238:229"]["inputs"]["value"] is True
    assert submitted["body"]["client_id"].startswith("reelforge-")
    # the raw download is not left beside the result
    assert not list(tmp_path.glob("*.raw*"))


@respx.mock
def test_a_rejected_workflow_reports_the_servers_node_error():
    from app.providers.visuals.base import VisualsError

    respx.post(f"{BASE}/prompt").mock(return_value=httpx.Response(400, json={
        "error": {"type": "prompt_outputs_failed_validation", "message": "Prompt outputs failed validation"},
        "node_errors": {"238:226": {"errors": [
            {"type": "value_not_in_list", "message": "Value not in list: unet_name: 'x.safetensors'"}]}},
    }))
    with pytest.raises(VisualsError, match="Value not in list"):
        _provider().submit({"1": {"class_type": "X", "inputs": {}}})


@respx.mock
def test_an_execution_error_in_history_is_surfaced(monkeypatch):
    from app.providers.visuals import comfyui
    from app.providers.visuals.base import VisualsError

    monkeypatch.setattr(comfyui, "POLL_SECONDS", 0.0)
    respx.get(f"{BASE}/history/p2").mock(return_value=httpx.Response(200, json={"p2": {
        "outputs": {}, "status": {"status_str": "error", "completed": False, "messages": [
            ["execution_error", {"node_type": "KSampler", "exception_message": "CUDA out of memory"}]]}}}))
    with pytest.raises(VisualsError, match="KSampler: CUDA out of memory"):
        _provider().wait("p2")


@respx.mock
def test_health_reports_reachability_devices_and_the_detected_nodes():
    respx.get(f"{BASE}/system_stats").mock(return_value=httpx.Response(200, json={
        "system": {"comfyui_version": "0.3.99"},
        "devices": [{"name": "cuda:0 NVIDIA RTX 6000", "vram_total": 48 * 2**30}]}))
    respx.get(f"{BASE}/queue").mock(return_value=httpx.Response(200, json={
        "queue_running": [], "queue_pending": [1, 2]}))
    respx.get(url__regex=rf"{BASE}/object_info/.*").mock(return_value=httpx.Response(404))

    out = _provider().health()
    assert out["reachable"] is True
    assert out["devices"][0]["vram_gb"] == 48.0
    assert out["queue"] == {"running": 0, "pending": 2}
    assert out["image_nodes"]["prompt"].startswith("238:227 CLIPTextEncode")
    assert out["video_nodes"]["seconds"].startswith("405:362 PrimitiveInt")
    assert "error" not in out


@respx.mock
def test_health_flags_a_model_the_server_does_not_have():
    respx.get(f"{BASE}/system_stats").mock(return_value=httpx.Response(200, json={"devices": []}))
    respx.get(f"{BASE}/queue").mock(return_value=httpx.Response(200, json={}))

    def info(request):
        cls = request.url.path.rsplit("/", 1)[-1]
        if cls == "UNETLoader":
            return httpx.Response(200, json={cls: {"input": {"required": {
                "unet_name": [["some-other-model.safetensors"]]}}}})
        return httpx.Response(404)

    respx.get(url__regex=rf"{BASE}/object_info/.*").mock(side_effect=info)
    out = _provider(video_workflow="").health()
    assert out["reachable"] is True
    assert "qwen_image_2512_fp8_e4m3fn.safetensors" in out["error"]


def test_unreachable_server_is_a_clean_health_result():
    out = _provider(base_url="http://127.0.0.1:9").health()
    assert out["reachable"] is False and "unreachable" in out["error"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not on PATH")
@respx.mock
def test_a_clip_is_downloaded_and_exploded_into_reel_frames(tmp_path, monkeypatch):
    from app.providers.visuals import comfyui

    monkeypatch.setattr(comfyui, "POLL_SECONDS", 0.0)
    # a real 1 s 24 fps clip at LTX-ish 9:16 size, so the scale+crop is exercised
    source = tmp_path / "src.mp4"
    subprocess.run([shutil.which("ffmpeg"), "-y", "-v", "error", "-f", "lavfi",
                    "-i", "testsrc=size=736x1312:rate=24:duration=1", "-pix_fmt", "yuv420p",
                    str(source)], check=True)

    submitted = {}

    def on_prompt(request):
        submitted["body"] = json.loads(request.content)
        return httpx.Response(200, json={"prompt_id": "v1"})

    respx.post(f"{BASE}/prompt").mock(side_effect=on_prompt)
    respx.get(f"{BASE}/history/v1").mock(return_value=httpx.Response(200, json={"v1": {
        "outputs": {"75": {"images": [{"filename": "LTX_00001.mp4", "subfolder": "video",
                                       "type": "output"}], "animated": [True]}},
        "status": {"status_str": "success", "completed": True}}}))
    respx.get(f"{BASE}/view").mock(return_value=httpx.Response(200, content=source.read_bytes()))

    out_dir = tmp_path / "clip-1"
    result = _provider().clip("slow dolly", out_dir, seconds=1, fps=30, width=1080,
                              height=1920, seed=3)
    frames = sorted(out_dir.glob("*.jpg"))
    assert result.frames == len(frames) and 28 <= len(frames) <= 31
    from PIL import Image

    assert Image.open(frames[0]).size == (1080, 1920)
    assert result.source and result.source.exists()
    nodes = submitted["body"]["prompt"]
    assert nodes["405:376"]["inputs"]["value"] == "slow dolly"
    assert nodes["405:362"]["inputs"]["value"] == 1
    # the workflow's own frame rate is kept; the reel's 30 fps is applied at extraction
    assert nodes["405:361"]["inputs"]["value"] == 24
