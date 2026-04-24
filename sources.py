"""
AI News Aggregator - Data Sources

Fetches news from: HackerNews, GitHub Trending, HuggingFace, RSS feeds,
阮一峰周刊, Reddit r/LocalLLaMA.
"""

import re
import httpx
import feedparser
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    summary: str = ""
    score: int = 0
    published: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tags: list[str] = field(default_factory=list)
    category: str = ""

    @property
    def age_hours(self) -> float:
        delta = datetime.now(timezone.utc) - self.published
        return delta.total_seconds() / 3600


async def fetch_hackernews(config: dict) -> list[NewsItem]:
    """Fetch top stories from HackerNews API."""
    if not config.get("enabled", True):
        return []

    top_n = config.get("top_n", 30)
    min_score = config.get("min_score", 50)
    items = []

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
        story_ids = resp.json()[:top_n * 2]  # fetch extra to filter

        for sid in story_ids:
            try:
                resp = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
                story = resp.json()
                if not story or story.get("type") != "story":
                    continue
                if story.get("score", 0) < min_score:
                    continue

                published = datetime.fromtimestamp(story.get("time", 0), tz=timezone.utc)
                items.append(NewsItem(
                    title=story.get("title", ""),
                    url=story.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                    source="HackerNews",
                    score=story.get("score", 0),
                    published=published,
                    tags=["hackernews"],
                ))

                if len(items) >= top_n:
                    break
            except Exception as e:
                logger.warning(f"Failed to fetch HN story {sid}: {e}")
                continue

    logger.info(f"HackerNews: fetched {len(items)} stories")
    return items


async def fetch_github_trending(config: dict) -> list[NewsItem]:
    """Fetch trending repos from GitHub (unofficial scrape-free approach via search API)."""
    if not config.get("enabled", True):
        return []

    languages = config.get("languages", ["python", "typescript"])
    since = config.get("since", "daily")
    items = []

    # Use GitHub search API: repos created/pushed recently with many stars
    date_map = {"daily": 1, "weekly": 7, "monthly": 30}
    days = date_map.get(since, 1)
    since_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    async with httpx.AsyncClient(timeout=30) as client:
        for lang in languages:
            try:
                query = f"language:{lang} pushed:>{since_date} stars:>10"
                resp = await client.get(
                    "https://api.github.com/search/repositories",
                    params={"q": query, "sort": "stars", "order": "desc", "per_page": 10},
                    headers={"Accept": "application/vnd.github.v3+json"},
                )
                if resp.status_code != 200:
                    logger.warning(f"GitHub API returned {resp.status_code} for {lang}")
                    continue

                for repo in resp.json().get("items", [])[:5]:
                    items.append(NewsItem(
                        title=f"{repo['full_name']}: {repo.get('description', '')[:100]}",
                        url=repo["html_url"],
                        source="GitHub Trending",
                        score=repo.get("stargazers_count", 0),
                        published=datetime.fromisoformat(
                            repo["pushed_at"].replace("Z", "+00:00")
                        ),
                        tags=["github", lang] + (repo.get("topics", []) or [])[:5],
                    ))
            except Exception as e:
                logger.warning(f"Failed to fetch GitHub trending for {lang}: {e}")

    logger.info(f"GitHub Trending: fetched {len(items)} repos")
    return items


async def fetch_huggingface(config: dict) -> list[NewsItem]:
    """Fetch daily papers and trending models from HuggingFace."""
    if not config.get("enabled", True):
        return []

    items = []
    async with httpx.AsyncClient(timeout=30) as client:
        # Daily papers
        if config.get("daily_papers", True):
            try:
                resp = await client.get("https://huggingface.co/api/daily_papers")
                if resp.status_code == 200:
                    for paper in resp.json()[:config.get("top_n", 10)]:
                        paper_info = paper.get("paper", {})
                        items.append(NewsItem(
                            title=paper_info.get("title", "Untitled"),
                            url=f"https://huggingface.co/papers/{paper_info.get('id', '')}",
                            source="HuggingFace Papers",
                            score=paper.get("numLikes", 0),
                            published=datetime.now(timezone.utc),
                            tags=["huggingface", "paper", "research"],
                        ))
            except Exception as e:
                logger.warning(f"Failed to fetch HF daily papers: {e}")

        # Trending models
        if config.get("trending_models", True):
            try:
                resp = await client.get(
                    "https://huggingface.co/api/models",
                    params={"sort": "trending", "limit": config.get("top_n", 10)},
                )
                if resp.status_code == 200:
                    for model in resp.json():
                        items.append(NewsItem(
                            title=f"🤗 {model.get('modelId', 'unknown')}",
                            url=f"https://huggingface.co/{model.get('modelId', '')}",
                            source="HuggingFace Models",
                            score=model.get("likes", 0),
                            published=datetime.now(timezone.utc),
                            tags=["huggingface", "model"] + (model.get("tags", []) or [])[:3],
                        ))
            except Exception as e:
                logger.warning(f"Failed to fetch HF trending models: {e}")

    logger.info(f"HuggingFace: fetched {len(items)} items")
    return items


async def fetch_rss_feeds(config: dict) -> list[NewsItem]:
    """Fetch and parse RSS feeds."""
    if not config.get("enabled", True):
        return []

    items = []
    feeds = config.get("feeds", [])

    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for feed_cfg in feeds:
            try:
                resp = await client.get(feed_cfg["url"])
                if resp.status_code != 200:
                    logger.warning(f"RSS {feed_cfg['name']}: HTTP {resp.status_code}")
                    continue

                parsed = feedparser.parse(resp.text)
                for entry in parsed.entries[:10]:
                    published = datetime.now(timezone.utc)
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        from calendar import timegm
                        published = datetime.fromtimestamp(
                            timegm(entry.published_parsed), tz=timezone.utc
                        )

                    summary = ""
                    if hasattr(entry, "summary"):
                        # Strip HTML tags naively
                        import re
                        summary = re.sub(r"<[^>]+>", "", entry.summary)[:200]

                    items.append(NewsItem(
                        title=entry.get("title", "Untitled"),
                        url=entry.get("link", ""),
                        source=feed_cfg["name"],
                        summary=summary,
                        published=published,
                        tags=["rss", feed_cfg["name"].lower().replace(" ", "-")],
                    ))
            except Exception as e:
                logger.warning(f"Failed to fetch RSS {feed_cfg['name']}: {e}")

    logger.info(f"RSS Feeds: fetched {len(items)} items from {len(feeds)} feeds")
    return items


async def fetch_ruanyf_weekly(config: dict) -> list[NewsItem]:
    """Fetch latest issue from ruanyf/weekly (阮一峰科技爱好者周刊)."""
    if not config.get("enabled", True):
        return []

    items = []
    repo = config.get("repo", "ruanyf/weekly")

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            # Find latest issue number from recent commits
            resp = await client.get(
                f"https://api.github.com/repos/{repo}/commits",
                params={"per_page": 10},
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code != 200:
                logger.warning(f"ruanyf/weekly commits API returned {resp.status_code}")
                return []

            issue_num = None
            for commit in resp.json():
                msg = commit.get("commit", {}).get("message", "")
                match = re.search(r"issue[_\s-]*(\d+)", msg, re.IGNORECASE)
                if match:
                    issue_num = match.group(1)
                    break

            if not issue_num:
                logger.warning("Could not find latest ruanyf/weekly issue number")
                return []

            # Fetch the markdown file
            file_resp = await client.get(
                f"https://raw.githubusercontent.com/{repo}/master/docs/issue-{issue_num}.md"
            )
            if file_resp.status_code != 200:
                logger.warning(f"Failed to fetch issue-{issue_num}.md: {file_resp.status_code}")
                return []

            items = _parse_ruanyf_markdown(file_resp.text, config)
            logger.info(f"阮一峰周刊: fetched {len(items)} items from issue #{issue_num}")

        except Exception as e:
            logger.warning(f"Failed to fetch ruanyf/weekly: {e}")

    if not items:
        logger.info("阮一峰周刊: fetched 0 items")
    return items


def _parse_ruanyf_markdown(
    markdown: str, config: dict, published: datetime | None = None
) -> list[NewsItem]:
    """Extract linked items from ruanyf weekly markdown."""
    if published is None:
        published = datetime.now(timezone.utc)

    items = []
    max_items = config.get("max_items", 20)

    # Match markdown links: [title](url) with optional surrounding text as summary
    link_pattern = re.compile(
        r"(?:^|\n).*?\[([^\]]{5,})\]\((https?://[^\)]+)\)(.{0,200})",
        re.MULTILINE,
    )

    seen_urls: set[str] = set()
    for match in link_pattern.finditer(markdown):
        title = match.group(1).strip()
        url = match.group(2).strip()
        context = match.group(3).strip()

        # Skip navigation/self links
        if "github.com/ruanyf/weekly" in url:
            continue
        if url.rstrip("/").lower() in seen_urls:
            continue
        seen_urls.add(url.rstrip("/").lower())

        # Clean up context as summary
        summary = re.sub(r"\[.*?\]\(.*?\)", "", context)
        summary = re.sub(r"[#*`>]", "", summary).strip()
        summary = summary[:200]

        items.append(NewsItem(
            title=title,
            url=url,
            source="阮一峰周刊",
            summary=summary,
            published=published,
            tags=["ruanyf", "weekly", "chinese-tech"],
        ))

        if len(items) >= max_items:
            break

    return items


async def fetch_reddit(config: dict) -> list[NewsItem]:
    """Fetch hot posts from configured subreddits (default: r/LocalLLaMA)."""
    if not config.get("enabled", True):
        return []

    subreddits = config.get("subreddits", ["LocalLLaMA"])
    top_n = config.get("top_n", 15)
    min_score = config.get("min_score", 50)
    items = []

    async with httpx.AsyncClient(
        timeout=30,
        headers={"User-Agent": "ai-daily-brief/1.0"},
        follow_redirects=True,
    ) as client:
        for sub in subreddits:
            try:
                resp = await client.get(
                    f"https://www.reddit.com/r/{sub}/hot.json",
                    params={"limit": top_n * 2},
                )
                if resp.status_code != 200:
                    logger.warning(f"Reddit r/{sub} returned {resp.status_code}")
                    continue

                posts = resp.json().get("data", {}).get("children", [])
                count = 0
                for post in posts:
                    data = post.get("data", {})
                    if data.get("stickied"):
                        continue
                    score = data.get("score", 0)
                    if score < min_score:
                        continue

                    created_utc = data.get("created_utc", 0)
                    published = datetime.fromtimestamp(created_utc, tz=timezone.utc)

                    # Use external URL if it's a link post, otherwise reddit permalink
                    url = data.get("url", "")
                    if not url or "reddit.com" in url:
                        url = f"https://www.reddit.com{data.get('permalink', '')}"

                    items.append(NewsItem(
                        title=data.get("title", ""),
                        url=url,
                        source=f"Reddit r/{sub}",
                        summary=data.get("selftext", "")[:200],
                        score=score,
                        published=published,
                        tags=["reddit", sub.lower()],
                    ))
                    count += 1
                    if count >= top_n:
                        break

            except Exception as e:
                logger.warning(f"Failed to fetch Reddit r/{sub}: {e}")

    logger.info(f"Reddit: fetched {len(items)} posts")
    return items
