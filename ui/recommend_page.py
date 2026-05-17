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
    return RecommendationService().run_t1_plan(
        strategy,
        sector,
        num_stocks,
        progress_callback=progress_callback,
    )


def _request_key(strategy, sector, num_stocks):
    return f"{strategy}:{sector}:{int(num_stocks or 0)}"


def _format_request_key_label(request_key):
    if not request_key:
        return "--"
    parts = str(request_key).split(":")
    if len(parts) != 3:
        return str(request_key)
    strategy, sector, num_stocks = parts
    return f"{strategy} / {sector} / {num_stocks}只"


def _result_matches_request(result, request_key):
    if not isinstance(result, dict):
        return False
    result_key = _request_key(result.get("strategy"), result.get("sector"), result.get("num_stocks"))
    return result_key == request_key


def _render_t1_plan_meta(result):
    if not isinstance(result, dict) or result.get("mode") != "T+1_PLAN":
        return
    generated = result.get("generated_at") or "--"
    base_date = result.get("generated_trade_date") or "--"
    plan_date = result.get("plan_for_trade_date") or "--"
    metrics = result.get("generation_metrics") or {}
    data_status = result.get("data_status") or {}
    st.info(
        f"T+1 推荐计划：生成时间 {generated}｜基准交易日 {base_date}｜计划入场日 {plan_date}。"
        "推荐列表不会因入场检查而改变。"
    )
    source = data_status.get("source") or "--"
    trigger = metrics.get("trigger") or "--"
    elapsed = metrics.get("elapsed_seconds")
    elapsed_text = f"{elapsed:.2f}s" if isinstance(elapsed, (int, float)) else "--"
    st.caption(f"缓存状态：{source}；生成触发：{trigger}；生成耗时：{elapsed_text}")
    cache_metrics = data_status.get("cache_read_metrics") or {}
    cache_elapsed = cache_metrics.get("elapsed_seconds")
    if isinstance(cache_elapsed, (int, float)):
        st.caption(f"缓存读取耗时：{cache_elapsed:.3f}s；未重新扫描股票池；实时行情未参与选股。")
    preheat = data_status.get("preheat") or {}
    if preheat:
        st.caption(
            f"预热状态：K线缓存 {preheat.get('kline_cache')}；"
            f"扩展信息缓存 {preheat.get('extended_info_cache')}"
        )


def _render_entry_check(entry_check):
    if not isinstance(entry_check, dict):
        return
    status = entry_check.get("status")
    message = entry_check.get("message") or ""
    if status != "ok":
        st.warning(message)
        return
    source = entry_check.get("source") or "--"
    checked_at = entry_check.get("checked_at") or "--"
    st.success(f"{message}｜实时来源：{source}｜检查时间：{checked_at}")
    rows = []
    for item in entry_check.get("items") or []:
        rows.append({
            "代码": item.get("symbol"),
            "名称": item.get("name"),
            "检查结果": item.get("status"),
            "原因": item.get("reason"),
            "计划价": item.get("plan_price"),
            "当前价": item.get("latest_price"),
            "涨跌幅": f"{item.get('change_pct'):+.2f}%" if item.get("change_pct") is not None else "--",
        })
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)


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

    if 'rec_entry_check' not in st.session_state:
        st.session_state.rec_entry_check = None
    if 'rec_is_running' not in st.session_state:
        st.session_state.rec_is_running = False
    if 'rec_last_error' not in st.session_state:
        st.session_state.rec_last_error = None
    if 'rec_active_request_key' not in st.session_state:
        st.session_state.rec_active_request_key = None

    service = RecommendationService()
    current_request_key = _request_key(strategy, sector, num_stocks)
    running_request_key = st.session_state.get("rec_active_request_key")
    is_current_request_running = bool(st.session_state.rec_is_running and running_request_key == current_request_key)
    is_other_request_running = bool(st.session_state.rec_is_running and running_request_key != current_request_key)
    running_label = _format_request_key_label(running_request_key)
    if st.session_state.rec_results and not _result_matches_request(st.session_state.rec_results, current_request_key):
        st.session_state.rec_results = None
        st.session_state.rec_data_loaded = False
        st.session_state.rec_entry_check = None
    if not st.session_state.rec_results and not st.session_state.rec_is_running:
        latest_result = service.latest_t1_plan(strategy, sector, num_stocks)
        if latest_result and _result_matches_request(latest_result, current_request_key):
            st.session_state.rec_results = latest_result
            st.session_state.rec_data_loaded = True
            pass

    col1, col2, col3 = st.columns([1, 1.2, 3])
    with col1:
        if st.button("刷新数据", type="secondary", disabled=st.session_state.rec_is_running):
            with status_loading("正在刷新智能推荐本地K线缓存，请稍候...", 20):
                cache_result = service.refresh_strategy_kline_cache()
            st.session_state.rec_data_loaded = False
            st.session_state.rec_results = None
            st.session_state.rec_entry_check = None
            st.session_state.rec_last_error = None
            st.success(
                f"本地K线缓存已刷新：成功 {cache_result.get('refreshed', 0)} / "
                f"{cache_result.get('total', 0)}，失败 {cache_result.get('failed', 0)}"
            )

    with col2:
        entry_check_clicked = st.button(
            "检查当前是否适合入场",
            type="secondary",
            disabled=st.session_state.rec_is_running or not bool(st.session_state.rec_results),
        )

    generate_label = "生成 T+1 推荐计划"
    if is_current_request_running:
        generate_label = "本策略生成中..."
    elif is_other_request_running:
        generate_label = "其他计划生成中"
    generate_clicked = st.button(
        generate_label,
        type="primary",
        disabled=st.session_state.rec_is_running,
    )

    if generate_clicked:
        st.session_state.rec_results = None
        st.session_state.rec_data_loaded = False
        st.session_state.rec_entry_check = None
        st.session_state.rec_last_error = None
        st.session_state.rec_is_running = True
        st.session_state.rec_active_request_key = current_request_key
        progress_placeholder = st.empty()
        progress_callback = _make_progress_callback(progress_placeholder, strategy, sector)
        progress_callback("启动", 5, {})
        try:
            result = _run_recommendation_task(
                strategy,
                sector,
                num_stocks,
                progress_callback=progress_callback,
            )
            if _result_matches_request(result, current_request_key):
                st.session_state.rec_results = result
                st.session_state.rec_data_loaded = True
            else:
                st.session_state.rec_last_error = "推荐结果与当前筛选条件不匹配，已丢弃旧结果。"
        except Exception as exc:
            st.session_state.rec_last_error = f"生成 T+1 推荐计划失败：{exc}"
        finally:
            st.session_state.rec_is_running = False
            if st.session_state.get("rec_active_request_key") == current_request_key:
                st.session_state.rec_active_request_key = None
            progress_placeholder.empty()

    if entry_check_clicked:
        st.session_state.rec_entry_check = service.check_entry_plan(st.session_state.rec_results)

    if st.session_state.rec_last_error:
        st.error(st.session_state.rec_last_error)

    if is_current_request_running:
        st.info("当前策略正在生成 T+1 推荐计划，完成前不会展示旧推荐或旧诊断。")
        return
    if is_other_request_running:
        st.info(f"其他 T+1 计划正在生成：{running_label}。当前策略尚未开始生成，完成后可再点击生成。")

    if not st.session_state.rec_data_loaded:
        st.info("选择策略和板块后，点击“生成 T+1 推荐计划”开始收盘后/盘后计划分析。")

    if st.session_state.rec_results and _result_matches_request(st.session_state.rec_results, current_request_key):
        _render_t1_plan_meta(st.session_state.rec_results)
        st.caption("已读取 T+1 推荐计划缓存；未重新扫描股票池。只有点击“生成 T+1 推荐计划”才会重新运行策略。")
        _render_entry_check(st.session_state.rec_entry_check)
        display_recommendation_list(
            st.session_state.rec_results["recommended"],
            st.session_state.rec_results["title"],
            st.session_state.rec_results.get("diagnostics"),
        )
