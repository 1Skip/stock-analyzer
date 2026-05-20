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


def build_t1_plan_report(plans: dict[str, Any]) -> tuple[str, str]:
    """Build a Feishu/WeChat report for cached T+1 plans generated after close."""
    title = "T+1 推荐计划"
    body_lines = []
    for strategy, plan in (plans or {}).items():
        if not isinstance(plan, dict):
            continue
        generated = plan.get("generated_at") or "--"
        plan_date = plan.get("plan_for_trade_date") or "--"
        sector = plan.get("sector") or "全部"
        recommended = plan.get("recommended") or []
        status = plan.get("status")
        body_lines.append(f"## {strategy}")
        body_lines.append(f"生成时间: {generated}｜板块: {sector}｜计划日: {plan_date}")
        if status in {"timeout", "failed"}:
            error = ((plan.get("data_status") or {}).get("error") or "生成失败") if isinstance(plan.get("data_status"), dict) else "生成失败"
            body_lines.append(f"状态: {status}｜{error}")
            body_lines.append("")
            continue
        if not recommended:
            body_lines.append("暂无推荐")
            body_lines.append("")
            continue
        for stock in recommended:
            body_lines.extend(_build_sector_stock_lines(stock))
        body_lines.append("")
    body = "\n".join(body_lines).strip()
    return title, body or "暂无 T+1 推荐计划"


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
    if stock.get("alpha_score") is not None:
        reasons = "；".join(str(item) for item in (stock.get("rank_reason") or [])[:2])
        penalties = "；".join(str(item) for item in (stock.get("rank_penalty") or [])[:1])
        alpha_line = f"  Alpha {stock.get('alpha_score')}/100（{stock.get('alpha_grade', '--')}）"
        if reasons:
            alpha_line += f": {reasons}"
        if penalties:
            alpha_line += f"；扣分 {penalties}"
        lines.append(alpha_line)
    lines.extend(_build_main_accumulation_push_lines(stock))
    lines.extend(_build_trade_plan_push_lines(stock))
    lines.extend(_build_explanation_push_lines(stock))
    checks = stock.get("strategy_checks") or {}
    details = stock.get("strategy_details") or {}
    if checks:
        passed = [name for name, ok in checks.items() if ok]
        missing = [name for name, ok in checks.items() if not ok]
        lines.append(f"  策略命中: {', '.join(passed) if passed else '暂无'}")
        if missing:
            lines.append(f"  缺失/未通过: {', '.join(missing)}")
    for key in ["买入观察", "卖出纪律", "市值过滤", "技术说明", "财务确认", "连涨3日", "主力净流入趋势", "15日涨停", "风险排除"]:
        if details.get(key):
            lines.append(f"  {key}: {details[key]}")

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


def _build_main_accumulation_push_lines(stock: dict[str, Any]) -> list[str]:
    indicators = stock.get("indicators") if isinstance(stock.get("indicators"), dict) else {}
    accumulation = _number(indicators.get("main_accumulation"))
    risk = _number(indicators.get("accumulation_risk"))
    trend = _number(indicators.get("accumulation_trend"))
    if accumulation is None and risk is None and trend is None:
        return []
    parts = []
    if accumulation is not None:
        parts.append(f"吸货 {accumulation:.2f}")
    if risk is not None:
        parts.append(f"风险 {risk:.2f}")
    if trend is not None:
        parts.append(f"涨跌 {trend:.2f}")
    return [f"  主力吸货: {'；'.join(parts)}（同花顺公式，真实日K推导）"]


def _build_trade_plan_push_lines(stock: dict[str, Any]) -> list[str]:
    plan = stock.get("trade_plan") if isinstance(stock.get("trade_plan"), dict) else {}
    if not plan:
        return []
    lines = [
        (
            "  买卖点: "
            f"观察区 {plan.get('buy_zone') or '--'}；"
            f"止损 {_format_plan_level(plan.get('stop_loss'))}；"
            f"第一压力 {_format_plan_level(plan.get('take_profit_1'))}；"
            f"仓位 {plan.get('position') or '--'}"
        )
    ]
    if plan.get("add_condition"):
        lines.append(f"  加仓确认: {plan['add_condition']}")
    invalid = plan.get("invalid_conditions") or []
    if invalid:
        lines.append(f"  失效条件: {'；'.join(str(item) for item in invalid[:2])}")
    return lines


def _format_plan_level(value: Any) -> str:
    try:
        if value is None or value == "":
            return "--"
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _build_explanation_push_lines(stock: dict[str, Any]) -> list[str]:
    explanation = stock.get("explanation") if isinstance(stock.get("explanation"), dict) else {}
    if not explanation:
        return []
    lines = []
    reasons = explanation.get("why_selected") or []
    risks = explanation.get("risk_flags") or []
    entry = explanation.get("entry_conditions") or []
    invalid = explanation.get("invalid_conditions") or []
    missing = explanation.get("missing_data") or []
    if reasons:
        lines.append(f"  入选依据: {'；'.join(str(item) for item in reasons[:2])}")
    if risks:
        lines.append(f"  风险/扣分: {'；'.join(str(item) for item in risks[:2])}")
    if entry:
        lines.append(f"  入场条件: {'；'.join(str(item) for item in entry[:2])}")
    if invalid:
        lines.append(f"  失效条件: {'；'.join(str(item) for item in invalid[:2])}")
    if missing:
        lines.append(f"  数据缺口: {'；'.join(str(item) for item in missing[:3])}")
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
                           extended_info: dict | None = None,
                           indicators: dict | None = None) -> tuple[str, str]:
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
    accumulation_lines = _build_main_accumulation_push_lines({"indicators": indicators or {}})
    if accumulation_lines:
        body += "\n" + "\n".join(line.strip() for line in accumulation_lines) + "\n"
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
