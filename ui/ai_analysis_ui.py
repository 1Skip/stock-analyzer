"""AI 分析 UI 组件 — API 配置表单 + 分析结果渲染"""
import re
import streamlit as st
from config import AI_MODEL, AI_API_KEY, AI_BASE_URL, AI_TEMPERATURE
from ai_analysis import build_indicator_snapshot, call_ai_analysis, run_multi_agent_analysis
from ui.loading import status_loading


AI_MODEL_OPTIONS = {
    # 国内模型
    "deepseek/deepseek-chat": "DeepSeek V3",
    "deepseek/deepseek-reasoner": "DeepSeek R1",
    "deepseek/deepseek-v4-pro": "DeepSeek V4 Pro",
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

    if cache_key not in st.session_state:
        st.session_state[cache_key] = None
    if multi_cache_key not in st.session_state:
        st.session_state[multi_cache_key] = None

    st.caption("主结论以 A股决策委员会 为准；AI 仅用于解释技术指标、补充风险和梳理语言，不作为独立买卖建议。")

    use_multi = st.checkbox("启用补充协作模式（技术+风险+决策三Agent解释）",
                            key=f"ai_multi_{symbol}_{period}")

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        if st.button("生成辅助解读", type="primary", key=f"ai_btn_{symbol}_{period}"):
            error_msg = None
            try:
                snapshot = build_indicator_snapshot(data, signals, symbol, stock_name)
                if use_multi:
                    with status_loading("\u591aAgent\u534f\u4f5c\u5206\u6790\u4e2d\uff08\u6280\u672f\u5206\u6790+\u98ce\u9669\u8bc4\u4f30+\u7efc\u5408\u51b3\u7b56\uff09...", 25):
                        result = run_multi_agent_analysis(
                            snapshot, model, api_key, AI_BASE_URL
                        )
                    st.session_state[multi_cache_key] = result
                    st.session_state[cache_key] = None
                else:
                    with status_loading("AI \u6b63\u5728\u5206\u6790\u6280\u672f\u6307\u6807...", 25):
                        result = call_ai_analysis(
                            snapshot, model, api_key, AI_BASE_URL, AI_TEMPERATURE
                        )
                    st.session_state[cache_key] = result
                    st.session_state[multi_cache_key] = None
            except Exception as e:
                st.session_state[cache_key] = None
                st.session_state[multi_cache_key] = None
                error_msg = str(e)
            if error_msg:
                st.error(f"分析失败：{error_msg}")
    with col_info:
        model_label = AI_MODEL_OPTIONS.get(model, model)
        st.caption(f"当前模型: {model_label}")

    # 单Agent 结果渲染
    result = st.session_state[cache_key]
    if result:
        def _clean(text):
            if not isinstance(text, str):
                return text
            return re.sub(r'^#{1,3}\s*', '', text, flags=re.MULTILINE)

        st.markdown("#### 核心结论")
        st.markdown(_clean(result.get("核心结论", "无")))

        risks = result.get("风险提示", [])
        if risks:
            st.markdown("#### 风险提示")
            for r in risks:
                st.markdown(f"- {_clean(r)}")

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
            st.markdown(_clean(suggestion))

        st.caption(f"模型: {model_label} | AI 辅助解读，仅作解释补充，不构成投资建议")

    # 多Agent 结果渲染
    multi_result = st.session_state[multi_cache_key]
    if multi_result:
        tech = multi_result.get("technical", {})
        risk = multi_result.get("risk", {})
        decision = multi_result.get("decision", {})

        dec_struct = decision.get("structured", {})
        if dec_struct:
            conclusion = dec_struct.get("核心结论", "")
            score = dec_struct.get("技术面评分", "")
            confidence = dec_struct.get("信心度", "")
            if conclusion:
                st.markdown("#### 核心结论")
                score_badge = {"偏多": "🟢", "偏空": "🔴", "中性": "🟡"}.get(score, "")
                conf_badge = {"高": "高", "中": "中", "低": "低"}.get(confidence, confidence)
                st.markdown(f"{score_badge} {conclusion}（信心度: {conf_badge}）")

        tech_struct = tech.get("structured", {})
        if tech_struct:
            with st.expander("技术指标解读", expanded=False):
                for key, label in [("MACD解读", "MACD"), ("RSI解读", "RSI"),
                                   ("KDJ解读", "KDJ"), ("布林带解读", "布林带"),
                                   ("均线解读", "均线"), ("指标一致性", "一致性")]:
                    val = tech_struct.get(key, "")
                    if val:
                        st.markdown(f"- **{label}**: {val}")

        risk_struct = risk.get("structured", {})
        if risk_struct:
            with st.expander("风险评估", expanded=False):
                risk_level = risk_struct.get("风险等级", "")
                if risk_level:
                    level_emoji = {"低": "🟢", "中": "🟡", "高": "🔴"}.get(risk_level, "")
                    st.markdown(f"**风险等级**: {level_emoji} {risk_level}")

                factors = risk_struct.get("风险因素", [])
                if factors:
                    for f in factors:
                        st.markdown(f"- {f}")

                conflict = risk_struct.get("矛盾信号", "")
                if conflict:
                    st.markdown(f"**矛盾信号**: {conflict}")

                levels = risk_struct.get("关注点位", {})
                if levels:
                    cols = st.columns(len(levels))
                    for i, (name, value) in enumerate(levels.items()):
                        with cols[i]:
                            st.metric(name, value)

        if dec_struct:
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
    model = st.session_state.get("ai_model") or AI_MODEL

    if not key:
        with st.expander("设置 API Key 后启用 AI 辅助解读", expanded=False):
            _show_setup_form()
        return

    with st.expander("展开 AI 辅助解读", expanded=False):
        _show_analysis_ui(data, signals, symbol, stock_name, period, key, model)

    if st.checkbox("更换 AI 配置", key=f"ai_change_cfg_{symbol}_{period}"):
        _show_setup_form(symbol, period)
