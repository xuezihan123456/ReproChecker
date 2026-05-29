"""PyMuPDF 文本/表格提取模块

从学术论文 PDF 中提取表格数据和全文文本。
优先提取结构化表格，失败时回退到全文提取供 LLM 处理。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from reprochecker.logging import get_logger
from reprochecker.pdf.constants import BEST_MARKERS, KNOWN_METRICS

logger = get_logger(__name__.replace("reprochecker.", ""))

# 数值匹配模式：整数 / 小数 / 百分比
_NUM_PATTERN = re.compile(
    r"(?<![a-zA-Z])(\d+\.?\d*)\s*%?"
)

# 表格标题模式
_CAPTION_PATTERN = re.compile(
    r"(?:table|tab)\s*\.?\s*\d+[.:]\s*(.+?)(?:\n|$)",
    re.IGNORECASE,
)


def extract_from_pdf(pdf_path: Path) -> list[dict[str, Any]]:
    """从 PDF 提取实验结果，返回与 paper_results 表一致的字典列表。

    流程：
    1. 尝试提取表格结构化数据
    2. 若表格提取无结果，回退到全文文本提取（由调用方交给 LLM 处理）
    """
    if not pdf_path.exists():
        logger.warning("PDF 文件不存在: %s", pdf_path)
        return []

    results = extract_tables(pdf_path)
    if results:
        logger.info("表格提取成功，共 %d 条记录", len(results))
        return results

    # 表格提取无结果时，尝试全文提取并记录诊断信息
    try:
        text = extract_text(pdf_path)
        if text:
            logger.info(
                "表格提取无结果，已提取全文 %d 字符（需 LLM 处理）", len(text)
            )
        else:
            logger.warning("PDF 文本提取也返回空结果: %s", pdf_path)
    except Exception:
        logger.debug("全文提取失败", exc_info=True)

    return []


def extract_text(pdf_path: Path) -> str:
    """提取 PDF 全文文本内容。"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF 未安装，请执行: pip install pymupdf")
        return ""

    text_parts: list[str] = []
    try:
        doc = fitz.open(str(pdf_path))
        for page in doc:
            page_text = page.get_text("text")
            if page_text:
                text_parts.append(page_text)
        doc.close()
    except Exception:
        logger.exception("PDF 文本提取失败: %s", pdf_path)
        return ""

    return "\n".join(text_parts)


def extract_tables(pdf_path: Path) -> list[dict[str, Any]]:
    """从 PDF 中提取表格数据，返回结构化结果列表。

    返回格式：
        [{"table_caption": str, "method_name": str, "metric_name": str,
          "metric_value": float, "is_best": bool}, ...]
    """
    try:
        import fitz
    except ImportError:
        logger.error("PyMuPDF 未安装，请执行: pip install pymupdf")
        return []

    all_results: list[dict[str, Any]] = []
    try:
        doc = fitz.open(str(pdf_path))
        for page_idx, page in enumerate(doc):
            tables = page.find_tables()
            if not tables or not tables.tables:
                continue
            for table in tables.tables:
                results = _parse_fitz_table(table, page, page_idx)
                all_results.extend(results)
        doc.close()
    except Exception:
        logger.exception("PDF 表格提取失败: %s", pdf_path)

    return all_results


def _parse_fitz_table(
    table: Any, page: Any, page_idx: int
) -> list[dict[str, Any]]:
    """解析单个 fitz 提取的表格对象。"""
    results: list[dict[str, Any]] = []
    try:
        rows = table.extract()
    except Exception:
        return results

    if not rows or len(rows) < 2:
        return results

    # 尝试从页面文本中获取表格标题
    caption = _find_table_caption(page, page_idx)

    # 第一行通常是表头
    header = [_normalize_cell(c) for c in rows[0]]
    metric_cols = _identify_metric_columns(header)

    if not metric_cols:
        return results

    # 第一列通常是方法名
    method_col = 0

    for row in rows[1:]:
        cells = [_normalize_cell(c) for c in row]
        method_name = cells[method_col] if len(cells) > method_col else ""
        if not method_name:
            continue

        is_best = method_name.lower() in BEST_MARKERS

        for col_idx, metric_name in metric_cols:
            if col_idx >= len(cells):
                continue
            value = _parse_numeric(cells[col_idx])
            if value is None:
                continue
            results.append({
                "table_caption": caption,
                "method_name": method_name,
                "metric_name": metric_name,
                "metric_value": value,
                "is_best": is_best,
            })

    return results


def _normalize_cell(cell: Any) -> str:
    """将表格单元格规范化为字符串。"""
    if cell is None:
        return ""
    return str(cell).strip()


def _identify_metric_columns(header: list[str]) -> list[tuple[int, str]]:
    """识别表头中的指标列，返回 (列索引, 标准化指标名) 列表。"""
    metric_cols: list[tuple[int, str]] = []
    for idx, raw in enumerate(header):
        name = raw.lower().strip()
        # 直接匹配已知指标
        if name in KNOWN_METRICS:
            metric_cols.append((idx, name))
            continue
        # 去除括号内容后匹配，如 "Accuracy (%)"
        cleaned = re.sub(r"\(.*?\)", "", name).strip()
        if cleaned in KNOWN_METRICS:
            metric_cols.append((idx, cleaned))
            continue
        # 模糊匹配：包含已知指标名
        for metric in KNOWN_METRICS:
            if metric in name or name in metric:
                metric_cols.append((idx, metric))
                break
    return metric_cols


def _parse_numeric(text: str) -> float | None:
    """从文本中解析数值，处理百分比。"""
    if not text:
        return None
    cleaned = text.strip()
    # 去除加粗标记
    cleaned = cleaned.replace("**", "")
    # 跳过非数值内容
    if not cleaned or cleaned in ("-", "--", "N/A", "n/a", ""):
        return None

    # 匹配百分比
    pct_match = re.match(r"^(\d+\.?\d*)\s*%$", cleaned)
    if pct_match:
        return float(pct_match.group(1))

    # 匹配普通数值（可能有上下标标记如 92.1^{*}）
    num_match = re.match(r"^(\d+\.?\d*)", cleaned)
    if num_match:
        return float(num_match.group(1))

    return None


def _find_table_caption(page: Any, page_idx: int) -> str:
    """尝试从页面文本中提取最近的表格标题。"""
    try:
        text = page.get_text("text")
    except Exception:
        return f"Page {page_idx + 1}"

    match = _CAPTION_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return f"Page {page_idx + 1}"


def extract_fulltext_for_llm(pdf_path: Path) -> str:
    """提取 PDF 全文并做预处理，便于 LLM 解析。

    与 extract_text 的区别：额外清理页眉页脚等噪声。
    """
    raw = extract_text(pdf_path)
    if not raw:
        return ""

    # 删除常见页眉页脚模式
    lines = raw.split("\n")
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        # 跳过纯页码行
        if re.match(r"^\d+$", stripped):
            continue
        # 跳过 arXiv 页脚
        if stripped.startswith("arXiv:"):
            continue
        cleaned.append(line)

    return "\n".join(cleaned)
