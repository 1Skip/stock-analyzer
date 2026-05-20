"""AI 分析 UI 组件 — API 配置表单 + 分析结果渲染"""
import re
import streamlit as st
from config import AI_MODEL, AI_API_KEY, AI_BASE_URL, AI_TEMPERATURE
from ai_analysis import (
    build_indicator_snapshot,
    call_ai_analysis,
    normalize_llm_model,
    run_multi_agent_analysis,
)
from ui.loading import render_status_loading


AI_MODEL_OPTIONS = {
    # 国内模型
    "deepseek/deepseek-v4-pro": "DeepSeek V4 Pro",
    "deepseek/deepseek-reasoner": "DeepSeek R1",
    "zhipuai/glm-4-flash": "智谱 GLM-4 Flash（免费）",
    "zhipuai/glm-4": "智谱 GLM-4",
    "moonshot/moonshot-v1-8k": "Kimi (Moonshot)",
    "moonshot/moonshot-v1-32k": "Kimi 32K (Moonshot)",
    "dashscope/qwen-plus": "通义千问 Qwen-Plus",
    "dashscope/qwen-max": "通义千问 Qwen-Max",
    "baichuan/baichuan2-turbo": "百川 Baichuan2-Turbo",
    "baichuan/baichuan3-turbo": "百川 Baichuan3-Turbo",
    # 国际模型
    "gemini/gemini-2.5-flash": "Gemini 2.5 Flash（免费）",
    "gemini/gemini-2.5-pro": "Gemini 2.5 Pro",
    "openai/gpt-4o": "GPT-4o",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "claude-opus-4-7": "Claude Opus 4.7",
}


def _detect_provider(api_key):
    """根据 API Key 前缀自动检测厂商"""
    if not api_key:
        return None
    key = api_key.strip()
    if key.startswith("AIza"):
        return ("gemini", "gemini/gemini-2.5-flash")
    if key.startswith("sk-ant"):
        return ("claude", "claude-sonnet-4-6")
    if key.startswith("sk-or-"):
        return ("openrouter", AI_MODEL)
    if key.startswith("sk-proj-") or key.startswith("sk-svcacct-"):
        return ("openai", "openai/gpt-4o")
    if key.startswith("sk-"):
        return ("deepseek", AI_MODEL)
    if "." in key and len(key) > 30 and not key.startswith("sk-"):
        return ("zhipuai", "zhipuai/glm-4-flash")
    return None


def _resolve_setup_model(api_key):
    """返回设置页应使用的模型与识别说明。"""
    detected = _detect_provider(api_key)
    if detected:
        provider_name, model_key = detected
        return provider_name, model_key, False

    model_key = st.session_state.get("ai_model") or AI_MODEL
    return "默认配置", model_key, True


def _clean_ai_text(text):
    """清理模型返回中的 Markdown 标题前缀。"""
    if not isinstance(text, str):
        return text
    return re.sub(r'^#{1,3}\s*', '', text, flags=re.MULTILINE).strip()


def _has_meaningful_content(value):
    """判断模型返回值是否包含可展示内容。"""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_meaningful_content(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_meaningful_content(item) for item in value)
    return value is not None


def _agent_has_displayable_content(agent_result):
    """判断单个 Agent 是否有结构化内容、原文或错误信息可展示。"""
    if not agent_result:
        return False
    return (
        _has_meaningful_content(agent_result.get("structured", {}))
        or _has_meaningful_content(agent_result.get("content", ""))
        or _has_meaningful_content(agent_result.get("error", ""))
    )


def _render_agent_fallback(agent_result, label):
    """在结构化字段为空时展示原始内容或失败原因，避免空白面板。"""
    content = agent_result.get("content", "") if agent_result else ""
    error = agent_result.get("error", "") if agent_result else ""
    if _has_meaningful_content(content):
        st.markdown(_clean_ai_text(content))
    elif _has_meaningful_content(error):
        st.caption(f"{label}未生成：{error}")
    else:
        st.caption(f"{label}暂无可展示内容：模型返回了空字段，请重试或更换模型。")


def _show_setup_form(symbol="", period=""):
    """显示 API Key 配置表单，并根据 Key 自动匹配模型。"""
    st.markdown("#### 设置 API Key")
    api_key = st.text_input("API Key", type="password", key="ai_setup_key",
                            placeholder="输入你的 API Key")

    provider_name, model, is_default = _resolve_setup_model(api_key)
    model_label = AI_MODEL_OPTIONS.get(model, model)
    if api_key.strip():
        if is_default:
            st.caption(f"当前模型：{model_label}（未识别到明确厂商，使用项目默认配置）")
        else:
            st.caption(f"已识别：{provider_name.upper()} · {model_label}")

    with st.form(key="ai_setup_form"):
        if st.form_submit_button("保存配置", type="primary"):
            if not api_key.strip():
                st.error("API Key 不能为空")
            else:
                st.session_state.ai_api_key = api_key.strip()
                st.session_state.ai_model = model
                if symbol:
                    st.session_state[f"ai_change_cfg_{symbol}_{period}"] = False
                st.rerun()
    st.caption("获取 API Key: [Google AI Studio](https://aistudio.google.com/app/apikey)")


def _show_analysis_ui(data, signals, symbol, stock_name, period, api_key, model):
    """显示 AI 辅助解读按钮和结果。"""
    cache_key = f"ai_result_{symbol}_{period}"
    multi_cache_key = f"ai_multi_result_{symbol}_{period}"
    running_key = f"ai_running_{symbol}_{period}"
    error_key = f"ai_error_{symbol}_{period}"

    if cache_key not in st.session_state:
        st.session_state[cache_key] = None
    if multi_cache_key not in st.session_state:
        st.session_state[multi_cache_key] = None
    if running_key not in st.session_state:
        st.session_state[running_key] = False
    if error_key not in st.session_state:
        st.session_state[error_key] = None

    st.caption("主结论以 A股决策委员会 为准；AI 仅用于解释技术指标、补充风险和梳理语言，不作为独立买卖建议。")

    use_multi = st.checkbox(
        "启用补充协作模式（技术+风险+决策三Agent解释）",
        key=f"ai_multi_{symbol}_{period}",
        disabled=st.session_state[running_key],
    )

    result_container = st.empty()
    progress_container = st.empty()

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        clicked = st.button(
            "生成辅助解读" if not st.session_state[running_key] else "生成中...",
            type="primary",
            key=f"ai_btn_{symbol}_{period}",
            disabled=st.session_state[running_key],
        )
    with col_info:
        model_label = AI_MODEL_OPTIONS.get(model, model)
        st.caption(f"当前模型: {model_label}")

    if clicked:
        st.session_state[running_key] = True
        st.session_state[cache_key] = None
        st.session_state[multi_cache_key] = None
        st.session_state[error_key] = None
        result_container.empty()
        progress_container.empty()
        try:
            snapshot = build_indicator_snapshot(data, signals, symbol, stock_name)
            if use_multi:
                render_status_loading(progress_container, "多Agent协作分析中（技术分析+风险评估+综合决策）...", 25)
                result = run_multi_agent_analysis(snapshot, model, api_key, AI_BASE_URL)
                st.session_state[multi_cache_key] = result
            else:
                render_status_loading(progress_container, "AI 正在分析技术指标...", 25)
                result = call_ai_analysis(snapshot, model, api_key, AI_BASE_URL, AI_TEMPERATURE)
                st.session_state[cache_key] = result
        except Exception as e:
            st.session_state[error_key] = str(e)
        finally:
            progress_container.empty()
            st.session_state[running_key] = False
            st.rerun()

    if st.session_state[running_key]:
        render_status_loading(progress_container, "AI 辅助解读生成中...", 25)
        return
    if st.session_state[error_key]:
        st.error(f"分析失败：{st.session_state[error_key]}")

    with result_container.container():
        result = st.session_state[cache_key]
        if result:
            st.markdown("#### 核心结论")
            st.markdown(_clean_ai_text(result.get("核心结论", "无")))

            risks = result.get("风险提示", [])
            if risks:
                st.markdown("#### 风险提示")
                for r in risks:
                    st.markdown(f"- {_clean_ai_text(r)}")

            levels = result.get("关键点位", {})
            if levels:
                st.markdown("#### 关键点位")
                cols = st.columns(len(levels))
                for i, (name, value) in enumerate(levels.items()):
                    with cols[i]:
                        st.metric(name, value)

            suggestion = result.get("操作参考", "")
            if suggestion:
                st.markdown("#### 操作参考")
                st.markdown(_clean_ai_text(suggestion))

            st.caption(f"模型: {model_label} | AI 辅助解读，仅作解释补充，不构成投资建议")

        multi_result = st.session_state[multi_cache_key]
        if multi_result:
            tech = multi_result.get("technical", {})
            risk = multi_result.get("risk", {})
            decision = multi_result.get("decision", {})

            dec_struct = decision.get("structured", {})
            if _has_meaningful_content(dec_struct):
                conclusion = dec_struct.get("核心结论", "")
                score = dec_struct.get("技术面评分", "")
                confidence = dec_struct.get("信心度", "")
                if conclusion:
                    st.markdown("#### 核心结论")
                    score_badge = {"偏多": "看多", "偏空": "看空", "中性": "中性"}.get(score, "")
                    conf_badge = {"高": "高", "中": "中", "低": "低"}.get(confidence, confidence)
                    st.markdown(f"{score_badge} {conclusion}（信心度: {conf_badge}）")
            elif _agent_has_displayable_content(decision):
                st.markdown("#### 核心结论")
                _render_agent_fallback(decision, "综合决策")

            tech_struct = tech.get("structured", {})
            tech_items = [("MACD解读", "MACD"), ("RSI解读", "RSI"),
                          ("KDJ解读", "KDJ"), ("布林带解读", "布林带"),
                          ("均线解读", "均线"), ("指标一致性", "一致性")]
            has_tech_fields = any(_has_meaningful_content(tech_struct.get(key, "")) for key, _ in tech_items)
            if has_tech_fields or _agent_has_displayable_content(tech):
                with st.expander("技术指标解读", expanded=False):
                    rendered = False
                    for key, label in tech_items:
                        val = tech_struct.get(key, "")
                        if _has_meaningful_content(val):
                            st.markdown(f"- **{label}**: {val}")
                            rendered = True
                    if not rendered:
                        _render_agent_fallback(tech, "技术指标解读")

            risk_struct = risk.get("structured", {})
            has_risk_fields = any(_has_meaningful_content(risk_struct.get(key, "")) for key in [
                "风险等级", "风险因素", "矛盾信号", "关注点位"
            ])
            if has_risk_fields or _agent_has_displayable_content(risk):
                with st.expander("风险评估", expanded=False):
                    rendered = False
                    risk_level = risk_struct.get("风险等级", "")
                    if _has_meaningful_content(risk_level):
                        level_text = {"低": "低", "中": "中", "高": "高"}.get(risk_level, risk_level)
                        st.markdown(f"**风险等级**: {level_text}")
                        rendered = True

                    factors = risk_struct.get("风险因素", [])
                    if _has_meaningful_content(factors):
                        for f in factors:
                            st.markdown(f"- {f}")
                        rendered = True

                    conflict = risk_struct.get("矛盾信号", "")
                    if _has_meaningful_content(conflict):
                        st.markdown(f"**矛盾信号**: {conflict}")
                        rendered = True

                    levels = risk_struct.get("关注点位", {})
                    if _has_meaningful_content(levels):
                        cols = st.columns(len(levels))
                        for i, (name, value) in enumerate(levels.items()):
                            with cols[i]:
                                st.metric(name, value)
                        rendered = True
                    if not rendered:
                        _render_agent_fallback(risk, "风险评估")

            if _has_meaningful_content(dec_struct):
                suggestion = dec_struct.get("操作参考", "")
                if suggestion:
                    st.markdown("#### 操作参考")
                    st.markdown(suggestion)

                points = dec_struct.get("关注要点", [])
                if points:
                    with st.expander("关注要点", expanded=False):
                        for p in points:
                            st.markdown(f"- {p}")

            st.caption(f"模型: {model_label} | 补充协作解读 | 不构成投资建议")


def display_ai_analysis_card(data, signals, symbol, stock_name, period):
    """AI 辅助解读 — 默认折叠的可选解释区。"""
    st.divider()
    st.subheader("AI 辅助解读（可选）")
    st.caption("默认不参与 A股决策委员会评分；需要自然语言解释时再展开使用。")

    key = st.session_state.get("ai_api_key") or AI_API_KEY
    model = normalize_llm_model(st.session_state.get("ai_model") or AI_MODEL, AI_BASE_URL)
    if st.session_state.get("ai_model") and st.session_state.ai_model != model:
        st.session_state.ai_model = model

    if not key:
        with st.expander("设置 API Key 后启用 AI 辅助解读", expanded=False):
            _show_setup_form()
        return

    with st.expander("展开 AI 辅助解读", expanded=False):
        _show_analysis_ui(data, signals, symbol, stock_name, period, key, model)

    if st.checkbox("更换 AI 配置", key=f"ai_change_cfg_{symbol}_{period}"):
        _show_setup_form(symbol, period)
