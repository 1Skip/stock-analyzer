"""
通知推送模块
支持企业微信 / 飞书 两个渠道
"""
import logging
import requests
from typing import Any, Optional

from config import (
    WECHAT_WEBHOOK_URL, FEISHU_WEBHOOK_URL, NOTIFY_CHANNELS,
)

logger = logging.getLogger(__name__)


def send_push(title: str, body: str, channels: Optional[list[str]] = None) -> dict[str, bool]:
    """发送推送通知到指定渠道

    Args:
        title: 标题
        body: 正文（支持 Markdown）
        channels: 渠道列表，默认使用 NOTIFY_CHANNELS 配置

    Returns:
        {channel: success} 字典
    """
    targets = channels or NOTIFY_CHANNELS
    results = {}

    for ch in targets:
        ch = ch.strip().lower()
        try:
            if ch == "wechat":
                results[ch] = _send_wechat(title, body)
            elif ch == "feishu":
                results[ch] = _send_feishu(title, body)
            else:
                logger.warning(f"未知通知渠道: {ch}")
                results[ch] = False
        except Exception as e:
            logger.error(f"{ch} 推送失败: {e}")
            results[ch] = False

    return results


def _send_wechat(title: str, body: str) -> bool:
    """企业微信机器人 Webhook"""
    if not WECHAT_WEBHOOK_URL:
        logger.warning("企业微信 webhook 未配置")
        return False

    content = f"## {title}\n{body}"
    resp = requests.post(
        WECHAT_WEBHOOK_URL,
        json={"msgtype": "markdown", "markdown": {"content": content}},
        timeout=10,
    )
    ok = resp.status_code == 200 and resp.json().get("errcode") == 0
    if not ok:
        logger.warning(f"企业微信推送失败: {resp.text}")
    return ok


def _send_feishu(title: str, body: str) -> bool:
    """飞书机器人 Webhook — 交互式卡片"""
    if not FEISHU_WEBHOOK_URL:
        logger.warning("飞书 webhook 未配置")
        return False
    elements = _build_feishu_markdown_elements(body)

    resp = requests.post(
        FEISHU_WEBHOOK_URL,
        json={
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": "blue",
                },
                "elements": elements,
            },
        },
        timeout=10,
    )
    ok = resp.status_code == 200 and resp.json().get("code") == 0
    if not ok:
        logger.warning(f"飞书推送失败: {resp.text}")
    return ok


def _build_feishu_markdown_elements(body: str, max_chars: int = 3500) -> list[dict]:
    """把长 Markdown 拆成多个飞书卡片元素，降低超长日报推送失败概率。"""
    text = str(body or "").strip()
    if not text:
        return [{"tag": "markdown", "content": "暂无内容"}]
    chunks = []
    current = ""
    for block in text.split("\n\n"):
        candidate = block if not current else f"{current}\n\n{block}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(block) <= max_chars:
            current = block
        else:
            chunks.extend(block[index:index + max_chars] for index in range(0, len(block), max_chars))
            current = ""
    if current:
        chunks.append(current)
    return [{"tag": "markdown", "content": chunk} for chunk in chunks]


def build_sector_report(sector_data: dict) -> tuple[str, str]:
    """构造板块推荐推送标题和正文

    Args:
        sector_data: get_all_sector_recommendations() 的返回值
            {板块名: {'短线': [...], '长线': [...]}}

    Returns:
        (title, body) 元组
    """
    SECTOR_ICONS = {
        "算力租赁": "💻",
        "电力": "⚡",
        "苹果概念": "🍎",
        "特斯拉概念": "🚗",
    }

    title = "📊 板块龙头推荐 — 短线/长线"

    body_lines = []
    for sector_name in ["算力租赁", "电力", "苹果概念", "特斯拉概念"]:
        data = sector_data.get(sector_name)
        if not data:
            continue

        icon = SECTOR_ICONS.get(sector_name, "📌")
        body_lines.append(f"## {icon} {sector_name}")

        # 短线
        short_stocks = data.get('短线', [])
        if short_stocks:
            body_lines.append("**短线**")
            for stock in short_stocks:
                body_lines.extend(_build_sector_stock_lines(stock))
        else:
            body_lines.append(f"**短线**: 暂无推荐")

        # 长线
        long_stocks = data.get('长线', [])
        if long_stocks:
            body_lines.append("**长线**")
            for stock in long_stocks:
                body_lines.extend(_build_sector_stock_lines(stock))
        else:
            body_lines.append(f"**长线**: 暂无推荐")

        body_lines.append("")

    body = "\n".join(body_lines).strip()
    return title, body


def _build_sector_stock_lines(stock: dict[str, Any]) -> list[str]:
    """Render a sector recommendation with the same decision cards used by watchlist push."""
    price = _number(stock.get("latest_price") or stock.get("price"))
    change_pct = _number(stock.get("change_pct")) or 0.0
    direction = "📈" if change_pct > 0 else "📉" if change_pct < 0 else "➡"
    name = stock.get("name") or stock.get("symbol", "--")
    symbol = stock.get("symbol", "--")
    strategy = stock.get("strategy", "")
    score = stock.get("score", "--")
    rating = stock.get("rating", "--")

    header = (
        f"- {name}({symbol}) "
        f"{price:.2f} {direction}{change_pct:+.2f}%"
        f"｜{strategy or '推荐'}｜评分 {score}｜{rating}"
    ) if price is not None else (
        f"- {name}({symbol}) {direction}{change_pct:+.2f}%"
        f"｜{strategy or '推荐'}｜评分 {score}｜{rating}"
    )
    lines = [header]

    try:
        from decision_committee import build_watchlist_decision
        from reports.decision_cards import build_decision_card_markdown

        item = {
            "symbol": symbol,
            "name": name,
            "price": price,
            "change_pct": change_pct,
            "signal_summary": stock.get("rating") or "观望",
            "rating": stock.get("rating") or "观望",
            "indicators": stock.get("indicators") or {},
        }
        decision = build_watchlist_decision(item)
        card_lines = build_decision_card_markdown(decision, compact=True)
        lines.extend(f"  {line}" for line in card_lines)
    except Exception as exc:
        logger.info("推荐股决策卡生成失败，保留基础推荐信息: %s", exc)

    return lines


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def build_analysis_report(symbol: str, name: str, price: float,
                           change_pct: float, signals: dict,
                           ai_summary: str = "",
                           decision: dict | None = None,
                           extended_info: dict | None = None) -> tuple[str, str]:
    """构造推送标题和正文"""
    direction = "📈" if change_pct > 0 else "📉" if change_pct < 0 else "➡"
    title = f"{name}({symbol}) {price:.2f} {direction}{change_pct:+.2f}%"

    signal_lines = []
    for indicator, signal in signals.items():
        emoji = {"偏多": "🟢", "偏空": "🔴", "观望": "⚪"}.get(signal, "")
        signal_lines.append(f"{indicator}: {emoji}{signal}")
    signal_text = " | ".join(signal_lines)

    body = f"价格: {price:.2f} ({change_pct:+.2f}%)\n"
    body += f"信号: {signal_text}\n"
    if decision:
        from reports.decision_cards import build_decision_card_markdown

        card_lines = build_decision_card_markdown(
            decision,
            extended_info=extended_info or {},
            profile=(extended_info or {}).get("profile") if isinstance(extended_info, dict) else None,
            compact=True,
        )
        if card_lines:
            body += "\n" + "\n".join(card_lines) + "\n"
    if ai_summary:
        body += f"\nAI解读:\n{ai_summary}"

    return title, body
