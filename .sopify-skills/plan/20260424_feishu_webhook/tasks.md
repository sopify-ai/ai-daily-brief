# 飞书 Webhook 机器人推送 — 任务清单

## 概要

| 指标 | 值 |
|------|---|
| 新增文件 | 2 个（`feishu_push.py` + `feishu-push.yml`） |
| 修改文件 | 2 个（`.env.example` + `README.md`） |
| 现有代码变更 | 0 行（仅文档追加） |
| 新增依赖 | 0（httpx 已有） |
| 风险等级 | 低 |

## 任务列表

### T1 · 新建 `feishu_push.py` 推送脚本

**文件**: `feishu_push.py`（项目根目录，和 `main.py` 同级）

功能：
1. 读取 `daily-brief.md`
2. 校验日期（`## 📅 YYYY-MM-DD`）是否为当天
3. 按 `### ` 分隔符解析为板块（焦点/速览/工具/金句/延伸/数据）
4. 清理不兼容元素（badge 图片、表格 → 纯文本）
5. 构建飞书交互卡片 JSON
6. 可选签名校验
7. POST 到 Webhook URL
8. 校验返回 `StatusCode == 0`

环境变量：
- `FEISHU_WEBHOOK_URL`（必需，缺失时 exit 0 + warning，不是 exit 1）
- `FEISHU_WEBHOOK_SECRET`（可选）
- `GITHUB_REPOSITORY`（Actions 自动提供，用于推导按钮链接）
- `BRIEF_URL`（可选，本地运行时手动指定按钮链接）

### T2 · 新建 `.github/workflows/feishu-push.yml`

**文件**: `.github/workflows/feishu-push.yml`

```yaml
name: Feishu Push
on:
  schedule:
    - cron: '0 2 * * *'        # 02:00 UTC = 10:00 Beijing
  workflow_dispatch:             # 支持手动触发

jobs:
  push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install httpx
      - run: python feishu_push.py
        env:
          FEISHU_WEBHOOK_URL: ${{ secrets.FEISHU_WEBHOOK_URL }}
          FEISHU_WEBHOOK_SECRET: ${{ secrets.FEISHU_WEBHOOK_SECRET }}
```

### T3 · `.env.example` 追加飞书变量

**文件**: `.env.example`

追加：
```env
# Feishu (Lark) webhook bot
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-hook-id
FEISHU_WEBHOOK_SECRET=           # optional, for signed webhooks
```

### T4 · README.md 追加飞书推送说明

**文件**: `README.md`

在 `🤖 自动部署 (GitHub Actions)` section 之后追加 `📱 飞书推送（可选）` section：
- 3 步启用指南（创建群机器人 → 设 Secret → 完成）
- Secrets 表格
- 手动触发说明
- 项目结构表更新（加入 `feishu_push.py` 和 `feishu-push.yml`）

## 依赖关系

```
T1 (脚本) ← T2 (workflow 调用 T1)
T3 (env 模板) 独立
T4 (README) 独立
```

T1 完成后即可本地测试：`FEISHU_WEBHOOK_URL=xxx python feishu_push.py`

## 验收标准

1. 本地运行 `python feishu_push.py`，飞书群收到交互卡片
2. 卡片包含：焦点 + 速览 + 工具 + 金句 + 延伸 + 数据概览 + "查看完整简报"按钮
3. `daily-brief.md` 日期不是当天时，脚本跳过推送并记 warning，**exit 0**
4. **Webhook URL 缺失时，打印 warning 并 exit 0（不影响 CI）**
5. GitHub Actions 手动触发 `workflow_dispatch` 能正常推送
6. 现有 `daily-news.yml` 和 `main.py` 零修改
7. **Fork 用户只需设 `FEISHU_WEBHOOK_URL` 一个 Secret 即可启用**
8. **按钮链接自动指向 fork 用户自己的仓库**

## 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `feishu_push.py` | 新增 | 独立推送脚本 |
| `.github/workflows/feishu-push.yml` | 新增 | 独立定时 workflow |
| `.env.example` | 修改 | 追加飞书环境变量模板 |
| `README.md` | 修改 | 追加飞书推送启用说明 |

