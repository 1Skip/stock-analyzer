"""
通知推送模块
支持企业微信 / 飞书 两个渠道
"""
import logging
import requests
from datetime import datetime
from typing import Optional

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

    resp = requests.post(
        FEISHU_WEBHOOK_URL,
        json={
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": "blue",
                },
                "elements": [{"tag": "markdown", "content": body}],
            },
        },
        timeout=10,
    )
    ok = resp.status_code == 200 and resp.json().get("code") == 0
    if not ok:
        logger.warning(f"飞书推送失败: {resp.text}")
    return ok


def build_analysis_report(symbol: str, name: str, price: float,
                           change_pct: float, signals: dict,
                           ai_summary: str = "") -> tuple[str, str]:
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
    if ai_summary:
        body += f"\nAI解读:\n{ai_summary}"

    return title, body
