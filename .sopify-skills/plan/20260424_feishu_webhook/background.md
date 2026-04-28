# 飞书 Webhook 机器人推送 — 背景

## 需求来源

ai-daily-brief 每日 08:00（北京时间）通过 GitHub Actions 自动生成 `daily-brief.md`。需要在 10:00（北京时间）将简报以交互卡片形式推送到飞书群聊。

## 时间线

```
08:00 Beijing (00:00 UTC)  →  daily-news.yml 采集 + 策展 + 生成 daily-brief.md
                                ↓ 提交到仓库
10:00 Beijing (02:00 UTC)  →  feishu-push.yml 读取 daily-brief.md → 构建卡片 → POST 飞书
```

生成和推送分离，互不阻塞。

## 现有输出通道

| 通道 | 状态 | 触发方式 |
|------|------|---------|
| `daily-brief.md` | ✅ 已有 | daily-news.yml (08:00) |
| `archives/` | ✅ 已有 | 同上 |
| Notion | ⚠️ 预留 | 同上 |
| **飞书群** | ❌ 新增 | feishu-push.yml (10:00) |

## 架构决策

**不需要服务层**。GitHub Actions 定时触发 = 推送服务。飞书自定义机器人 Webhook 只需要一个 HTTP POST。

**推送与生成解耦**：独立 workflow + 独立脚本，不修改现有 pipeline 代码。理由：
1. 生成失败不影响推送逻辑
2. 推送时间可独立调整
3. 可手动触发推送（不需要重跑采集）
4. 现有 `main.py` / `outputs.py` 零侵入

## Fork-Friendly 设计原则

本方案面向两类用户：仓库 owner 和 fork 用户。核心目标：**fork 后只需设 1 个 Secret 即可推送，零代码改动。**

| 原则 | 实现 |
|------|------|
| 零配置按钮链接 | `$GITHUB_REPOSITORY` 自动推导，不需手填 URL |
| 渐进启用 | 不设 `FEISHU_WEBHOOK_URL` 时跳过推送，不影响其他 CI |
| 文档自包含 | README 新增飞书推送 section，包含完整启用步骤 |
| 最小 Secrets | 必需 1 个（`FEISHU_WEBHOOK_URL`），可选 1 个（`FEISHU_WEBHOOK_SECRET`） |

## 约束条件

- 飞书自定义机器人 Webhook，无需应用审批
- Webhook URL + 可选签名密钥通过 GitHub Secrets 注入
- 交互卡片消息体上限 ~30KB
- 推送前校验 brief 是否当天更新，避免推送过期内容
- `FEISHU_WEBHOOK_URL` 缺失时 exit 0（不是 exit 1），保证 fork 用户 CI 不红

