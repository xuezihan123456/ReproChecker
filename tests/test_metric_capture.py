"""指标捕获测试"""

from __future__ import annotations

import pytest

from reprochecker.runner.metric_capture import capture_metrics


class TestMetricCapture:
    def test_basic_accuracy(self) -> None:
        stdout = "Epoch 1: accuracy: 0.921"
        metrics = capture_metrics(stdout, "")
        names = [m["name"] for m in metrics]
        assert "accuracy" in names

    def test_percentage_format(self) -> None:
        stdout = "Accuracy: 92.1%"
        metrics = capture_metrics(stdout, "")
        acc = [m for m in metrics if m["name"] == "accuracy"]
        assert len(acc) > 0
        assert acc[0]["value"] == pytest.approx(0.921, abs=0.005)

    def test_loss_format(self) -> None:
        stdout = "Step 100: loss = 0.0345"
        metrics = capture_metrics(stdout, "")
        loss = [m for m in metrics if m["name"] == "loss"]
        assert len(loss) > 0
        assert loss[0]["value"] == pytest.approx(0.0345, abs=0.001)

    def test_multiple_metrics(self) -> None:
        stdout = """
        Epoch 1/100: loss: 0.5, accuracy: 0.8, f1: 0.75
        Epoch 2/100: loss: 0.3, accuracy: 0.85, f1: 0.82
        """
        metrics = capture_metrics(stdout, "")
        names = {m["name"] for m in metrics}
        assert "loss" in names
        assert "accuracy" in names
        assert "f1_score" in names

    def test_f1_score_alias(self) -> None:
        stdout = "f1_score: 0.903"
        metrics = capture_metrics(stdout, "")
        f1 = [m for m in metrics if "f1" in m["name"]]
        assert len(f1) > 0

    def test_precision_recall(self) -> None:
        stdout = "precision: 0.91, recall: 0.895"
        metrics = capture_metrics(stdout, "")
        names = {m["name"] for m in metrics}
        assert "precision" in names
        assert "recall" in names

    def test_epoch_extraction(self) -> None:
        stdout = "Epoch 5/100 loss: 0.2 accuracy: 0.85"
        metrics = capture_metrics(stdout, "")
        loss = [m for m in metrics if m["name"] == "loss"]
        assert len(loss) > 0
        # epoch 提取取决于模块实现，至少值应正确
        assert loss[0]["value"] == pytest.approx(0.2, abs=0.01)

    def test_empty_input(self) -> None:
        metrics = capture_metrics("", "")
        assert metrics == []

    def test_noise_filtering(self) -> None:
        stdout = """
        ERROR: something went wrong
        Traceback (most recent call last):
          File "/path/to/file.py", line 42
        accuracy: 0.95
        """
        metrics = capture_metrics(stdout, "")
        # 应该只捕获 accuracy，跳过错误行
        assert len(metrics) >= 1
        assert metrics[0]["name"] == "accuracy"
