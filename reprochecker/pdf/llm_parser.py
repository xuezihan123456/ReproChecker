"""LLM 结构化数值提取模块

使用 OpenAI 兼容 API 从论文文本中提取结构化实验结果。
当 LLM 不可用时自动降级到正则表达式方式。
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from reprochecker.logging import get_logger
from reprochecker.pdf.constants import BEST_MARKERS, METRIC_ALIASES

logger = get_logger(__name__.replace("reprochecker.", ""))

# ──────────────────────────── LLM Prompt 模板 ────────────────────────────

_SYSTEM_PROMPT = "你是一个学术论文结果提取专家。请严格按照 JSON 格式输出，不要包含任何其他文字。"

_USER_PROMPT_TEMPLATE = """\
从以下论文文本中提取所有报告的实验结果。

要求：
1. 提取所有表格中的数值结果
2. 识别最佳结果（论文声称的 SOTA），标记 is_best=true
3. 识别方法名和对应的指标名/指标值
4. 处理百分比值（如 92.1% 提取为 92.1）

返回 JSON 数组，每个元素格式：
{{
  "table_caption": "表格标题（如有）",
  "method_name": "方法名",
  "metric_name": "指标名",
  "metric_value": 数值,
  "is_best": true/false
}}

论文文本：
{text}
"""


# ──────────────────────────── 公共接口 ────────────────────────────


def parse_paper_results(text: str) -> list[dict[str, Any]]:
    """使用 LLM 从论文文本中提取结构化结果。

    优先使用 LLM，若不可用或调用失败则降级到正则方式。
    返回格式与 extractor.extract_from_pdf 一致。
    """
    if not text or not text.strip():
        return []

    # 尝试 LLM 方式
    llm_results = _try_llm_parse(text)
    if llm_results is not None:
        return llm_results

    # 降级到正则方式
    logger.info("LLM 不可用，降级到正则表达式提取")
    return parse_with_regex(text)


def parse_with_regex(text: str) -> list[dict[str, Any]]:
    """使用正则表达式从论文文本中提取实验结果。

    作为 LLM 方式的备选方案，覆盖常见的学术论文指标报告格式。
    """
    if not text or not text.strip():
        return []

    results: list[dict[str, Any]] = []
    lines = text.split("\n")

    # 策略 1: 匹配 "指标名 = 数值" 或 "指标名: 数值" 格式
    results.extend(_extract_key_value_pairs(lines))

    # 策略 2: 匹配表格行格式（方法名 + 多个数值列）
    results.extend(_extract_table_like_rows(lines))

    # 去重（同一 method+metric 只保留首次出现）
    return _deduplicate_results(results)


# ──────────────────────────── LLM 调用 ────────────────────────────


def _try_llm_parse(text: str) -> list[dict[str, Any]] | None:
    """尝试使用 LLM 解析，成功返回结果列表，失败返回 None。"""
    # 检查 openai 库是否可用
    try:
        from openai import OpenAI
    except ImportError:
        logger.debug("openai 库未安装")
        return None

    # 检查 API key
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        logger.debug("OPENAI_API_KEY 环境变量未设置")
        return None

    # 截断过长文本，避免超出 token 限制
    max_chars = 60_000
    truncated = text[:max_chars] if len(text) > max_chars else text

    try:
        from reprochecker.config import get_config
        config = get_config()

        client = OpenAI(
            api_key=api_key,
            base_url=os.environ.get("OPENAI_BASE_URL", None),
        )
        response = client.chat.completions.create(
            model=config.llm_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _USER_PROMPT_TEMPLATE.format(text=truncated)},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or ""
        parsed = _parse_llm_json(content)
        if parsed:
            logger.info("LLM 提取成功，共 %d 条记录", len(parsed))
        return parsed

    except Exception:
        logger.warning("LLM 调用失败，将降级到正则方式", exc_info=True)
        return None


def _parse_llm_json(content: str) -> list[dict[str, Any]] | None:
    """解析 LLM 返回的 JSON 内容。"""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # 尝试从 markdown 代码块中提取
        match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", content, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                return None
        else:
            return None

    # 兼容 {"results": [...]} 或直接 [...]
    if isinstance(data, dict):
        # 取第一个值为列表的键
        for v in data.values():
            if isinstance(v, list):
                data = v
                break
    if not isinstance(data, list):
        return None

    results: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_result(item)
        if normalized is not None:
            results.append(normalized)
    return results if results else None


def _normalize_result(item: dict[str, Any]) -> dict[str, Any] | None:
    """将单条 LLM 提取结果规范化为标准格式。"""
    metric_name = str(item.get("metric_name", "")).strip()
    raw_value = item.get("metric_value")

    if not metric_name or raw_value is None:
        return None

    # 尝试解析数值
    value = _to_float(raw_value)
    if value is None:
        return None

    # 标准化指标名
    metric_lower = metric_name.lower().strip()
    metric_name = METRIC_ALIASES.get(metric_lower, metric_name)

    method_name = str(item.get("method_name", "")).strip() or "Unknown"
    caption = str(item.get("table_caption", "")).strip() or ""

    # 判断 is_best
    is_best = bool(item.get("is_best", False))
    if not is_best and method_name.lower() in BEST_MARKERS:
        is_best = True

    return {
        "table_caption": caption,
        "method_name": method_name,
        "metric_name": metric_name,
        "metric_value": value,
        "is_best": is_best,
    }


def _to_float(val: Any) -> float | None:
    """将任意值转换为浮点数。"""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = val.strip().rstrip("%")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


# ──────────────────────────── 正则提取策略 ────────────────────────────


# 匹配 "Metric: 92.1" 或 "Accuracy = 92.1%" 等格式
_KV_PATTERN = re.compile(
    r"\b([A-Za-z][\w\-]*(?:\s+[\w\-]+)*)\s*[:=]\s*(\d+\.?\d*)\s*%?",
    re.IGNORECASE,
)

# 匹配表格行：方法名后跟多个数值
_TABLE_ROW_PATTERN = re.compile(
    r"^[\|\s]*([A-Za-z][\w\s\-]*?)\s*[\|\s]+"
    r"(\d+\.?\d*)\s*%?"
    r"(.*)",
    re.IGNORECASE,
)


def _extract_key_value_pairs(lines: list[str]) -> list[dict[str, Any]]:
    """提取 '指标名: 数值' 格式的结果。"""
    results: list[dict[str, Any]] = []
    for line in lines:
        for match in _KV_PATTERN.finditer(line):
            name_raw = match.group(1).strip().lower()
            value_raw = match.group(2).strip()

            # 检查是否是已知指标
            normalized = METRIC_ALIASES.get(name_raw)
            if normalized is None:
                # 尝试部分匹配
                for key, canon in METRIC_ALIASES.items():
                    if key in name_raw or name_raw in key:
                        normalized = canon
                        break
            if normalized is None:
                continue

            value = _to_float(value_raw)
            if value is None:
                continue

            results.append({
                "table_caption": "",
                "method_name": "Reported",
                "metric_name": normalized,
                "metric_value": value,
                "is_best": False,
            })
    return results


def _extract_table_like_rows(lines: list[str]) -> list[dict[str, Any]]:
    """提取表格行格式的结果（方法名 + 数值列）。"""
    results: list[dict[str, Any]] = []
    current_caption = ""

    for line in lines:
        # 检测表格标题
        caption_match = re.match(
            r"(?:table|tab)\s*\.?\s*\d+[.:]\s*(.+)", line, re.IGNORECASE
        )
        if caption_match:
            current_caption = caption_match.group(1).strip()
            continue

        # 跳过表头行（包含多个纯文本列）
        if re.match(r"^[\|\s]*(Method|Model|Approach|Dataset)", line, re.IGNORECASE):
            continue

        # 尝试匹配表格数据行
        row_match = _TABLE_ROW_PATTERN.match(line)
        if not row_match:
            continue

        method_name = row_match.group(1).strip()
        first_value = row_match.group(2).strip()
        rest = row_match.group(3)

        if not method_name or len(method_name) < 2:
            continue

        is_best = method_name.lower() in BEST_MARKERS

        # 尝试匹配该行中的所有数值及其对应的指标名
        values = _extract_values_from_rest(rest)
        # 第一个值已在正则中捕获
        all_values = [first_value] + values

        # 尝试关联指标名（从表格标题或上下文推断）
        for val_str in all_values:
            value = _to_float(val_str)
            if value is None:
                continue
            # 简单启发式：如果值 > 1 可能是百分比或原始分数
            results.append({
                "table_caption": current_caption,
                "method_name": method_name,
                "metric_name": _guess_metric_from_context(current_caption, line),
                "metric_value": value,
                "is_best": is_best,
            })

    return results


def _extract_values_from_rest(text: str) -> list[str]:
    """从行尾剩余文本中提取所有数值。"""
    return [m.group(1) for m in re.finditer(r"(\d+\.?\d*)\s*%?", text)]


def _guess_metric_from_context(caption: str, line: str) -> str:
    """根据上下文猜测指标名。"""
    combined = f"{caption} {line}".lower()
    for key, canonical in METRIC_ALIASES.items():
        if key in combined:
            return canonical
    return "metric"


def _deduplicate_results(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """去重：同一 (method_name, metric_name) 只保留第一条。"""
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for r in results:
        key = (r["method_name"].lower(), r["metric_name"].lower())
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped
