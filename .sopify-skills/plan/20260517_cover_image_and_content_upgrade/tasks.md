# 封面图 + 内容升级 — 任务清单

## 概要

| 指标 | 值 |
|------|---|
| 新增文件 | 2 个（`cover_generator.py` + `images/` 目录） |
| 修改文件 | 7 个 |
| 新增 Secrets | 4 个（可选，渐进启用） |
| 估算月成本 | $6-12（图片 API，封面 + 2-3 张板块配图/天） |
| 风险等级 | 中（涉及外部 API 调用 + 飞书自建应用） |

## Phase 1: 手绘图生成（封面 + 板块配图）

> 采用方案 B，详见 design.md「图片生成清单」。

### T1 · 新建 `cover_generator.py`

**文件**: `cover_generator.py`（项目根目录）

功能：
1. 接收 `curation_result` dict（focus 标题、highlights 关键词、日期、新增字段）
2. 构造 doc-to-sketch 风格的 style lock（所有图片共享）
3. 生成封面 prompt（16:9, 1792×1024）→ 调图片 API → 保存 `images/{date}/cover.png`
4. 根据 curation_result 内容决定是否生成板块配图：
   - focus 存在 → `focus.png`（焦点概念示意图）
   - tech_trends 非空 → `trends.png`（趋势抽象图解）
   - industry_data 非空 → `data.png`（手绘数据图表）
5. 返回生成的图片路径列表，API 不可用时返回空列表

Prompt 模板要素：
- 复用 doc-to-sketch theme-tokens 中的色彩和风格规范
- 近白纸底 (#FBFAF5)、细手绘线条、淡彩标记
- **图片文字只放短标签（≤8 字）**，不放长句
- 中央区域按图片类型变化，外壳固定

环境变量：
- `IMAGE_API_KEY`（必需，缺失时 skip）
- `IMAGE_API_URL`（必需，缺失时 skip）
- `IMAGE_MODEL`（可选，默认 gpt-image-2）

### T2 · main.py 集成图片生成

**文件**: `main.py`

在 Step 6 (Output) 之后添加：
```python
# 7. Generate cover + section images (optional)
from cover_generator import generate_images
image_paths = generate_images(curation_result, config.get("cover", {}))
if image_paths:
    logger.info(f"Generated {len(image_paths)} images: {image_paths}")
```

### T3 · daily-news.yml 添加图片相关配置

**文件**: `.github/workflows/daily-news.yml`

在 `Run news aggregator` step 的 env 中添加：
```yaml
IMAGE_API_KEY: ${{ secrets.IMAGE_API_KEY }}
IMAGE_API_URL: ${{ secrets.IMAGE_API_URL }}
```

在 `Commit and push changes` step 中添加 images/ 目录：
```yaml
git add daily-brief.md archives/ images/ 2>/dev/null || true
```

---

## Phase 2: 飞书图片上传

### T4 · feishu_push.py 添加图片批量上传

**文件**: `feishu_push.py`

新增函数：
```python
def upload_images_to_feishu(image_dir: str) -> dict[str, str]:
    """批量上传图片到飞书，返回 {filename: img_key} 映射。
    需要 FEISHU_APP_ID + FEISHU_APP_SECRET。"""
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return {}
    
    # 1. 获取 tenant_access_token
    # 2. 遍历 image_dir 下的 .png 文件
    # 3. 逐个上传，收集 img_key
    # 4. 返回映射
```

修改 `build_card()`:
- 封面图 img 元素插入 elements 开头
- 板块配图 img 元素插入对应板块的 markdown 元素之前

修改 `main()`: 在构建卡片前尝试批量上传 images/{date}/。

### T5 · feishu-push.yml 添加飞书应用 Secrets

**文件**: `.github/workflows/feishu-push.yml`

```yaml
env:
  FEISHU_WEBHOOK_URL: ${{ secrets.FEISHU_WEBHOOK_URL }}
  FEISHU_WEBHOOK_SECRET: ${{ secrets.FEISHU_WEBHOOK_SECRET }}
  FEISHU_APP_ID: ${{ secrets.FEISHU_APP_ID }}
  FEISHU_APP_SECRET: ${{ secrets.FEISHU_APP_SECRET }}
```

---

## Phase 3: 内容升级

### T6 · summarizer.py 扩展 Stage 2 输出

> 对标微信版板块，详见 background.md「板块取舍说明」+ design.md「Prompt 指令设计」。

**文件**: `summarizer.py`

修改 `STAGE2_PROMPT`，在现有输出基础上增加可选字段：

```
6. 如果候选新闻中包含行业数据/投融资数据，提取为 industry_data（最多 3 条）
   → 对标微信版「📊 行业数据」板块
7. 如果多条新闻反映同一技术趋势，归纳为 tech_trends（最多 2 条）
   → 对标微信版「🏗️ 技术趋势」板块
8. 如果有值得关注的风险/争议，归纳为 risks（最多 2 条）
   → 对标微信版「⚠️ 风险与争议」板块
9. 如果候选新闻中包含行业大佬的引言/观点，提取为 expert_quotes（最多 2 条）
   → 对标微信版「💡 AI 大佬观点」板块（升级：优先真人引言）
```

新增输出 JSON 字段（均可选，无数据时输出空数组 `[]`）：
- `industry_data`: 行业数据点
- `tech_trends`: 技术趋势归纳
- `risks`: 风险与争议
- `expert_quotes`: 专家观点

### T7 · outputs.py 新增板块渲染

> 采用"有数据才渲染"原则，详见 design.md「有数据才渲染处理逻辑」。

**文件**: `outputs.py`

在 `format_daily_brief()` 中，在"延伸阅读"之前插入新板块：

1. 📊 行业数据 — 表格形式（指标 | 数据 | 趋势 | 来源）
2. 🏗️ 技术趋势 — 趋势名 + 1 句描述 + 板块配图引用
3. ⚠️ 风险与争议 — 话题 + 简述
4. 💬 专家观点 — 人名 + 身份 + 引言（替代原"今日洞察"中的 AI 金句）

所有新板块按"有数据才渲染"原则，`brief.get(key)` 返回 None/空列表时不占空间。

同时在封面图和焦点之后插入对应图片引用：
```markdown
![cover](images/{date}/cover.png)
...
![trends](images/{date}/trends.png)
```

### T8 · feishu_push.py 兼容新板块

**文件**: `feishu_push.py`

`parse_sections()` 基于 `###` 分隔，新板块自动被识别为独立 section，**无需修改逻辑**。

验证：确保新板块不会导致卡片超过 30KB 限制。如超限，优先截断延伸阅读（现有逻辑已覆盖）。

---

## Phase 4: 文档 & 配置

### T9 · .env.example 更新

**文件**: `.env.example`

追加：
```env
# Cover image generation (optional)
IMAGE_API_KEY=
IMAGE_API_URL=
IMAGE_MODEL=gpt-image-2

# Feishu app (optional, for card images)
FEISHU_APP_ID=
FEISHU_APP_SECRET=
```

### T10 · README.md 更新

**文件**: `README.md`

1. 输出格式表新增板块说明
2. 飞书推送 section 补充"带封面图"的启用说明
3. Secrets 表格更新

---

## 依赖关系

```
Phase 1: T1 ← T2 ← T3      (图片生成)
Phase 2: T4 ← T5             (飞书上传，依赖 Phase 1 产出 images/)
Phase 3: T6 ← T7 (T8 无需改动)  (内容升级)
Phase 4: T9, T10 独立          (文档配置)

Phase 1 和 Phase 3 可并行
Phase 2 依赖 Phase 1
Phase 3 的 T7 输出图片引用，最好在 Phase 1 之后
推荐顺序: Phase 3 (T6) → Phase 1 (T1-T3) → Phase 3 (T7) → Phase 2 (T4-T5) → Phase 4
```

## 验收标准

### Phase 1
1. 本地运行 `python main.py`，如果配置了 IMAGE_API_KEY，生成 `images/{date}/cover.png` (16:9, 1792×1024)
2. 当 curation_result 包含 tech_trends/industry_data 时，额外生成对应配图
3. 未配置 IMAGE_API_KEY 时，静默跳过，pipeline 正常完成
4. 所有图片风格：近白纸底手绘中文技术插画，文字只有短标签（≤8 字）

### Phase 2
5. 配置了 FEISHU_APP_ID 时，飞书卡片展示封面图 + 板块配图
6. 未配置时，卡片退回纯文本模式（零影响）
7. 图片在飞书移动端和桌面端均正常显示

### Phase 3
8. daily-brief.md 输出包含行业数据/趋势/风险/专家观点板块（当有相关数据时）
9. 无相关数据的板块完全不出现（不留空标题、不留占位符）
10. 飞书卡片正常展示新板块，不超过 30KB 限制（预估 14-23KB，见 design.md 评估）
11. 现有板块（焦点/速览/工具/金句/延伸）格式不变

### 全局
12. 所有新功能渐进启用：不配置对应 Secrets 时完全兼容现有行为
13. Fork 用户零改动即可继续使用
14. Before/After 输出对比符合 design.md「五、Before / After 输出对比」
