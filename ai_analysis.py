"""
AI 智能解读模块
将技术指标快照交给 LLM 翻译为自然语言分析
"""
import json
import os
import re


def build_indicator_snapshot(data, signals, symbol, stock_name):
    """从当前数据中提取结构化指标快照"""
    latest = data.iloc[-1]

    # 技术指标数值（所有值保留 2 位小数，与同花顺一致）
    indicators = {
        "MACD": {
            "DIF": round(float(latest['macd']), 2),
            "DEA": round(float(latest['macd_signal']), 2),
            "MACD柱": round(float(latest['macd_hist']), 2),
        },
        "RSI": {
            "RSI_6": round(float(latest['rsi_6']), 2),
            "RSI_12": round(float(latest['rsi_12']), 2),
            "RSI_24": round(float(latest['rsi_24']), 2),
        },
        "KDJ": {
            "K": round(float(latest['kdj_k']), 2),
            "D": round(float(latest['kdj_d']), 2),
            "J": round(float(latest['kdj_j']), 2),
        },
        "布林带": {
            "上轨": round(float(latest['boll_upper']), 2),
            "中轨": round(float(latest['boll_mid']), 2),
            "下轨": round(float(latest['boll_lower']), 2),
            "带宽": f"{latest['boll_width']*100:.2f}%",
        },
    }

    # 均线（如果存在）
    for period in [5, 10, 20, 60]:
        col = f'ma{period}'
        if col in latest.index:
            indicators[f'MA{period}'] = round(float(latest[col]), 2)

    # 最新价
    price = round(float(latest['close']), 2)

    # 信号
    snapshot = {
        "股票": f"{stock_name} ({symbol})",
        "最新价": price,
        "技术指标": indicators,
        "交易信号": {
            "MACD": signals.get('macd', ''),
            "RSI": signals.get('rsi', ''),
            "KDJ": signals.get('kdj', ''),
            "布林带": signals.get('boll', ''),
            "综合建议": signals.get('recommendation', ''),
        },
    }

    return snapshot


def call_ai_analysis(snapshot, model, api_key, base_url, temperature=0.2):
    """调用 LLM 分析指标快照，返回解析后的 dict"""
    import litellm

    if base_url:
        os.environ["OPENAI_API_BASE"] = base_url

    prompt = _build_prompt(snapshot)
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, indent=2)

    response = litellm.completion(
        model=model,
        api_key=api_key,
        messages=[
            {
                "role": "system",
                "content": prompt,
            },
            {
                "role": "user",
                "content": f"以下是股票技术指标数据，请分析：\n\n```json\n{snapshot_json}\n```",
            },
        ],
        temperature=temperature,
        max_tokens=1024,
    )

    raw = response.choices[0].message.content

    # 尝试从回复中提取 JSON
    result = _parse_response(raw)
    return result


def _build_prompt(snapshot):
    """构建 system prompt"""
    return """你是一个专业的股票技术分析助手。你的任务是基于提供给你的技术指标数据，做出简明、准确的分析。

规则：
1. 只能引用提供给你的数据，绝对禁止编造任何数值、信号或结论。
2. 分析要简洁，每个要点不超过 30 字。
3. 关键点位必须引用具体的指标数值。
4. 如果多个指标给出矛盾的信号（如 MACD 多头但 KDJ 超买），必须在风险提示中指出来。
5. 操作参考不得包含具体的买卖价格，只能用"支撑位附近"、"压力位附近"等区间描述。
6. 始终用中文回复。

回复格式（必须是严格的 JSON，不要包含任何其他文字）：

```json
{
  "核心结论": "一句话概括当前技术面状况，不超过 50 字",
  "风险提示": ["风险1描述", "风险2描述"],
  "关键点位": {
    "支撑": "数值",
    "压力": "数值"
  },
  "操作参考": "基于指标的操作参考，不超过 50 字"
}
```

如果某个指标的数据不足或异常，在对应字段中如实说明，不要猜测。"""


def _parse_response(raw):
    """从 LLM 回复中提取 JSON"""
    # 尝试匹配 ```json ... ``` 代码块
    m = re.search(r'```json\s*([\s\S]*?)\s*```', raw)
    if m:
        raw = m.group(1)

    # 尝试匹配第一个 { ... } 对象
    m = re.search(r'\{[\s\S]*\}', raw)
    if m:
        raw = m.group(0)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "核心结论": "AI 返回格式异常，请重试",
            "风险提示": [],
            "关键点位": {},
            "操作参考": "",
        }

    # 验证必填字段
    for key in ["核心结论", "风险提示", "关键点位", "操作参考"]:
        if key not in result:
            result[key] = "" if key == "核心结论" or key == "操作参考" else ([] if key == "风险提示" else {})

    return result
