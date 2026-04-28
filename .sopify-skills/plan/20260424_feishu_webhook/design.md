# 飞书 Webhook 机器人推送 — 技术设计

## 方案概述

新增独立脚本 `feishu_push.py` + 独立 workflow `feishu-push.yml`，读取已生成的 `daily-brief.md`，转换为飞书交互卡片，POST 到 Webhook。**不修改现有 pipeline 任何代码。**

## 架构

```
daily-news.yml (08:00)          feishu-push.yml (10:00)
    ↓                               ↓
 main.py                        feishu_push.py
    ↓                               ↓
 daily-brief.md ──────────────→ 读取 md
                                    ↓
                                校验日期
                                    ↓
                                解析为板块
                                    ↓
                                构建卡片 JSON
                                    ↓
                                POST → 飞书 Webhook
                                    ↓
                                群聊收到卡片 ✓
```

## 核心逻辑：Markdown → 飞书卡片

### 解析策略

`daily-brief.md` 结构稳定（由 `format_daily_brief()` 模板生成），直接按 `###` 分隔符切分板块：

```python
sections = re.split(r'^### ', content, flags=re.MULTILINE)
# → ["header...", "📌 今日焦点\n...", "🔥 热点速览\n...", ...]
```

### 飞书 Markdown 兼容处理

| 原始元素 | 飞书卡片支持 | 处理方式 |
|---------|------------|---------|
| `**加粗**` | ✅ | 保留 |
| `[链接](url)` | ✅ | 保留 |
| `> 引用` | ✅ | 保留 |
| `- 列表` | ✅ | 保留 |
| `` `行内代码` `` | ✅ | 保留 |
| `[![badge](img)](url)` | ❌ | 移除 |
| `\| 表格 \|` | ❌ | 转为 `key: value` 文本 |
| `---` 分隔线 | — | 用 `{"tag": "hr"}` 替代 |

### 卡片结构

```json
{
  "msg_type": "interactive",
  "card": {
    "header": {
      "title": {"tag": "plain_text", "content": "🤖 AI Daily Brief · 2026-04-24 周五"},
      "template": "blue"
    },
    "elements": [
      {"tag": "markdown", "content": "**📌 今日焦点**\n\n[GPT-5.5](url) · `HackerNews` ⭐\n\n> 编辑评论...\n\n📎 延伸: [来源1](url) · [来源2](url)"},
      {"tag": "hr"},
      {"tag": "markdown", "content": "**🔥 热点速览**\n\n**1.** [标题](url) · `来源`\n评论\n\n**2.** ..."},
      {"tag": "hr"},
      {"tag": "markdown", "content": "**🛠️ 今日工具**\n\n[工具名](url)\n推荐理由"},
      {"tag": "hr"},
      {"tag": "markdown", "content": "> 💬 金句..."},
      {"tag": "hr"},
      {"tag": "markdown", "content": "**📎 延伸阅读**\n\n- [标题1](url) · `来源`\n- [标题2](url) · `来源`\n..."},
      {"tag": "note", "elements": [
        {"tag": "plain_text", "content": "📊 11源 · 150篇 → 10精选 | 生成于 2026-04-24 06:03 UTC"}
      ]},
      {"tag": "action", "actions": [{
        "tag": "button",
        "text": {"tag": "plain_text", "content": "📰 查看完整简报"},
        "url": "https://github.com/Li-Sanze/ai-daily-brief/blob/main/daily-brief.md",
        "type": "primary"
      }]}
    ]
  }
}
```

## 日期校验

推送前检查 `daily-brief.md` 中的日期行（`## 📅 2026-04-24`）是否为当天：

```python
today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
if today not in content:
    logger.warning(f"Brief date mismatch, skipping push")
    return
```

避免 08:00 生成失败后 10:00 推送过期内容。

## 签名校验（可选）

飞书 Webhook 支持签名验证：

```python
import hmac, hashlib, base64, time

def sign_webhook(secret: str) -> tuple[str, str]:
    timestamp = str(int(time.time()))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode(), digestmod=hashlib.sha256).digest()
    sign = base64.b64encode(hmac_code).decode()
    return timestamp, sign
```

启用时，POST body 额外携带 `timestamp` + `sign` 字段。

## 错误处理

- **Webhook URL 缺失** → `print("⚠️ FEISHU_WEBHOOK_URL not set, skipping.") → exit 0`
  - **不是 exit 1**：fork 用户如果没配飞书，CI 不应该报红
- brief 日期不匹配 → 跳过，记 warning，exit 0
- POST 失败 → 重试 1 次（间隔 5s），仍失败则记 error，exit 1
- 飞书返回 `StatusCode != 0` → 记 error + StatusMessage，exit 1

## 按钮链接自动推导

```python
# GitHub Actions 环境自动提供 GITHUB_REPOSITORY
repo = os.environ.get("GITHUB_REPOSITORY", "")
brief_url = os.environ.get("BRIEF_URL") or (
    f"https://github.com/{repo}/blob/main/daily-brief.md" if repo else None
)
```

| 场景 | 来源 | 按钮链接 |
|------|------|---------|
| GitHub Actions（原仓库） | `$GITHUB_REPOSITORY` | `github.com/Li-Sanze/ai-daily-brief/...` |
| GitHub Actions（fork） | `$GITHUB_REPOSITORY` | `github.com/user123/ai-daily-brief/...` |
| 本地运行 | `$BRIEF_URL` 环境变量 | 用户自定义 |
| 本地运行（未设） | — | 不显示按钮 |

## README 新增 Section 设计

在 README.md `🤖 自动部署` 之后新增：

```markdown
## 📱 飞书推送（可选）

支持将每日简报以交互卡片推送到飞书群。Fork 用户只需 3 步启用：

### 1. 创建飞书群机器人
群设置 → 群机器人 → 添加机器人 → 自定义机器人 → 复制 Webhook URL

### 2. 设置 GitHub Secret
仓库 Settings → Secrets → Actions → New：
| Secret | 说明 |
|--------|------|
| `FEISHU_WEBHOOK_URL` | Webhook 地址（必需） |
| `FEISHU_WEBHOOK_SECRET` | 签名密钥（可选，安全加固） |

### 3. 完成
每天 10:00（北京时间）自动推送。也可在 Actions → Feishu Push 手动触发。
```

