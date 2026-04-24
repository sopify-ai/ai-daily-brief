"""
AI News Aggregator - Daily Brief Output

Generates structured daily briefing in README.md and archive files.
"""

import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CATEGORY_EMOJI = {
    "product": "🚀",
    "tool": "🛠️",
    "research": "🔬",
    "industry": "📊",
    "tutorial": "💡",
}

BRIEF_HEADER = """# 🤖 AI Daily Brief

> 每日 AI / 开发者工具链精选简报 · GitHub Actions + GPT 自动策展

[![Daily Update](https://github.com/{repo}/actions/workflows/daily-news.yml/badge.svg)](https://github.com/{repo}/actions/workflows/daily-news.yml)

---

"""

BRIEF_FOOTER = """
---

## 📚 往期简报

查看 [archives/](./archives/) 目录浏览历史简报。

## 🔧 工作原理

1. **数据采集**: HackerNews · GitHub Trending · HuggingFace · 阮一峰周刊 · Reddit · RSS (9 源)
2. **智能筛选**: GPT 两阶段策展 — 打分聚类 → 主编选稿
3. **每日更新**: GitHub Actions 定时运行，自动发布

👉 回到 [项目主页 (README)](./README.md)
"""


def _source_badge(source: str) -> str:
    """Format source as inline badge."""
    return f"`{source}`"


def _format_related(item: dict) -> str:
    """Format related sources as inline links."""
    related = item.get("related_sources", [])
    if not related:
        return ""
    links = " · ".join(f"[{r['source']}]({r['url']})" for r in related[:3])
    return f"  📎 延伸: {links}\n"


def format_daily_brief(curation_result: dict, config: dict) -> str:
    """Generate daily brief README content."""
    candidates = curation_result["candidates"]
    brief = curation_result["brief"]
    repo = os.environ.get("GITHUB_REPOSITORY", "sopify-ai/ai-daily-brief")
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    weekday_zh = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekday_zh[datetime.now(timezone.utc).weekday()]

    content = BRIEF_HEADER.format(repo=repo)
    content += f"## 📅 {date} {weekday}\n\n"

    # === 今日焦点 ===
    focus = brief.get("focus", {})
    focus_idx = focus.get("index", 0)
    if focus_idx < len(candidates):
        focus_item = candidates[focus_idx]
        cat_emoji = CATEGORY_EMOJI.get(focus_item.get("category", ""), "📌")
        content += f"### 📌 今日焦点\n\n"
        content += f"**[{focus_item['title']}]({focus_item['url']})** "
        content += f"{_source_badge(focus_item['source'])}"
        if focus_item["score"] > 0:
            content += f" ⭐{focus_item['score']}"
        content += "\n\n"
        content += f"> {focus.get('editorial', '')}\n\n"
        content += _format_related(focus_item)
        content += "\n"

    # === 热点速览 ===
    highlights = brief.get("highlights", [])
    if highlights:
        content += f"### 🔥 热点速览\n\n"
        for hl in highlights:
            idx = hl.get("index", 0)
            if idx < len(candidates):
                item = candidates[idx]
                cat_emoji = CATEGORY_EMOJI.get(item.get("category", ""), "•")
                editorial = hl.get("editorial", "")
                score_text = f" ⭐{item['score']}" if item["score"] > 0 else ""

                content += f"- {cat_emoji} **[{item['title']}]({item['url']})** "
                content += f"{_source_badge(item['source'])}{score_text}\n"
                if editorial:
                    content += f"  {editorial}\n"
                related_text = _format_related(item)
                if related_text:
                    content += related_text
                content += "\n"

    # === 今日工具 ===
    tools = brief.get("tools", [])
    if tools:
        content += f"### 🛠️ 今日工具\n\n"
        for tool in tools:
            idx = tool.get("index", 0)
            if idx < len(candidates):
                item = candidates[idx]
                reason = tool.get("reason", "")
                content += f"- **[{item['title']}]({item['url']})** "
                content += f"{_source_badge(item['source'])}\n"
                if reason:
                    content += f"  {reason}\n"
                content += "\n"

    # === 金句 ===
    quote = brief.get("quote", "")
    if quote:
        content += f"### 💬 一句话\n\n"
        content += f"> {quote}\n\n"

    # === 延伸阅读 (remaining candidates not selected) ===
    selected_indices = set()
    selected_indices.add(focus.get("index", -1))
    for hl in highlights:
        selected_indices.add(hl.get("index", -1))
    for tool in tools:
        selected_indices.add(tool.get("index", -1))

    remaining = [
        (i, item) for i, item in enumerate(candidates)
        if i not in selected_indices
    ]
    if remaining:
        content += f"### 📎 延伸阅读\n\n"
        for i, item in remaining[:10]:
            cat_emoji = CATEGORY_EMOJI.get(item.get("category", ""), "•")
            content += f"- {cat_emoji} [{item['title']}]({item['url']}) {_source_badge(item['source'])}\n"
        content += "\n"

    content += BRIEF_FOOTER
    return content


def write_readme(content: str, output_path: str = "README.md"):
    """Write README.md."""
    Path(output_path).write_text(content, encoding="utf-8")
    logger.info(f"README written to {output_path}")


def write_archive(curation_result: dict, config: dict):
    """Write daily archive file with full brief + raw data."""
    if not config.get("enabled", True):
        return

    directory = config.get("directory", "archives")
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    weekday_zh = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekday_zh[datetime.now(timezone.utc).weekday()]

    Path(directory).mkdir(parents=True, exist_ok=True)

    candidates = curation_result["candidates"]
    brief = curation_result["brief"]

    content = f"# AI Daily Brief — {date} {weekday}\n\n"
    content += f"> Generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\n"
    content += f"候选条目: {len(candidates)} | "

    highlights = brief.get("highlights", [])
    content += f"精选: {1 + len(highlights) + len(brief.get('tools', []))} 条\n\n"

    # Focus
    focus = brief.get("focus", {})
    focus_idx = focus.get("index", 0)
    if focus_idx < len(candidates):
        item = candidates[focus_idx]
        content += f"## 📌 焦点: [{item['title']}]({item['url']})\n\n"
        content += f"{focus.get('editorial', '')}\n\n"

    # Highlights
    content += f"## 🔥 速览\n\n"
    for hl in highlights:
        idx = hl.get("index", 0)
        if idx < len(candidates):
            item = candidates[idx]
            content += f"### [{item['title']}]({item['url']})\n\n"
            content += f"- **Source**: {item['source']}\n"
            content += f"- **Category**: {item.get('category', '')}\n"
            content += f"- **Importance**: {item.get('importance', 5)}/10\n"
            content += f"- **编辑点评**: {hl.get('editorial', '')}\n\n"

    # Full candidate list
    content += f"## 📋 全部候选 ({len(candidates)} 条)\n\n"
    for i, item in enumerate(candidates):
        content += f"{i+1}. [{item['title']}]({item['url']}) — {item['source']} "
        content += f"(importance: {item.get('importance', 5)}, topic: {item.get('topic_key', '')})\n"

    path = Path(directory) / f"{date}.md"
    path.write_text(content, encoding="utf-8")
    logger.info(f"Archive written to {path}")


async def push_to_notion(items: list[dict], config: dict):
    """Push curated items to Notion database (optional)."""
    if not config.get("enabled", False):
        return

    token = os.environ.get("NOTION_TOKEN")
    db_id = os.environ.get(config.get("database_id_env", "NOTION_DATABASE_ID"))

    if not token or not db_id:
        logger.warning("Notion integration enabled but missing NOTION_TOKEN or database ID")
        return

    import httpx
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        for item in items[:20]:
            try:
                page = {
                    "parent": {"database_id": db_id},
                    "properties": {
                        "Title": {"title": [{"text": {"content": item["title"][:100]}}]},
                        "URL": {"url": item["url"]},
                        "Source": {"select": {"name": item["source"]}},
                        "Category": {"select": {"name": item.get("category", "tool")}},
                        "Importance": {"number": item.get("importance", 5)},
                        "Date": {"date": {"start": item["published"][:10]}},
                    },
                }
                resp = await client.post(
                    "https://api.notion.com/v1/pages",
                    headers=headers,
                    json=page,
                )
                if resp.status_code != 200:
                    logger.warning(f"Notion push failed for '{item['title'][:30]}': {resp.status_code}")
            except Exception as e:
                logger.warning(f"Notion push error: {e}")

    logger.info(f"Notion: pushed {min(len(items), 20)} items")
