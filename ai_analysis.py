"""
AI 智能解读模块
将技术指标快照交给 LLM 翻译为自然语言分析
"""
import json
import os
import re
from dataclasses import dataclass


@dataclass
class AgentConfig:
    """单个 Agent 的配置"""
    name: str
    model: str = ""
    temperature: float = 0.2
    max_tokens: int = 512
    timeout: int = 30


def normalize_llm_model(model, base_url=""):
    """补齐 LiteLLM 需要的 provider 前缀，兼容旧的 DeepSeek 本地配置。"""
    model_name = (model or "").strip()
    if not model_name:
        return model_name
    if "/" in model_name:
        return model_name

    base = (base_url or "").lower()
    if model_name.startswith("deepseek-") or "deepseek.com" in base:
        return f"deepseek/{model_name}"

    return model_name


def resolve_llm_max_tokens(model, max_tokens):
    """推理模型会先消耗 reasoning token，给它保留足够正文输出空间。"""
    model_name = (model or "").lower()
    if any(name in model_name for name in ("deepseek-v4-pro", "deepseek-reasoner")):
        return max(int(max_tokens or 0), 2048)
    return max_tokens


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
        },
    }

    return snapshot


def call_ai_analysis(snapshot, model, api_key, base_url, temperature=0.2):
    """调用 LLM 分析指标快照，返回解析后的 dict"""
    import litellm

    prompt = _build_prompt(snapshot)
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, indent=2)
    normalized_model = normalize_llm_model(model, base_url)

    completion_kwargs = dict(
        model=normalized_model,
        api_key=api_key,
    )
    if base_url:
        completion_kwargs['api_base'] = base_url

    response = litellm.completion(
        **completion_kwargs,
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
        max_tokens=resolve_llm_max_tokens(normalized_model, 1024),
        timeout=30,
    )

    raw = response.choices[0].message.content

    # 尝试从回复中提取 JSON
    result = _parse_response(raw)
    return result


def _build_prompt(snapshot):
    """构建 system prompt"""
    return """你是一个专业的股票技术分析助手。你的任务是基于提供给你的技术指标数据，做出简明、准确的分析。

规则：
1. 只能引用提供给你的指标数值，绝对禁止编造任何数值或结论。
2. 根据指标数据独立分析，不要引用或重复"交易信号"中的系统判断文字。
3. 绝对不要输出"综合建议"四个字，也不要在回复内容中使用任何 Markdown 标题（# ## ### 等）。
4. 分析要简洁，每个要点不超过 30 字。
5. 关键点位必须引用具体的指标数值。
6. 如果多个指标给出矛盾的信号（如 MACD 多头但 KDJ 超买），必须在风险提示中指出来。
7. 操作参考不得包含具体的买卖价格，只能用"支撑位附近"、"压力位附近"等区间描述。
8. 始终用中文回复。

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


# ============================================================
# 多Agent协作分析
# ============================================================

_TECHNICAL_PROMPT = """你是一个技术指标分析专家。你只负责解读技术指标的数值含义，不做任何买卖建议。

规则：
1. 只能引用提供给你的指标数值，绝对禁止编造
2. 对于每个指标，简要说明当前数值的含义
3. 如果多个指标指向同一方向，指出这种一致性
4. 不要提"综合建议"或任何买卖结论
5. 始终用中文回复

回复格式（严格 JSON）：
```json
{
  "MACD解读": "基于DIF/DEA/柱状图的简要分析，不超过40字",
  "RSI解读": "基于三周期RSI的简要分析，不超过40字",
  "KDJ解读": "基于K/D/J值的简要分析，不超过40字",
  "布林带解读": "基于价格在布林带中位置的简要分析，不超过40字",
  "均线解读": "基于价格与均线关系的简要分析，不超过40字",
  "指标一致性": "指标指向是否一致的分析，不超过40字"
}
```"""

_RISK_PROMPT = """你是一个风险评估专家。你只负责识别风险因素，不做任何买卖建议。

规则：
1. 只能基于提供给你的指标数值识别风险
2. 关注：超买超卖、背离、波动率、多空矛盾信号
3. 每条风险描述不超过 30 字，最多 4 条
4. 如果没有明显风险，写"无明显风险信号"
5. 始终用中文回复

回复格式（严格 JSON）：
```json
{
  "风险等级": "低/中/高",
  "风险因素": ["风险1", "风险2"],
  "矛盾信号": "如MACD多头但RSI超买等矛盾，不超过50字",
  "关注点位": {
    "下方": "关键支撑位描述",
    "上方": "关键压力位描述"
  }
}
```"""

_DECISION_PROMPT = """你是一个投资决策顾问。你将收到技术解读和风险评估两份报告，综合给出最终判断。

规则：
1. 必须同时引用技术解读和风险评估的内容
2. 如果技术和风险矛盾，必须在结论中体现
3. 操作参考只能是区间描述，不能给具体买卖价格
4. 始终用中文回复

回复格式（严格 JSON）：
```json
{
  "核心结论": "综合技术和风险后的一句话结论，不超过50字",
  "技术面评分": "偏多/偏空/中性",
  "信心度": "高/中/低",
  "操作参考": "不超过50字",
  "关注要点": ["要点1", "要点2", "要点3"]
}
```"""


_BULL_PROMPT = """你是A股多头研究员。你只基于输入中的公开数据、技术信号、资金情绪、基本面、题材与风险事件，提炼支持关注该股票的理由。
要求：
1. 不编造任何输入中没有的数据。
2. 必须说明触发多头观点的证据来源，例如技术、资金、基本面、题材或催化因素。
3. 不给具体买入价格，只给观察条件。
4. 始终用中文回复。
回复格式必须是严格 JSON：
```json
{
  "立场": "看多/谨慎看多/中性",
  "核心论点": "一句话，不超过50字",
  "证据": ["证据1", "证据2", "证据3"],
  "触发条件": ["条件1", "条件2"]
}
```"""


_BEAR_PROMPT = """你是A股空头研究员。你只基于输入中的公开数据、技术信号、资金情绪、基本面、题材与风险事件，提炼需要回避或降仓的风险。
要求：
1. 不编造任何输入中没有的数据。
2. 必须指出风险来自技术、资金、估值、公告、解禁、龙虎榜或题材退潮中的哪一类。
3. 不给具体卖出价格，只给风险条件。
4. 始终用中文回复。
回复格式必须是严格 JSON：
```json
{
  "立场": "看空/谨慎看空/中性",
  "核心论点": "一句话，不超过50字",
  "风险": ["风险1", "风险2", "风险3"],
  "失效条件": ["条件1", "条件2"]
}
```"""


_RISK_MANAGER_PROMPT = """你是A股风控经理。你将收到系统化决策结果、多头观点和空头观点，请给出最终风控裁决。
要求：
1. 先尊重系统化决策分数、仓位、风险等级和执行风控 Agent。
2. 如果存在 hard_block 或仓位上限，不能给出高于执行风控 Agent 的建议仓位。
3. 如果多空观点冲突，优先控制回撤和仓位。
4. 输出要能直接放进每日分析报告。
5. 始终用中文回复。
回复格式必须是严格 JSON：
```json
{
  "最终裁决": "积极关注/轻仓试探/等待确认/回避降仓",
  "建议仓位": "0-1成/观察仓/1-2成/2-3成",
  "核心理由": "一句话，不超过60字",
  "买点条件": ["条件1", "条件2"],
  "风险红线": ["红线1", "红线2"],
  "置信度": "高/中/低"
}
```"""


def _call_agent(system_prompt, snapshot, config, api_key, base_url):
    """调用单个 Agent，返回 dict 结果"""
    import litellm

    snapshot_json = json.dumps(snapshot, ensure_ascii=False, indent=2)
    normalized_model = normalize_llm_model(config.model, base_url)

    completion_kwargs = dict(
        model=normalized_model,
        api_key=api_key,
    )
    if base_url:
        completion_kwargs['api_base'] = base_url

    try:
        response = litellm.completion(
            **completion_kwargs,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请分析以下数据：\n\n```json\n{snapshot_json}\n```"},
            ],
            temperature=config.temperature,
            max_tokens=resolve_llm_max_tokens(normalized_model, config.max_tokens),
            timeout=config.timeout,
        )
        raw = response.choices[0].message.content
        structured = _parse_response(raw)
        return {
            "agent": config.name,
            "content": raw,
            "success": True,
            "structured": structured,
            "error": "",
        }
    except Exception as e:
        return {
            "agent": config.name,
            "content": "",
            "success": False,
            "structured": {},
            "error": str(e),
        }


def run_multi_agent_analysis(snapshot, model, api_key, base_url=""):
    """多Agent协作分析：技术Agent + 风险Agent → 决策Agent

    Args:
        snapshot: build_indicator_snapshot() 的输出
        model: LLM 模型标识
        api_key: API key
        base_url: 自定义 API 地址

    Returns:
        {
            "technical": dict (agent/structured/success/error),
            "risk": dict,
            "decision": dict,
            "mode": "multi_agent",
        }
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    tech_config = AgentConfig(name="技术分析", model=model, max_tokens=512)
    risk_config = AgentConfig(name="风险评估", model=model, max_tokens=512)
    decision_config = AgentConfig(name="决策综合", model=model, max_tokens=512)

    # Phase 1: 并行执行技术分析和风险评估
    tech_result = None
    risk_result = None

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(_call_agent, _TECHNICAL_PROMPT, snapshot, tech_config, api_key, base_url): "technical",
            executor.submit(_call_agent, _RISK_PROMPT, snapshot, risk_config, api_key, base_url): "risk",
        }
        for future in as_completed(futures):
            name = futures[future]
            if name == "technical":
                tech_result = future.result()
            else:
                risk_result = future.result()

    # Phase 2: 综合决策
    context = {
        "原始数据": snapshot,
        "技术分析结果": tech_result.get("structured", {}) if tech_result else {},
        "风险分析结果": risk_result.get("structured", {}) if risk_result else {},
    }
    decision_result = _call_agent(
        _DECISION_PROMPT, context, decision_config, api_key, base_url,
    )

    return {
        "technical": tech_result or {"agent": "技术分析", "success": False, "error": "未执行"},
        "risk": risk_result or {"agent": "风险评估", "success": False, "error": "未执行"},
        "decision": decision_result,
        "mode": "multi_agent",
    }


def build_debate_snapshot(
    committee_decision: dict,
    *,
    stock: dict | None = None,
    extended_info: dict | None = None,
) -> dict:
    """构建给 LLM 多空辩论使用的精简 A股决策快照。"""
    stock = stock or {}
    extended_info = extended_info or {}
    return {
        "股票": {
            "代码": committee_decision.get("symbol") or stock.get("symbol"),
            "名称": committee_decision.get("name") or stock.get("name"),
            "现价": stock.get("price"),
            "涨跌幅": stock.get("change_pct"),
        },
        "系统化决策": {
            "评分": committee_decision.get("score"),
            "行动": committee_decision.get("action"),
            "仓位": committee_decision.get("position"),
            "风险等级": committee_decision.get("risk_level"),
            "置信度": committee_decision.get("confidence"),
            "买卖点": committee_decision.get("entry_hint"),
            "关键价位": committee_decision.get("key_levels"),
            "执行风控": committee_decision.get("risk_control"),
            "看多依据": committee_decision.get("bullish_points"),
            "看空风险": committee_decision.get("bearish_points"),
            "风险警报": committee_decision.get("risk_alerts"),
            "催化因素": committee_decision.get("catalysts"),
        },
        "六Agent": [
            {
                "名称": agent.get("name"),
                "立场": agent.get("stance"),
                "加减分": agent.get("score_delta"),
                "权重": agent.get("weight"),
                "置信度": agent.get("confidence"),
                "证据": agent.get("evidence"),
                "警报": agent.get("warnings"),
            }
            for agent in committee_decision.get("agents", [])
        ],
        "扩展信息": {
            "资金流": extended_info.get("fund_flow"),
            "研报": extended_info.get("research"),
            "风险事件": extended_info.get("risk_events"),
            "板块归因": extended_info.get("sector_attribution") or extended_info.get("attribution"),
        },
    }


def run_debate_analysis(
    committee_decision: dict,
    *,
    stock: dict | None = None,
    extended_info: dict | None = None,
    model: str = "",
    api_key: str | None = None,
    base_url: str | None = "",
) -> dict:
    """A股多空辩论：多头研究员 + 空头研究员 → 风控经理裁决。"""
    if not api_key:
        return {
            "mode": "a_share_debate",
            "enabled": False,
            "error": "未配置 AI_API_KEY",
            "bull": {},
            "bear": {},
            "risk_manager": {},
        }

    from concurrent.futures import ThreadPoolExecutor, as_completed

    snapshot = build_debate_snapshot(committee_decision, stock=stock, extended_info=extended_info)
    bull_config = AgentConfig(name="多头研究员", model=model, max_tokens=512)
    bear_config = AgentConfig(name="空头研究员", model=model, max_tokens=512)
    risk_config = AgentConfig(name="风控经理", model=model, max_tokens=512)

    bull_result = None
    bear_result = None
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(_call_agent, _BULL_PROMPT, snapshot, bull_config, api_key, base_url): "bull",
            executor.submit(_call_agent, _BEAR_PROMPT, snapshot, bear_config, api_key, base_url): "bear",
        }
        for future in as_completed(futures):
            if futures[future] == "bull":
                bull_result = future.result()
            else:
                bear_result = future.result()

    context = {
        "原始快照": snapshot,
        "多头观点": bull_result.get("structured", {}) if bull_result else {},
        "空头观点": bear_result.get("structured", {}) if bear_result else {},
    }
    manager_result = _call_agent(_RISK_MANAGER_PROMPT, context, risk_config, api_key, base_url)

    return {
        "mode": "a_share_debate",
        "enabled": True,
        "error": "",
        "bull": bull_result or {"agent": "多头研究员", "success": False, "error": "未执行", "structured": {}},
        "bear": bear_result or {"agent": "空头研究员", "success": False, "error": "未执行", "structured": {}},
        "risk_manager": manager_result,
    }
