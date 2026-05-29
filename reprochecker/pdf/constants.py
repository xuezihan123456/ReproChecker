"""PDF 解析共享常量"""

from __future__ import annotations

# 已知指标名映射：别名 -> 标准名
METRIC_ALIASES: dict[str, str] = {
    "accuracy": "accuracy",
    "acc": "accuracy",
    "f1": "f1",
    "f1-score": "f1",
    "f1 score": "f1",
    "precision": "precision",
    "recall": "recall",
    "bleu": "bleu",
    "bleu-1": "bleu-1",
    "bleu-2": "bleu-2",
    "bleu-3": "bleu-3",
    "bleu-4": "bleu-4",
    "map": "mAP",
    "mmap": "mAP",
    "map@50": "mAP@50",
    "map@75": "mAP@75",
    "map50": "mAP@50",
    "map75": "mAP@75",
    "iou": "IoU",
    "miou": "mIoU",
    "dice": "Dice",
    "psnr": "PSNR",
    "ssim": "SSIM",
    "mse": "MSE",
    "rmse": "RMSE",
    "mae": "MAE",
    "auc": "AUC",
    "ap": "AP",
    "top-1": "Top-1",
    "top-5": "Top-5",
    "top1": "Top-1",
    "top5": "Top-5",
    "perplexity": "Perplexity",
    "ppl": "Perplexity",
    "wer": "WER",
    "cer": "CER",
    "fid": "FID",
    "lpips": "LPIPS",
}

# 所有已知指标名集合（小写，用于快速查找）
KNOWN_METRICS: set[str] = set(METRIC_ALIASES.keys())

# 识别 "最佳方法" 的标记
BEST_MARKERS: set[str] = {
    "ours",
    "our method",
    "proposed",
    "proposed method",
    "our model",
    "our approach",
}
