"""资源监控模块测试"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from reprochecker.runner.resource_monitor import ResourceMonitor


class TestResourceMonitorLifecycle:
    """启停生命周期测试"""

    def test_start_and_stop(self) -> None:
        monitor = ResourceMonitor(interval=1)
        assert not monitor.is_running
        monitor.start()
        assert monitor.is_running
        monitor.stop()
        assert not monitor.is_running

    def test_double_start_is_safe(self) -> None:
        monitor = ResourceMonitor(interval=1)
        monitor.start()
        monitor.start()  # should not raise
        assert monitor.is_running
        monitor.stop()

    def test_double_stop_is_safe(self) -> None:
        monitor = ResourceMonitor(interval=1)
        monitor.start()
        monitor.stop()
        monitor.stop()  # should not raise
        assert not monitor.is_running

    def test_stop_without_start_is_safe(self) -> None:
        monitor = ResourceMonitor(interval=1)
        monitor.stop()  # should not raise


class TestResourceMonitorStats:
    """统计数据测试"""

    @patch("reprochecker.runner.resource_monitor.psutil")
    def test_get_stats_default(self, mock_psutil: MagicMock) -> None:
        mock_psutil.cpu_percent.return_value = 50.0
        mock_mem = MagicMock()
        mock_mem.used = 1024 * 1024 * 1024  # 1 GB
        mock_psutil.virtual_memory.return_value = mock_mem

        monitor = ResourceMonitor(interval=1)
        stats = monitor.get_stats()
        assert stats["peak_cpu_percent"] == 0.0
        assert stats["peak_ram_mb"] == 0.0
        assert stats["sample_count"] == 0
        assert stats["interval_sec"] == 1

    @patch("reprochecker.runner.resource_monitor.psutil")
    def test_tracks_peaks(self, mock_psutil: MagicMock) -> None:
        mock_psutil.cpu_percent.return_value = 75.0
        mock_mem = MagicMock()
        mock_mem.used = 2 * 1024 * 1024 * 1024  # 2 GB
        mock_psutil.virtual_memory.return_value = mock_mem

        monitor = ResourceMonitor(interval=1)
        monitor.start()
        # Wait for at least one sample
        import time
        time.sleep(2)
        monitor.stop()

        stats = monitor.get_stats()
        assert stats["sample_count"] >= 1
        assert stats["peak_cpu_percent"] >= 0.0
        assert stats["peak_ram_mb"] > 0.0


class TestGpuDetection:
    """GPU 检测测试"""

    @patch("reprochecker.runner.resource_monitor.subprocess.run")
    def test_gpu_available(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0, stdout="4096\n2048\n", stderr=""
        )
        monitor = ResourceMonitor(interval=1)
        result = monitor._query_gpu_memory()
        assert result == 6144.0  # 4096 + 2048
        assert monitor._gpu_available is True

    @patch("reprochecker.runner.resource_monitor.subprocess.run")
    def test_gpu_not_available(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError
        monitor = ResourceMonitor(interval=1)
        result = monitor._query_gpu_memory()
        assert result == 0.0
        assert monitor._gpu_available is False

    @patch("reprochecker.runner.resource_monitor.subprocess.run")
    def test_gpu_cached_unavailable(self, mock_run: MagicMock) -> None:
        monitor = ResourceMonitor(interval=1)
        monitor._gpu_available = False
        result = monitor._query_gpu_memory()
        assert result == 0.0
        mock_run.assert_not_called()
