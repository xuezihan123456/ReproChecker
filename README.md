# ReproChecker

学术论文可复现性自动检验工具。输入 GitHub 仓库 URL + 论文 PDF，自动完成：clone → 安装依赖 → 运行实验 → 解析论文结果 → 全维度对比 → 输出可复现性报告。

## 安装

```bash
pip install -e ".[dev]"
```

可选依赖：
```bash
pip install -e ".[pdf]"     # PDF 导出（WeasyPrint）
pip install -e ".[llm]"     # LLM 解析（OpenAI/Anthropic）
pip install -e ".[charts]"  # 训练曲线图（matplotlib）
```

## 快速开始

```bash
# 完整检验（仓库 + PDF）
repro check https://github.com/user/repo --pdf paper.pdf

# 仅运行代码
repro check https://github.com/user/repo

# 自定义命令
repro check https://github.com/user/repo --cmd "python train.py --epochs 50"

# 指定环境方式
repro check https://github.com/user/repo --env docker

# 试运行模式（预览计划，不实际执行）
repro check https://github.com/user/repo --dry-run

# 生成 SVG 可复现性徽章（可嵌入 README）
repro badge 1 -o badge.svg

# 导出 CSV 格式报告（方便学术元分析）
repro report 1 --format csv
```

## CLI 命令

| 命令 | 说明 |
|------|------|
| `repro check <url> --pdf paper.pdf` | 执行完整检验 |
| `repro check --dry-run` | 试运行模式 |
| `repro list [--status/--repo/--grade]` | 列出检验记录 |
| `repro show <id>` | 查看检验详情 |
| `repro report <id> [--format html/pdf/json/csv]` | 生成报告 |
| `repro badge <id> [-o path]` | 生成 SVG 可复现性徽章 |
| `repro compare <id1> <id2>` | 对比两次检验 |
| `repro stats` | 统计概览 |
| `repro delete <id>` | 删除记录 |
| `repro cache list` | 列出缓存仓库 |
| `repro cache clear [repo] [--force]` | 清除缓存 |

## 评分体系

```
总分 = 指标复现 × 50% + 环境复现 × 20% + 代码质量 × 30%

A (90-100): 完全可复现
B (75-89):  基本可复现
C (60-74):  部分可复现
D (40-59):  难以复现
F (0-39):   无法复现
```

## 配置文件

在项目根目录或 `~/.reprochecker/` 下创建 `repro.yaml` 自定义行为：

```yaml
scoring:
  metric_weight: 0.5
  env_weight: 0.2
  code_weight: 0.3

tolerance:
  excellent: 0.01
  good: 0.05
  acceptable: 0.10
  poor: 0.20

defaults:
  env: auto
  timeout: 14400
  gpu: 0
  seed: 42

report:
  format: html
  output_dir: ./reports
```

## 项目结构

```
reprochecker/
├── cli.py              # CLI 入口（11 个命令）
├── pipeline.py         # 主流程编排（6 阶段 + 干运行）
├── config.py           # 配置管理
├── logging.py          # 日志系统
├── repo/               # 仓库克隆、分析、环境搭建
├── runner/             # 实验运行、指标捕获、资源监控
├── pdf/                # PDF 解析、LLM 数值提取
├── compare/            # 指标对比、曲线对比、资源对比
├── report/             # 评分、报告（HTML/PDF/JSON/CSV）、徽章生成
└── storage/            # SQLite 存储层
```

## 开发

```bash
# 运行测试
python -m pytest tests/ -v

# 代码检查
ruff check reprochecker/
```
