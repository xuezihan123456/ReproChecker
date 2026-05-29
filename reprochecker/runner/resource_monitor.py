"""资源监控 — 后台线程采样 GPU / CPU / 内存使用情况"""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass

import psutil

from reprochecker.logging import get_logger

logger = get_logger(__name__.replace("reprochecker.", ""))

# 默认采样间隔（秒）
_DEFAULT_INTERVAL = 5


@dataclass
class _SampleSnapshot:
    """单次采样快照。"""

    timestamp: float = 0.0
    cpu_percent: float = 0.0
    ram_mb: float = 0.0
    gpu_mem_mb: float = 0.0


@dataclass
class _PeakStats:
    """累计峰值统计。"""

    peak_cpu_percent: float = 0.0
    peak_ram_mb: float = 0.0
    peak_gpu_mem_mb: float = 0.0
    sample_count: int = 0


class ResourceMonitor:
    """GPU / CPU / 内存资源监控器。

    在后台线程中以固定间隔采样，记录峰值使用量。
    使用 nvidia-smi 获取 GPU 信息（如果不可用则跳过 GPU 监控）。

    Usage
    -----
    >>> monitor = ResourceMonitor(interval=5)
    >>> monitor.start()
    >>> # ... 运行实验 ...
    >>> monitor.stop()
    >>> stats = monitor.get_stats()
    """

    def __init__(self, interval: int = _DEFAULT_INTERVAL) -> None:
        self._interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._peaks = _PeakStats()
        self._gpu_available: bool | None = None  # None = 尚未检测
        self._running = False

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动后台监控线程。重复调用是安全的。"""
        if self._running:
            logger.debug("ResourceMonitor already running, ignoring start()")
            return

        self._stop_event.clear()
        self._peaks = _PeakStats()
        self._running = True

        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="ResourceMonitor",
            daemon=True,
        )
        self._thread.start()
        logger.info("ResourceMonitor started (interval=%ds)", self._interval)

    def stop(self) -> None:
        """停止后台监控线程并等待其退出。"""
        if not self._running:
            logger.debug("ResourceMonitor not running, ignoring stop()")
            return

        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval * 2)
            self._thread = None
        self._running = False
        logger.info("ResourceMonitor stopped (samples=%d)", self._peaks.sample_count)

    def get_stats(self) -> dict:
        """返回监控统计结果。

        Returns
        -------
        dict
            包含 peak_gpu_mem_mb, peak_cpu_percent, peak_ram_mb,
            sample_count, interval_sec, gpu_available。
        """
        with self._lock:
            return {
                "peak_gpu_mem_mb": round(self._peaks.peak_gpu_mem_mb, 1),
                "peak_cpu_percent": round(self._peaks.peak_cpu_percent, 1),
                "peak_ram_mb": round(self._peaks.peak_ram_mb, 1),
                "sample_count": self._peaks.sample_count,
                "interval_sec": self._interval,
                "gpu_available": self._gpu_available if self._gpu_available is not None else False,
            }

    @property
    def is_running(self) -> bool:
        """监控线程是否正在运行。"""
        return self._running

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        """后台线程主循环。"""
        while not self._stop_event.is_set():
            try:
                snapshot = self._take_sample()
                self._update_peaks(snapshot)
            except Exception:
                logger.debug("Sample failed", exc_info=True)
            # 可中断的等待
            self._stop_event.wait(timeout=self._interval)

    def _take_sample(self) -> _SampleSnapshot:
        """执行一次系统资源采样。"""
        snap = _SampleSnapshot(timestamp=time.time())

        # CPU 和内存
        snap.cpu_percent = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        snap.ram_mb = mem.used / (1024 * 1024)

        # GPU
        snap.gpu_mem_mb = self._query_gpu_memory()

        return snap

    def _update_peaks(self, snap: _SampleSnapshot) -> None:
        """用一次采样更新峰值统计。"""
        with self._lock:
            self._peaks.sample_count += 1
            if snap.cpu_percent > self._peaks.peak_cpu_percent:
                self._peaks.peak_cpu_percent = snap.cpu_percent
            if snap.ram_mb > self._peaks.peak_ram_mb:
                self._peaks.peak_ram_mb = snap.ram_mb
            if snap.gpu_mem_mb > self._peaks.peak_gpu_mem_mb:
                self._peaks.peak_gpu_mem_mb = snap.gpu_mem_mb

    def _query_gpu_memory(self) -> float:
        """通过 nvidia-smi 查询当前 GPU 显存使用量（MiB）。

        首次调用时检测 nvidia-smi 是否可用，后续使用缓存结果。
        如果 GPU 不可用返回 0.0。
        """
        # 首次检测
        if self._gpu_available is False:
            return 0.0

        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                self._gpu_available = False
                return 0.0

            self._gpu_available = True
            # 可能有多张 GPU，取总和
            total = 0.0
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if line:
                    try:
                        total += float(line)
                    except ValueError:
                        continue
            return total

        except FileNotFoundError:
            # nvidia-smi 不存在
            self._gpu_available = False
            logger.debug("nvidia-smi not found, GPU monitoring disabled")
            return 0.0
        except subprocess.TimeoutExpired:
            logger.debug("nvidia-smi timed out")
            return 0.0
        except Exception:
            logger.debug("GPU query failed", exc_info=True)
            return 0.0
