"""智能推荐页面 — 多策略智能选股推荐"""
import html
import streamlit as st
from recommendation_service import RecommendationService
from ui.loading import status_loading


def _format_progress_message(strategy, sector, stage, metrics):
    metrics = metrics or {}
    parts = [f"正在分析{sector}板块（{strategy}）", f"阶段：{stage}"]
    label_map = {
        "raw_pool": "股票池",
        "small_cap_pool": "市值通过",
        "realtime_quotes": "实时价量",
        "technical_passed": "技术突破",
        "light_passed": "轻筛通过",
        "shortlist": "深度候选",
        "deep_checked": "深度检查",
        "deep_total": "深度总数",
        "deep_done": "已深查",
        "result_count": "最终命中",
    }
    for key, label in label_map.items():
        if key in metrics:
            parts.append(f"{label} {metrics[key]}")
    return " ｜ ".join(parts)


def _make_progress_callback(progress_placeholder, strategy, sector):
    def update(stage, percent, metrics=None):
        percent = max(0, min(100, int(percent or 0)))
        message = _format_progress_message(strategy, sector, stage, metrics or {})
        progress_placeholder.markdown(
            f"""
            <div class="status-loading-strip">
              <div class="status-loading-main">
                <span class="status-loading-dot"></span>
                <div class="status-loading-copy">{html.escape(message)}</div>
                <span class="status-loading-percent">{percent}%</span>
              </div>
              <div class="status-loading-bar"><div style="width:{percent}%"></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    return update


def _run_recommendation_task(strategy, sector, num_stocks, progress_callback=None):
    """后台生成推荐列表。"""
    return RecommendationService().run(
        strategy,
        sector,
        num_stocks,
        progress_callback=progress_callback,
    )


def _render_multi_factor_diagnostics(diagnostics):
    if not diagnostics:
        return
    st.markdown("**筛选诊断**")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("扫描池", diagnostics.get("raw_pool", 0))
    col2.metric("市值通过", diagnostics.get("small_cap_pool", 0))
    col3.metric("轻筛通过", diagnostics.get("light_passed", 0))
    col4.metric("深度检查", diagnostics.get("deep_checked", 0))
    col5.metric("最终命中", diagnostics.get("result_count", 0))

    failures = {}
    for source_key in ("light_failures", "deep_failures"):
        for reason, count in (diagnostics.get(source_key) or {}).items():
            failures[reason] = failures.get(reason, 0) + count
    if failures:
        top_failures = sorted(failures.items(), key=lambda item: item[1], reverse=True)[:8]
        st.caption("主要卡点：" + "；".join(f"{html.escape(str(reason))} {count}只" for reason, count in top_failures))


def _render_aggressive_diagnostics(diagnostics):
    if not diagnostics:
        return
    st.markdown("**筛选诊断**")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("扫描池", diagnostics.get("raw_pool", 0))
    col2.metric("技术突破", diagnostics.get("technical_passed", 0))
    col3.metric("市值未过", diagnostics.get("market_cap_failed", 0))
    col4.metric("最终命中", diagnostics.get("result_count", 0))
    st.caption("激进突破型按全市场沪深主板 + 创业板扫描：先做量价突破，再对技术命中股检查市值 < 300 亿。")


_MULTI_FACTOR_REMOVED_CHECKS = {
    "个股资金流入",
    "消息/公告/研报催化",
    "近7日涨停活跃",
    "近7日涨停",
}

_MULTI_FACTOR_REMOVED_DETAILS = {
    "个股资金流",
    "消息催化",
    "催化依据",
    "偏利好催化",
    "风险催化",
    "近7日涨停",
}


def _filter_removed_multi_factor_fields(stock, strategy_name):
    if "多因子稳健型" not in str(strategy_name):
        return stock
    filtered = dict(stock or {})
    filtered["strategy_checks"] = {
        key: value
        for key, value in (filtered.get("strategy_checks") or {}).items()
        if key not in _MULTI_FACTOR_REMOVED_CHECKS
    }
    filtered["strategy_details"] = {
        key: value
        for key, value in (filtered.get("strategy_details") or {}).items()
        if key not in _MULTI_FACTOR_REMOVED_DETAILS
    }
    return filtered


def display_recommendation_list(recommended, strategy_name, diagnostics=None):
    """显示推荐列表"""
    if not recommended:
        st.warning(f"暂无{strategy_name}推荐股票")
        if "多因子稳健型" in strategy_name:
            _render_multi_factor_diagnostics(diagnostics or {})
            st.info("稳健型采用硬排除 + 评分制：先排除市值不符、短期过热和重大风险，再按技术、财务、连涨3日、主力净流入趋势、15日内涨停打分。上方诊断会显示具体卡点。")
        elif "激进突破型" in strategy_name:
            _render_aggressive_diagnostics(diagnostics or {})
            st.info("激进突破型采用全市场沪深主板 + 创业板扫描，若暂无结果，上方诊断会显示是技术突破不足还是市值过滤未通过。")
        else:
            st.info("可能原因：\n1. 数据获取失败（网络问题）\n2. 股票分析返回None（数据不足）\n3. 请检查日志输出")
        return

    st.success(f"{strategy_name}：为您推荐以下 {len(recommended)} 只股票")

    for i, stock in enumerate(recommended, 1):
        stock = _filter_removed_multi_factor_fields(stock, strategy_name)
        with st.container():
            change_pct = stock.get('change_pct', 0) or 0
            if change_pct > 0:
                arrow = "📈"
            elif change_pct < 0:
                arrow = "📉"
            else:
                arrow = "➡"
            st.markdown(f"""
            <div class="stock-card">
                <h4>#{i} {html.escape(str(stock['symbol']))} {html.escape(str(stock['name']))}</h4>
                <p><strong>综合评分:</strong> {stock['score']}/100 |
                <strong>建议:</strong> {html.escape(str(stock['rating']))} |
                <strong>当前价:</strong> {stock['latest_price']:.2f} {arrow}{change_pct:+.2f}% |
                <strong>范围:</strong> {html.escape(str(stock.get('board', '沪深主板')))}</p>
            </div>
            """, unsafe_allow_html=True)

            if stock.get("strategy_checks"):
                checks = stock.get("strategy_checks") or {}
                details = stock.get("strategy_details") or {}
                st.markdown("**策略命中**")
                check_cols = st.columns(min(5, max(1, len(checks))))
                for idx, (label, passed) in enumerate(checks.items()):
                    with check_cols[idx % len(check_cols)]:
                        st.metric(label, "通过" if passed else "缺失/未通过")
                detail_lines = []
                for key in ["买入观察", "卖出纪律", "市值过滤", "技术说明", "财务确认", "连涨3日", "主力净流入趋势", "15日涨停", "风险排除"]:
                    if details.get(key):
                        detail_lines.append(f"- **{key}**：{html.escape(str(details[key]))}")
                if detail_lines:
                    st.markdown("\n".join(detail_lines))

            ind = stock["indicators"]
            sig = stock["signals"]
            cols = st.columns(4)
            with cols[0]:
                macd_hist = ind.get("macd_hist", 0)
                st.markdown(f'<p style="font-size:1.05rem;margin:0"><b>MACD:</b> 柱:{macd_hist:.2f} DIF:{ind["macd"]:.2f} DEA:{ind["macd_signal"]:.2f}</p>', unsafe_allow_html=True)
                st.markdown(f'<p style="font-size:0.95rem;margin:0;opacity:0.85">{html.escape(str(sig.get("macd", sig.get("技术形态", "--"))))}</p>', unsafe_allow_html=True)
            with cols[1]:
                rsi6 = ind.get("rsi_6", ind.get("rsi", 0))
                rsi12 = ind.get("rsi_12", 0)
                rsi24 = ind.get("rsi_24", 0)
                st.markdown(f'<p style="font-size:1.05rem;margin:0"><b>RSI:</b> 6:{rsi6:.2f} 12:{rsi12:.2f} 24:{rsi24:.2f}</p>', unsafe_allow_html=True)
                st.markdown(f'<p style="font-size:0.95rem;margin:0;opacity:0.85">{html.escape(str(sig.get("rsi", "--")))}</p>', unsafe_allow_html=True)
            with cols[2]:
                st.markdown(f'<p style="font-size:1.05rem;margin:0"><b>KDJ:</b> K:{ind["kdj_k"]:.2f} D:{ind["kdj_d"]:.2f} J:{ind["kdj_j"]:.2f}</p>', unsafe_allow_html=True)
                st.markdown(f'<p style="font-size:0.95rem;margin:0;opacity:0.85">{html.escape(str(sig.get("kdj", "--")))}</p>', unsafe_allow_html=True)
            with cols[3]:
                boll_up = ind.get("boll_upper", 0)
                boll_mid = ind.get("boll_mid", 0)
                boll_low = ind.get("boll_lower", 0)
                st.markdown(f'<p style="font-size:1.05rem;margin:0"><b>布林带:</b> UP:{boll_up:.2f} MID:{boll_mid:.2f} LOW:{boll_low:.2f}</p>', unsafe_allow_html=True)
                st.markdown(f'<p style="font-size:0.95rem;margin:0;opacity:0.85">{html.escape(str(sig.get("boll", sig.get("卖出纪律", "--"))))}</p>', unsafe_allow_html=True)

            st.divider()


def recommended_stocks_page():
    """推荐股票页面 - 多策略智能选股推荐"""

    if 'rec_sector' not in st.session_state:
        st.session_state.rec_sector = "全部"
    if 'rec_num_stocks' not in st.session_state:
        st.session_state.rec_num_stocks = 5
    if 'rec_strategy' not in st.session_state:
        st.session_state.rec_strategy = "短线"

    def on_sector_change():
        st.session_state.rec_sector = st.session_state.rec_sector_select
        st.session_state.rec_data_loaded = False
        st.session_state.rec_results = None

    def on_num_stocks_change():
        st.session_state.rec_num_stocks = st.session_state.rec_num_slider
        st.session_state.rec_data_loaded = False
        st.session_state.rec_results = None

    def on_strategy_change():
        st.session_state.rec_strategy = st.session_state.rec_strategy_radio
        st.session_state.rec_data_loaded = False
        st.session_state.rec_results = None

    strategy = st.session_state.rec_strategy
    sector = st.session_state.rec_sector
    num_stocks = st.session_state.rec_num_stocks

    st.markdown(f'<h1 class="main-header">智能选股推荐 — {strategy}</h1>', unsafe_allow_html=True)

    strategy_options = ["短线", "长线", "激进突破型", "多因子稳健型"]
    if strategy not in strategy_options:
        strategy = "短线"
        st.session_state.rec_strategy = strategy
    st.radio("策略选择", options=strategy_options, index=strategy_options.index(strategy),
             horizontal=True, key="rec_strategy_radio", on_change=on_strategy_change)

    if strategy == "短线":
        st.info("基于MACD、RSI、KDJ、布林带等技术指标，筛选沪深主板短线候选；创业板、科创板、北交所不进入推荐池。")
    elif strategy == "长线":
        st.info("基于MA60趋势、MACD趋势等长线指标，筛选沪深主板长线候选；创业板、科创板、北交所不进入推荐池。")
    elif strategy == "激进突破型":
        st.info("纯量价突破策略：市值300亿以下、MA5>MA10>MA20、收盘价创20日新高、成交量大于前5日均量1.2倍；范围为沪深主板+创业板，排除科创板/北交所/ST。")
    else:
        st.info("多因子稳健型：先硬性过滤市值300亿以上、短期过热和重大风险事件；再按均线金叉/多头+放量、财务确认、连涨3日、主力净流入趋势≥3000万、既往15日内涨停评分，核心因子至少3/5且综合分≥70进入候选。")

    sector_options = ["全部", "苹果概念", "特斯拉概念", "电力", "算力租赁"]
    sector_index = sector_options.index(st.session_state.rec_sector)
    sector = st.selectbox("选择板块", options=sector_options,
                         index=sector_index,
                         key="rec_sector_select",
                         on_change=on_sector_change)

    num_stocks = st.slider("推荐数量", min_value=3, max_value=8,
                          value=st.session_state.rec_num_stocks,
                          key="rec_num_slider",
                          on_change=on_num_stocks_change)

    sector = st.session_state.rec_sector
    num_stocks = st.session_state.rec_num_stocks

    if 'rec_data_loaded' not in st.session_state:
        st.session_state.rec_data_loaded = False
    if 'rec_results' not in st.session_state:
        st.session_state.rec_results = None

    if not st.session_state.rec_results:
        latest_result = RecommendationService().latest(strategy, sector, num_stocks)
        if latest_result:
            st.session_state.rec_results = latest_result
            st.session_state.rec_data_loaded = True

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("刷新数据", type="secondary"):
            with status_loading("正在刷新智能推荐本地K线缓存，请稍候...", 20):
                cache_result = RecommendationService().refresh_strategy_kline_cache()
            st.session_state.rec_data_loaded = False
            st.session_state.rec_results = None
            st.success(
                f"本地K线缓存已刷新：成功 {cache_result.get('refreshed', 0)} / "
                f"{cache_result.get('total', 0)}，失败 {cache_result.get('failed', 0)}"
            )

    generate_clicked = st.button("生成推荐", type="primary")

    if generate_clicked:
        st.session_state.rec_results = None
        st.session_state.rec_data_loaded = False
        progress_placeholder = st.empty()
        progress_callback = _make_progress_callback(progress_placeholder, strategy, sector)
        progress_callback("启动", 5, {})
        try:
            st.session_state.rec_results = _run_recommendation_task(
                strategy,
                sector,
                num_stocks,
                progress_callback=progress_callback,
            )
            st.session_state.rec_data_loaded = True
        finally:
            progress_placeholder.empty()

    if not st.session_state.rec_data_loaded:
        st.info("选择策略和板块后，点击“生成推荐”开始分析。")

    if st.session_state.rec_results:
        display_recommendation_list(
            st.session_state.rec_results["recommended"],
            st.session_state.rec_results["title"],
            st.session_state.rec_results.get("diagnostics"),
        )
