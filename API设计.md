# ReproChecker API 设计

> 版本: v0.1 | 日期: 2026-05-28

## 基础信息

- **CLI 工具**：`repro` 命令
- **存储**：本地 SQLite
- **报告**：HTML/PDF 文件输出

---

## CLI 命令

### repro check — 执行检验

```bash
# 完整检验（仓库 + PDF）
repro check https://github.com/user/repo --pdf paper.pdf

# 仅运行代码（不解析 PDF）
repro check https://github.com/user/repo

# 指定入口命令
repro check https://github.com/user/repo --cmd "python train.py --epochs 50"

# 指定环境方式
repro check https://github.com/user/repo --env docker

# 设置最大运行时间
repro check https://github.com/user/repo --timeout 7200

# 指定 GPU
repro check https://github.com/user/repo --gpu 0
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `url` | positional | 必填 | GitHub 仓库 URL |
| `--pdf` | path | None | 论文 PDF 路径 |
| `--cmd` | string | 自动检测 | 自定义运行命令 |
| `--env` | string | auto | 环境方式：docker / conda / venv / auto |
| `--timeout` | int | 14400 | 最大运行时间（秒） |
| `--gpu` | int | 0 | GPU 编号 |
| `--seed` | int | 42 | 随机种子 |
| `--no-cache` | flag | false | 不使用缓存，重新 clone |
| `--name` | string | None | 自定义检验名称 |

**输出**：

```
[1/6] 克隆仓库... ✓ (commit: a1b2c3d)
[2/6] 分析项目... ✓ (PyTorch, entry: train.py)
[3/6] 搭建环境... ✓ (pip, 45 packages)
[4/6] 运行实验... ✓ (duration: 45m 32s)
[5/6] 解析论文... ✓ (found 3 tables, 12 metrics)
[6/6] 对比结果... ✓

═══════════════════════════════════════
  可复现性评分: B (82/100)
═══════════════════════════════════════

  指标复现:  85/100  (accuracy: +1.2%, F1: -2.1%)
  环境复现:  80/100  (有 requirements.txt，无 Dockerfile)
  代码质量:  78/100  (有 README，有种子，无预训练权重)

  报告已保存: ~/.reprochecker/reports/check_42.html
```

---

### repro list — 列出检验记录

```bash
# 列出所有记录
repro list

# 按状态筛选
repro list --status success

# 按仓库筛选
repro list --repo "user/repo"

# 按评分排序
repro list --sort score --limit 10
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--status` | string | all | 筛选状态：pending / running / success / failed |
| `--repo` | string | None | 按仓库名筛选 |
| `--grade` | string | None | 按等级筛选：A / B / C / D / F |
| `--sort` | string | created_at | 排序字段：created_at / score / grade |
| `--limit` | int | 20 | 返回数量 |

**输出**：

```
 ID  Repository              Grade  Score  Status   Date
─────────────────────────────────────────────────────────
 42  user/awesome-model       B      82     success  2026-05-28
 41  another/repo             A      95     success  2026-05-27
 40  broken/project           F      12     failed   2026-05-26
```

---

### repro show — 查看检验详情

```bash
repro show 42
```

**输出**：

```
═══════════════════════════════════════
  检验 #42: user/awesome-model
  评分: B (82/100) | 2026-05-28 10:45
═══════════════════════════════════════

  仓库: https://github.com/user/awesome-model
  Commit: a1b2c3d (main)
  框架: PyTorch 2.1.0
  入口: train.py
  环境: pip (45 packages)
  耗时: 45m 32s
  GPU 显存峰值: 8192 MB

  ── 指标对比 ─────────────────────────

  Metric       Paper    Actual   Error    Status
  accuracy     92.1%    93.3%    +1.2%    ✓ 完全复现
  F1           90.3%    88.4%    -2.1%    ✓ 基本复现
  precision    91.0%    87.2%    -4.2%    ✓ 基本复现
  recall       89.5%    89.8%    +0.3%    ✓ 完全复现

  ── 代码质量 ─────────────────────────

  ✓ 有 README.md
  ✓ 有 requirements.txt (有版本锁定)
  ✗ 无 Dockerfile
  ✓ 有随机种子设置
  ✗ 无预训练权重
  ✓ 有数据集下载脚本

  ── 环境信息 ─────────────────────────

  Python: 3.11.5
  PyTorch: 2.1.0
  CUDA: 12.1
  GPU: NVIDIA RTX 4090
```

---

### repro report — 生成/导出报告

```bash
# 生成 HTML 报告
repro report 42

# 导出 PDF
repro report 42 --format pdf --output ./reports/

# 导出 JSON
repro report 42 --format json
```

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `id` | positional | 必填 | 检验 ID |
| `--format` | string | html | 输出格式：html / pdf / json |
| `--output` | path | ~/.reprochecker/reports/ | 输出目录 |

---

### repro compare — 对比两次检验

```bash
repro compare 42 45
```

**输出**：

```
═══════════════════════════════════════
  对比: #42 vs #45
═══════════════════════════════════════

  #42: user/awesome-model (a1b2c3d) — B (82)
  #45: user/awesome-model (d4e5f6a) — A (91)

  ── 指标变化 ─────────────────────────

  Metric       #42      #45      Change
  accuracy     93.3%    94.1%    +0.8%  ↑
  F1           88.4%    91.2%    +2.8%  ↑
  precision    87.2%    90.5%    +3.3%  ↑

  ── 评分变化 ─────────────────────────

  指标复现:    85 → 92   (+7)
  环境复现:    80 → 80   (0)
  代码质量:    78 → 95   (+17)  ← 新增 Dockerfile
```

---

### repro delete — 删除检验记录

```bash
repro delete 42
```

---

### repro stats — 统计概览

```bash
repro stats
```

**输出**：

```
═══════════════════════════════════════
  ReproChecker 统计
═══════════════════════════════════════

  总检验次数: 150
  成功率: 78% (117/150)

  等级分布:
    A: 23 (15%)  ████████
    B: 45 (30%)  ████████████████
    C: 31 (21%)  ███████████
    D: 18 (12%)  ██████
    F: 33 (22%)  ████████████

  平均评分: 68.5
  平均耗时: 52m 18s

  最常检验的仓库:
    1. user/repo-a (12 次)
    2. lab/repo-b (8 次)
    3. team/repo-c (5 次)
```

---

## JSON 报告格式

```json
{
  "schema_version": "1.0",
  "check_id": 42,
  "repo_url": "https://github.com/user/awesome-model",
  "commit": "a1b2c3d",
  "framework": "pytorch",
  "score": {
    "overall": 82,
    "grade": "B",
    "metric_score": 85,
    "env_score": 80,
    "code_score": 78
  },
  "paper_results": [
    {"metric": "accuracy", "value": 92.1, "source": "Table 1, Row 3"}
  ],
  "actual_results": [
    {"metric": "accuracy", "value": 93.3, "step": "final"}
  ],
  "comparisons": [
    {
      "metric": "accuracy",
      "paper_value": 92.1,
      "actual_value": 93.3,
      "absolute_error": 1.2,
      "relative_error_percent": 1.3,
      "within_tolerance": true,
      "band": "<1%"
    }
  ],
  "code_quality": {
    "has_readme": true,
    "has_requirements": true,
    "requirements_pinned": true,
    "has_dockerfile": false,
    "has_seed": true,
    "has_pretrained": false,
    "has_data_script": true
  },
  "environment": {
    "method": "pip",
    "python": "3.11.5",
    "packages": {"torch": "2.1.0"}
  },
  "resources": {
    "duration_sec": 2732.5,
    "peak_gpu_mem_mb": 8192.0,
    "model_params": 25600000,
    "model_size_mb": 97.6,
    "inference_ms": 12.5
  },
  "created_at": "2026-05-28T10:45:00"
}
```

---

## 错误处理

| 场景 | CLI 输出 | 退出码 |
|------|----------|--------|
| URL 无效 | `错误: 无法访问仓库，请检查 URL` | 1 |
| Clone 失败 | `错误: git clone 失败 — <原因>` | 1 |
| 环境搭建失败 | `警告: 自动安装失败，请手动配置` + 日志 | 2 |
| 实验运行超时 | `错误: 运行超时 (超过 {timeout}s)` | 3 |
| 实验运行失败 | `错误: 进程退出码 {code}` + stderr | 4 |
| PDF 解析失败 | `警告: PDF 解析失败，跳过论文对比` | 0 (继续) |
| 无指标输出 | `警告: 未检测到任何指标` | 0 |
