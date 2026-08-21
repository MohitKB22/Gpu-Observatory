"""Telemetry collectors, including graceful behaviour with no GPU present."""

from app.collectors.dcgm import DcgmCollector
from app.collectors.nvml import NvmlCollector, _decode_throttle
from app.collectors.system import SystemCollector

DCGM_SAMPLE = """# HELP DCGM_FI_DEV_GPU_UTIL GPU utilization.
# TYPE DCGM_FI_DEV_GPU_UTIL gauge
DCGM_FI_DEV_GPU_UTIL{gpu="0",UUID="GPU-aaa",device="nvidia0"} 87
DCGM_FI_DEV_FB_USED{gpu="0",UUID="GPU-aaa"} 40960
DCGM_FI_DEV_FB_TOTAL{gpu="0",UUID="GPU-aaa"} 81920
DCGM_FI_DEV_GPU_TEMP{gpu="0",UUID="GPU-aaa"} 71
DCGM_FI_DEV_POWER_USAGE{gpu="0",UUID="GPU-aaa"} 412.5
DCGM_FI_DEV_SM_CLOCK{gpu="0",UUID="GPU-aaa"} 1755
DCGM_FI_DEV_GPU_UTIL{gpu="1",UUID="GPU-bbb"} 12
DCGM_FI_DEV_FB_USED{gpu="1",UUID="GPU-bbb"} 2048
DCGM_FI_DEV_FB_TOTAL{gpu="1",UUID="GPU-bbb"} 81920
"""


def test_nvml_reports_unavailable_without_fabricating():
    """With no NVIDIA driver present the collector must say so and return
    nothing -- never invent hardware statistics."""
    collector = NvmlCollector()
    status = collector.status()
    if not status.available:
        assert status.reason in {
            "nvml_library_not_installed",
            "nvml_init_failed",
            "no_nvidia_gpu_detected",
        }
        assert collector.discover() == []
        assert collector.sample() == []


def test_throttle_bitmask_decoding():
    assert _decode_throttle(0) == []
    assert "sw_power_cap" in _decode_throttle(0x4)
    decoded = _decode_throttle(0x40 | 0x20)
    assert "hw_thermal_slowdown" in decoded
    assert "sw_thermal_slowdown" in decoded


def test_dcgm_parses_multiple_gpus():
    samples = DcgmCollector(endpoint="http://unused").parse(DCGM_SAMPLE)
    assert len(samples) == 2
    first = samples[0]
    assert first.uuid == "GPU-aaa"
    assert first.utilization_pct == 87.0
    assert first.temperature_c == 71.0
    assert first.power_w == 412.5
    assert first.sm_clock_mhz == 1755
    # Derived when the exporter does not publish it directly.
    assert first.memory_utilization_pct == 50.0
    assert samples[1].uuid == "GPU-bbb"


def test_dcgm_ignores_comments_and_unknown_fields():
    payload = '# comment\nDCGM_FI_DEV_UNKNOWN{gpu="0",UUID="GPU-x"} 5\n'
    assert DcgmCollector(endpoint="http://unused").parse(payload) == []


def test_dcgm_unreachable_endpoint_degrades_cleanly():
    collector = DcgmCollector(endpoint="http://127.0.0.1:9/metrics", timeout=0.2)
    assert collector.sample() == []
    assert collector.status().available is False
    assert collector.status().reason == "dcgm_exporter_unreachable"


def test_system_collector_returns_real_host_metrics():
    collector = SystemCollector()
    if not collector.status().available:
        return
    sample = collector.sample()
    assert sample is not None
    assert 0 <= sample.cpu_utilization_pct <= 100
    assert sample.core_count >= 1
    assert 0 <= sample.ram_utilization_pct <= 100
    assert sample.process_count >= 1
