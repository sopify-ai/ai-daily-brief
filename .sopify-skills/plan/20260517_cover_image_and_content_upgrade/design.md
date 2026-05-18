# 封面图 + 内容升级 — 技术设计

## 一、手绘图生成（封面 + 板块配图）

> 对标微信版视觉体验。采用方案 B：封面 + 板块配图，文字内容保持 Markdown。

### 方案架构

```
daily-news.yml (08:00)
    ↓
 main.py → curation_result
    ↓
 cover_generator.py           ← 新增：生成封面 + 板块配图
    ↓
 daily-brief.md               ← Markdown 文本（含图片引用）
 images/YYYY-MM-DD/           ← 当日所有图片
   ├── cover.png              ← 封面图
   ├── focus.png              ← 焦点配图（可选）
   ├── trends.png             ← 趋势配图（可选）
   └── data.png               ← 数据配图（可选）

feishu-push.yml (08:30)
    ↓
 feishu_push.py
    ↓
 1. 批量上传 images/*.png → Feishu Open API → img_keys
 2. 构建卡片 JSON（含 img 元素）
 3. POST → Webhook
```

### 图片生成清单

| 图片 | 文字量 | 生成条件 | Prompt 核心要素 |
|------|--------|----------|----------------|
| **cover.png** | 日期 + 3-5 关键词标签 | 每日必生成 | 日期、焦点关键词、风格锁定 |
| **focus.png** | 焦点标题关键词（5-8 字） | focus 存在时 | 焦点新闻的概念示意图 |
| **trends.png** | 2-3 个趋势短标签 | tech_trends 非空时 | 技术趋势抽象图解 |
| **data.png** | 数字 + 短标签 | industry_data 非空时 | 数据可视化手绘图表 |

> ⚠️ **文字准确性边界**：AI 图片生成中文准确率：3-8 字 ~85-90%，15+ 字急剧下降。
> 因此图片只放短标签/关键词，编辑评论等长文本保留 Markdown。

### 每日 Prompt 结构

```
[Style lock - 固定不变，所有图片共享]
  近白纸底 (#FBFAF5) / 细手绘线 / 淡彩标记 / 中文短文字
  16:9 / 角标网格 / 无边框 / 页码 / doc-to-sketch v6

[Daily variable - 封面]
  标题: "AI Daily Brief · {日期} {星期}"
  关键词标签: {3-5 个从 highlights 提取的关键词}
  中央区域: 与焦点主题相关的技术概念图

[Daily variable - 板块配图]
  根据板块类型切换中央区域内容:
  - focus.png: 焦点新闻的核心概念/技术示意
  - trends.png: 多个趋势方向的关系/流向图
  - data.png: 数据点的手绘图表/趋势线
```

### 成本估算

| 方案 | 图片数/天 | 单价 | 月成本 | CI 耗时 |
|------|----------|------|--------|---------|
| 纯封面 (原 plan) | 1 | ~$0.10 | ~$3 | ~15s |
| **封面 + 板块配图 (当前)** | **2-4** | **~$0.10** | **$6-12** | **30-60s** |
| 全图片日报 (不推荐) | 6-10 | ~$0.10 | $18-30 | 60-150s |

### 飞书图片上传设计

#### 前置条件

需要创建飞书自建应用：

1. 登录 [飞书开放平台](https://open.feishu.cn/)
2. 创建应用 → 获取 `FEISHU_APP_ID` + `FEISHU_APP_SECRET`
3. 应用权限：`im:resource`（上传图片）
4. 不需要审批/发布，内部应用即可

#### API 调用流程

```python
# 1. 获取 tenant_access_token
resp = httpx.post(
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}
)
token = resp.json()["tenant_access_token"]

# 2. 上传图片
resp = httpx.post(
    "https://open.feishu.cn/open-apis/im/v1/images",
    headers={"Authorization": f"Bearer {token}"},
    data={"image_type": "message"},
    files={"image": open("cover.png", "rb")}
)
img_key = resp.json()["data"]["image_key"]
```

#### 卡片 JSON 变化

在 `elements` 数组开头插入图片元素：

```json
{
  "tag": "img",
  "img_key": "img_xxxxxxxxx",
  "alt": {"tag": "plain_text", "content": "AI Daily Brief 封面"},
  "mode": "fit_horizontal",
  "preview": true
}
```

### 飞书应用凭证分析

#### 能否复用 doc-to-sketch 的默认共享应用？

**结论：不能直接复用。** 原因：

| 维度 | doc-to-sketch 应用 (cli_aa8f1a91c5f8dcc5) | 日报封面上传需要 |
|------|-------------------------------------------|---------------|
| Token 类型 | user_access_token (OAuth 浏览器授权) | tenant_access_token (纯后端 API) |
| 权限 | `docx:document:readonly` `wiki:wiki:readonly` `offline_access` | `im:resource` (图片上传) |
| 运行环境 | 本地终端（可弹浏览器做 OAuth） | CI / GitHub Actions（无浏览器） |

三个不可调和的差异：
1. **权限不匹配**：共享应用只有文档只读权限，没有 `im:resource`（图片上传必需）
2. **Token 类型不兼容**：CI 无法走浏览器 OAuth 流程，只能用 `tenant_access_token`
3. **影响范围问题**：给共享应用加 `im:resource` 权限会影响所有 doc-to-sketch 用户

#### 推荐方案：新建独立飞书自建应用

复用 doc-to-sketch 的**设计模式**（默认嵌入凭证 + 环境变量覆盖），但用独立的应用：

1. 在飞书开放平台创建新应用（例如 "AI Daily Brief Bot"）
2. 只开 `im:resource` 权限
3. 走 `tenant_access_token`（`POST /auth/v3/tenant_access_token/internal`），无需浏览器
4. 凭证可以嵌入代码作为默认值（和 doc-to-sketch 一样的零配置模式），也可通过 FEISHU_APP_ID / FEISHU_APP_SECRET 覆盖

```python
# 获取 tenant_access_token（无需浏览器，适合 CI）
resp = httpx.post(
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    json={"app_id": APP_ID, "app_secret": APP_SECRET}
)
token = resp.json()["tenant_access_token"]  # 有效期 2 小时
```

飞书自建应用创建步骤：
1. 登录 https://open.feishu.cn/
2. 创建企业自建应用 → 获取 App ID + App Secret
3. 权限管理 → 添加 `im:resource`（上传图片）
4. 版本管理 → 创建版本 → 发布（内部应用即可，无需审批）

### 渐进启用设计（fork-friendly）

| 配置状态 | 行为 |
|---------|------|
| 无 IMAGE_API_KEY | 跳过所有图片生成，日志提示 |
| 有 IMAGE_API_KEY，无 FEISHU_APP_ID | 生成图片 → commit 到仓库，飞书卡片不带图 |
| 有 IMAGE_API_KEY + FEISHU_APP_ID | 完整流程：生成 → 上传 → 卡片带图 |
| 都没有 | 和当前完全一致，零影响 |

---

## 二、内容层升级（对标微信版）

> 对标见 background.md「板块取舍说明」。以下 4 个新字段对应微信版的行业数据/技术趋势/风险争议/专家观点。

### 策展 Prompt 优化 (summarizer.py)

#### Stage 2 Prompt 增强

当前 STAGE2_PROMPT 产出：focus + highlights + tools + quote + related_groups

升级后增加（**全部可选，有数据才输出**）：

```json
{
  "focus": {"..."},
  "highlights": ["..."],
  "tools": ["..."],
  "quote": "...",
  "related_groups": ["..."],
  // ---- 新增（均可选）----
  "industry_data": [
    {"metric": "Anthropic 年化收入", "value": "$40B+", "trend": "up", "source": "..."}
  ],
  "tech_trends": [
    {"topic": "AI 安全攻防战", "summary": "...", "items": [0, 2, 8]}
  ],
  "risks": [
    {"topic": "企业信任问题", "summary": "EY 撤回 AI 生成研究..."}
  ],
  "expert_quotes": [
    {"person": "Sundar Pichai", "role": "Google CEO", "quote": "...", "context": "..."}
  ]
}
```

#### Prompt 指令设计

```
6. 如果候选新闻中包含投融资/收入/市场数据，提取为 industry_data（最多 3 条）。
   没有明确数据时输出空数组 []。
7. 如果多条新闻反映同一技术趋势，归纳为 tech_trends（最多 2 条）。
   不足 3 条相关新闻时不要强行归纳，输出 []。
8. 如果有值得关注的风险/争议/负面信号，归纳为 risks（最多 2 条）。
   无明显风险时输出 []。
9. 如果候选新闻中包含行业大佬/专家的直接引言/观点，提取为 expert_quotes（最多 2 条）。
   优先使用新闻中的真人原话，不要 AI 创作。无引言时输出 []。
```

#### "有数据才渲染" 处理逻辑

```python
# outputs.py 中新板块渲染逻辑
for section_key, section_title, renderer in [
    ("industry_data", "📊 行业数据",  render_industry_data),
    ("tech_trends",   "🏗️ 技术趋势", render_tech_trends),
    ("risks",         "⚠️ 风险与争议", render_risks),
    ("expert_quotes", "💬 专家观点",  render_expert_quotes),
]:
    data = brief.get(section_key)
    # None、空列表、空字符串 → 全部跳过
    if not data:
        continue
    content += f"### {section_title}\n\n"
    content += renderer(data)
    content += "\n---\n\n"
```

#### 影响范围

| 文件 | 变更 | 微信对标板块 |
|------|------|-------------|
| summarizer.py | STAGE2_PROMPT 扩展输出字段 | 行业数据 / 技术趋势 / 风险争议 / 专家观点 |
| outputs.py | format_daily_brief() 新增板块渲染 | 同上 |
| feishu_push.py | parse_sections() 自动兼容新板块 | 自动 — 基于 `###` 分隔 |

#### 风险评估

- Stage 2 输出结构扩展，向后兼容（新字段可选，`brief.get()` 容错）
- GPT 可能在数据不足时"编造"数据 → Prompt 明确"无数据时输出 []"
- Token 消耗增加约 15-20%（新指令 + 新输出字段）

### 飞书卡片 30KB 限制影响评估

当前卡片 JSON 典型大小：~12-18KB

新增内容估算：
| 板块 | 平均 JSON 大小 | 出现频率 |
|------|---------------|---------|
| industry_data (3 条) | ~1.5KB | ~40% 的天 |
| tech_trends (2 条) | ~1.2KB | ~50% 的天 |
| risks (2 条) | ~0.8KB | ~30% 的天 |
| expert_quotes (2 条) | ~1.0KB | ~30% 的天 |
| 板块配图 img 元素 (2-3 个) | ~0.5KB | 有图时 |
| **合计新增** | **~2-5KB** | — |

**预估升级后**：14-23KB，仍在 30KB 限制内。极端情况（所有新板块 + 8 条速览全量）可能触及 25KB+，现有截断逻辑已覆盖（优先截断"延伸阅读"）。

### 摘要深度增强

当前：每条 highlights 只有 1 句编辑观点（50 字以内）
目标：焦点和 Top 3 highlights 提供 2-3 句深度评论

修改 STAGE2_PROMPT 中 highlights 的要求：
- Top 3 highlights：写 2 句评论（第 1 句为什么重要，第 2 句开发者行动建议）
- 其余 highlights：维持 1 句

### 周末特刊（可选）

每周六或周日输出"本周回顾"而非日报：
- 回顾本周 7 天的焦点
- 总结趋势与矛盾
- 需要读取 archives/ 目录近 7 天的归档

---

## 三、新增文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `cover_generator.py` | 新增 | 封面 + 板块配图 prompt 构造 + 图片 API 批量调用 |
| `images/` | 新增目录 | 按日期存放当日生成的图片 `images/YYYY-MM-DD/` |
| `feishu_push.py` | 修改 | 添加图片批量上传逻辑 + 卡片 img 元素 |
| `summarizer.py` | 修改 | STAGE2_PROMPT 扩展输出字段 |
| `outputs.py` | 修改 | 新增板块渲染 + 图片引用（行业数据/趋势/风险/专家观点）|
| `main.py` | 修改 | pipeline 末尾添加图片生成步骤 |
| `daily-news.yml` | 修改 | 添加 IMAGE_API_KEY/URL secrets + commit images/ |
| `feishu-push.yml` | 修改 | 添加 FEISHU_APP_ID/SECRET secrets |
| `.env.example` | 修改 | 追加图片 API + 飞书应用变量 |
| `README.md` | 修改 | 文档更新 |

## 四、新增 Secrets 清单

| Secret | 必需 | 说明 |
|--------|------|------|
| `IMAGE_API_KEY` | 图片功能必需 | 图片生成 API 密钥 |
| `IMAGE_API_URL` | 图片功能必需 | 图片生成 API 端点 |
| `FEISHU_APP_ID` | 飞书带图必需 | 飞书自建应用 App ID |
| `FEISHU_APP_SECRET` | 飞书带图必需 | 飞书自建应用 App Secret |

---

## 五、Before / After 输出对比

### Before（当前 daily-brief.md）

```markdown
## 📅 2026-05-17 周日

### 📌 今日焦点
**[Greg Brockman 接管 OpenAI 产品策略](...)** · `TechCrunch AI`
> 2 句编辑评论...

### 🔥 热点速览
**1. [ChatGPT 接入银行账户](...)** · `TechCrunch AI`
1 句编辑观点（50 字以内）
...

### 🛠️ 今日工具
**[Zerostack](...)** · `HackerNews`
1 句推荐理由

### 💡 今日洞察
> 金句（AI 生成）

### 📎 延伸阅读
- 🚀 [...]
```

### After（升级后 daily-brief.md）

```markdown
## 📅 2026-05-17 周日

![cover](images/2026-05-17/cover.png)

### 📌 今日焦点
**[Greg Brockman 接管 OpenAI 产品策略](...)** · `TechCrunch AI`
> OpenAI 产品策略由联合创始人直接接管...（2 句深评，同前）

![focus](images/2026-05-17/focus.png)    ← 焦点配图

### 🔥 热点速览
**1. [ChatGPT 接入银行账户](...)** · `TechCrunch AI`
Top 3 写 2 句评论（第 1 句为什么重要，第 2 句行动建议）← 深度升级
...

### 🛠️ 今日工具
（同前）

### 📊 行业数据                            ← 新增板块
| 指标 | 数据 | 趋势 | 来源 |
|------|------|------|------|
| Anthropic 年化收入 | $40B+ | 📈 | TechCrunch |

### 🏗️ 技术趋势                           ← 新增板块
**AI 安全攻防战** — 多智能体安全、ArXiv 禁令、Google 反操纵规则
形成三角：学术→平台→监管同步收紧

![trends](images/2026-05-17/trends.png)  ← 趋势配图

### ⚠️ 风险与争议                          ← 新增板块
**企业 AI 误用** — EY 撤回 AI 生成研究、多家企业"AI 失心疯"讨论热度高

### 💬 专家观点                            ← 升级板块（真人引言优先）
**Mitchell Hashimoto** (HashiCorp 创始人):
> "I believe there are entire companies right now under AI psychosis"

### 💡 今日洞察
> 金句（保留）

### 📎 延伸阅读
（同前）
```
