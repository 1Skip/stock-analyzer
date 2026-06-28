"""智能推荐页面 — 多策略智能选股推荐"""
import html
from datetime import date, datetime

import streamlit as st
from recommendation_service import RecommendationService, SELECTION_DATA_VERSION
from ui.scheduler_status import render_scheduler_status
from ui.loading import render_status_loading, status_loading
from ui.stock_search import suggest_stock_inputs


def _format_progress_message(strategy, sector, stage, metrics):
    metrics = metrics or {}
    parts = [f"正在分析{sector}板块（{strategy}）", f"阶段：{stage}"]
    if "result_count" not in metrics:
        metrics = {**metrics, "result_count": 0}
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
        "result_count": "当前命中",
    }
    for key, label in label_map.items():
        if key in metrics:
            parts.append(f"{label} {metrics[key]}")
    return " ｜ ".join(parts)


def _render_progress_html(progress_placeholder, message, percent):
    percent = max(0, min(100, int(percent or 0)))
    render_status_loading(progress_placeholder, message or "正在生成 T+1 推荐计划", percent)


def _save_progress_snapshot(request_key, strategy, sector, stage, percent, metrics, message):
    if not request_key:
        return
    snapshots = st.session_state.setdefault("rec_progress_snapshots", {})
    snapshots[request_key] = {
        "strategy": strategy,
        "sector": sector,
        "stage": stage,
        "percent": percent,
        "metrics": metrics or {},
        "message": message,
    }


def _render_saved_progress(progress_placeholder, request_key, strategy, sector):
    snapshots = st.session_state.get("rec_progress_snapshots") or {}
    snapshot = snapshots.get(request_key) or {}
    percent = max(0, min(100, int(snapshot.get("percent") or 5)))
    message = snapshot.get("message")
    if not message:
        message = _format_progress_message(strategy, sector, "\u8fd0\u884c\u4e2d", snapshot.get("metrics") or {})
    _render_progress_html(progress_placeholder, message, percent)


def _clear_progress_snapshot(request_key):
    snapshots = st.session_state.get("rec_progress_snapshots")
    if isinstance(snapshots, dict) and request_key in snapshots:
        snapshots.pop(request_key, None)


def _make_progress_callback(progress_placeholder, strategy, sector, request_key=None):
    def update(stage, percent, metrics=None):
        percent = max(0, min(100, int(percent or 0)))
        metrics = metrics or {}
        message = _format_progress_message(strategy, sector, stage, metrics)
        _save_progress_snapshot(request_key, strategy, sector, stage, percent, metrics, message)
        _render_progress_html(progress_placeholder, message, percent)
    return update


def _run_recommendation_task(strategy, sector, num_stocks, progress_callback=None):
    """后台生成推荐列表。"""
    return RecommendationService().run_t1_plan(
        strategy,
        sector,
        num_stocks,
        progress_callback=progress_callback,
        preheat_extended_info=True,
    )


def _sector_options_for_strategy(strategy):
    if strategy in ("激进突破型", "多因子稳健型"):
        return ["全部"]
    if strategy == "短线经典版":
        return ["全部"]
    if strategy == "短线":
        return ["全部", "苹果概念", "特斯拉概念"]
    return ["全部"]


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
    if str(result.get("strategy") or "") in ("短线", "短线经典版") and result.get("selection_data_version") != SELECTION_DATA_VERSION:
        return False
    return result_key == request_key


def _has_recommendations(result):
    return bool(isinstance(result, dict) and result.get("recommended"))


def _render_t1_plan_meta(result):
    if not isinstance(result, dict) or result.get("mode") != "T+1_PLAN":
        return
    generated = result.get("generated_at") or "--"
    base_date = result.get("generated_trade_date") or "--"
    plan_date = result.get("plan_for_trade_date") or "--"
    st.info(
        f"T+1 推荐计划：生成时间 {generated}｜基准交易日 {base_date}｜计划入场日 {plan_date}。"
        "推荐列表不会因入场检查而改变。"
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
        st.dataframe(rows, width="stretch", hide_index=True)


def _render_manual_trade_review(trade_review, service=None):
    if not isinstance(trade_review, dict):
        return
    summary = trade_review.get("summary") or {}
    with st.expander("手工成交成功率", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("已记录", summary.get("total_records", summary.get("records", 0)))
        success_rate = summary.get("success_rate_pct")
        avg_return = summary.get("avg_return_pct")
        col2.metric("成功率", f"{success_rate:.2f}%" if success_rate is not None else "--")
        col3.metric("平均收益", _format_return(avg_return))
        col4.metric(
            "已结/持有",
            f"{summary.get('closed_records', summary.get('records', 0))} / {summary.get('holding_count', 0)}",
        )
        readiness = summary.get("learning_readiness") or {}
        if readiness.get("ready"):
            st.success(readiness.get("message") or "实盘样本已达到提醒门槛，可以评估是否接入实盘反馈学习层。")
        elif readiness:
            st.caption(readiness.get("message") or "实盘样本继续积累，达到门槛后会自动提醒。")
        by_strategy = summary.get("by_strategy") or []
        if by_strategy:
            st.dataframe(
                [
                    {
                        "策略": item.get("strategy"),
                        "板块": item.get("sector"),
                        "记录数": item.get("records"),
                        "成功数": item.get("success_count"),
                        "持有中": item.get("holding_count", 0),
                        "成功率": _format_return(item.get("success_rate_pct")),
                        "平均收益": _format_return(item.get("avg_return_pct")),
                    }
                    for item in by_strategy
                ],
                width="stretch",
                hide_index=True,
            )
        records = trade_review.get("records") or []
        if records:
            st.dataframe(_manual_trade_record_rows(records[:50]), width="stretch", hide_index=True)
            if service is not None:
                with st.expander("删除手工成交记录", expanded=False):
                    for index, row in enumerate(records[:50]):
                        col_info, col_action = st.columns([5, 1])
                        with col_info:
                            st.caption(_manual_trade_delete_label(row))
                        with col_action:
                            if st.button("删除", key=f"manual_trade_delete_{row.get('record_key') or index}"):
                                result = service.delete_manual_trade_record(row.get("record_key"))
                                if result.get("success"):
                                    st.success(result.get("message") or "成交记录已删除。")
                                    st.session_state.rec_manual_trade_review = service.evaluate_manual_trade_success_rate(limit=200)
                                    st.rerun()
                                else:
                                    st.error(result.get("message") or "删除失败。")


def _render_manual_trade_form(current_plan, service, strategy, sector, history_rows=None):
    plan_options = _manual_trade_plan_options(current_plan, history_rows or [])
    with st.expander("录入推荐股实际买卖结果", expanded=False):
        query = st.text_input(
            "股票代码或名称",
            value="",
            key="manual_trade_stock_query",
            on_change=_queue_manual_trade_search,
            args=(plan_options,),
        )
        if st.button("搜索推荐记录", type="secondary"):
            _queue_manual_trade_search(plan_options)
        matches = st.session_state.get("manual_trade_matches") or []
        search_attempted = bool(st.session_state.get("manual_trade_search_attempted"))
        if str(st.session_state.get("manual_trade_query") or "").strip() != str(query or "").strip():
            matches = []
            search_attempted = False
        if search_attempted and not matches and str(query or "").strip():
            st.warning("没有识别到这只股票，请输入正确的股票代码或名称。")
        selected_match = matches[0] if matches else None
        if selected_match:
            st.caption(f"已找到推荐记录：{selected_match['label']}")
        is_holding = st.checkbox(
            "还在持有，暂不填写卖出时间和卖出价",
            value=False,
            key="manual_trade_is_holding",
        )
        with st.form("manual_trade_record_form", clear_on_submit=False):
            col1, col2 = st.columns(2)
            with col1:
                buy_date = st.date_input("买入时间", value=date.today())
                buy_price = st.number_input("买入价位", min_value=0.01, value=0.01, step=0.01, format="%.2f")
            with col2:
                sell_date = st.date_input("卖出时间", value=date.today(), disabled=is_holding)
                sell_price = st.number_input(
                    "卖出价位",
                    min_value=0.01,
                    value=0.01,
                    step=0.01,
                    format="%.2f",
                    disabled=is_holding,
            )
            submitted = st.form_submit_button("保存成交结果")
        if submitted:
            if not selected_match:
                st.error("请先搜索并选中一只股票，再保存成交结果。")
                return
            plan = selected_match["plan"]
            selected_stock = selected_match["stock"]
            selected_symbol = str(selected_stock.get("symbol") or "").strip()
            result = service.record_manual_trade_outcome(
                plan,
                selected_symbol,
                buy_date=buy_date,
                buy_price=buy_price,
                sell_date=None if is_holding else sell_date,
                sell_price=None if is_holding else sell_price,
                is_holding=is_holding,
                note="",
            )
            if result.get("success"):
                st.success(result.get("message") or "成交结果已记录。")
                st.session_state.manual_trade_matches = []
                st.session_state.manual_trade_search_attempted = False
                st.session_state.rec_manual_trade_review = service.evaluate_manual_trade_success_rate(limit=200)
            else:
                st.error(result.get("message") or "成交结果保存失败。")


def _manual_trade_plan_options(current_plan, history_rows):
    options = []
    seen = set()

    def add_plan(plan, source):
        if not isinstance(plan, dict) or not plan.get("recommended"):
            return
        key = str(plan.get("history_key") or plan.get("cache_key") or plan.get("generated_at") or id(plan))
        if key in seen:
            return
        seen.add(key)
        generated = str(plan.get("generated_at") or "--")[:19]
        plan_date = str(plan.get("plan_for_trade_date") or "--")[:10]
        label = (
            f"{source}｜{generated}｜{plan.get('strategy', '--')}｜"
            f"{plan.get('sector', '--')}｜入场日 {plan_date}｜{len(plan.get('recommended') or [])}只"
        )
        options.append({"key": key, "label": label, "plan": plan})

    add_plan(current_plan, "当前计划")
    for row in history_rows or []:
        add_plan((row or {}).get("plan"), "历史计划")
    return options


def _manual_trade_record_rows(records):
    return [
        {
            "记录时间": row.get("recorded_at"),
            "代码": row.get("symbol"),
            "名称": row.get("name"),
            "买入时间": row.get("buy_date"),
            "买入价": row.get("buy_price"),
            "卖出时间": row.get("sell_date"),
            "卖出价": row.get("sell_price"),
            "收益率": _format_return(row.get("return_pct")),
            "结果": "持有中" if row.get("is_holding") else "成功" if row.get("is_success") else "失败",
        }
        for row in records or []
    ]


def _manual_trade_delete_label(row):
    result = "持有中" if row.get("is_holding") else "成功" if row.get("is_success") else "失败"
    return (
        f"{row.get('symbol', '--')} {row.get('name', '--')}｜"
        f"买入 {row.get('buy_date', '--')} {row.get('buy_price', '--')}｜"
        f"卖出 {row.get('sell_date') or '--'} {row.get('sell_price') or '--'}｜{result}"
    )


def _queue_manual_trade_search(plan_options):
    """Submit the current trade-record stock input for both Enter and button search."""
    query = st.session_state.get("manual_trade_stock_query", "")
    st.session_state.manual_trade_matches = _manual_trade_stock_matches(plan_options, query)
    st.session_state.manual_trade_query = query
    st.session_state.manual_trade_search_attempted = True


def _manual_trade_stock_matches(plan_options, query):
    text = str(query or "").strip()
    if not text:
        return []
    lookup_values = _manual_trade_lookup_values(text)
    matches = []
    for option in plan_options or []:
        plan = option.get("plan") or {}
        for stock in plan.get("recommended") or []:
            symbol = str(stock.get("symbol") or "").strip()
            name = str(stock.get("name") or "").strip()
            candidates = {
                symbol.lower(),
                name.lower(),
                _normalize_manual_trade_text(symbol),
                _normalize_manual_trade_text(name),
            }
            if not any(value and any(value in candidate or candidate in value for candidate in candidates) for value in lookup_values):
                continue
            generated = str(plan.get("generated_at") or "--")[:19]
            plan_date = str(plan.get("plan_for_trade_date") or "--")[:10]
            matches.append({
                "plan": plan,
                "stock": stock,
                "label": (
                    f"{symbol} {name}｜{generated}｜{plan.get('strategy', '--')}｜"
                    f"{plan.get('sector', '--')}｜入场日 {plan_date}"
                ),
            })
    if matches:
        return matches
    fallback = _manual_trade_fallback_match(text)
    return [fallback] if fallback else []


def _manual_trade_lookup_values(query):
    values = {_normalize_manual_trade_text(query), str(query or "").strip().lower()}
    for item in suggest_stock_inputs(query, "CN", limit=5):
        values.add(_normalize_manual_trade_text(item.get("symbol")))
        values.add(_normalize_manual_trade_text(item.get("name")))
    return {value for value in values if value}


def _manual_trade_fallback_match(query):
    text = str(query or "").strip()
    if not text:
        return None
    suggestions = suggest_stock_inputs(text, "CN", limit=1)
    if suggestions:
        symbol = str(suggestions[0].get("symbol") or "").strip()
        name = str(suggestions[0].get("name") or symbol).strip()
    elif text.isdigit() and len(text) <= 6:
        symbol = text.zfill(6)
        name = symbol
    else:
        return None
    if not symbol:
        return None
    now = datetime.now().isoformat(timespec="seconds")
    stock = {
        "symbol": symbol,
        "name": name,
        "latest_price": None,
        "price": None,
        "score": None,
        "rating": "手工补录",
    }
    plan = {
        "generated_at": now,
        "generated_trade_date": None,
        "plan_for_trade_date": None,
        "strategy": "手工补录",
        "sector": "手工录入",
        "num_stocks": 1,
        "recommended": [stock],
        "manual_trade_source": "manual_input_fallback",
    }
    return {
        "plan": plan,
        "stock": stock,
        "label": f"{symbol} {name}｜手工补录",
    }


def _normalize_manual_trade_text(value):
    return "".join(str(value or "").strip().lower().split())


def _format_return(value):
    return f"{value:+.2f}%" if isinstance(value, (int, float)) else "--"


def _safe_positive_float(value):
    try:
        number = float(value)
        if number > 0 and number == number:
            return round(number, 4)
    except (TypeError, ValueError):
        pass
    return 0.01


def _render_quality_diagnostics(diagnostics):
    quality = (diagnostics or {}).get("quality") if isinstance(diagnostics, dict) else None
    if not isinstance(quality, dict):
        return
    with st.expander("数据质量与解释覆盖", expanded=False):
        col1, col2, col3 = st.columns(3)
        col1.metric("推荐数量", quality.get("stock_count", 0))
        col2.metric("解释覆盖", quality.get("explainable_count", 0))
        col3.metric("风险提示", quality.get("risk_flag_count", 0))
        missing = quality.get("missing_required_fields") or {}
        indicator_missing = quality.get("missing_indicator_fields") or {}
        if missing:
            st.caption("关键字段缺失：" + "；".join(f"{key} {value}只" for key, value in missing.items()))
        if indicator_missing:
            top = sorted(indicator_missing.items(), key=lambda item: item[1], reverse=True)[:6]
            st.caption("指标字段缺失：" + "；".join(f"{key} {value}只" for key, value in top))
        if not missing and not indicator_missing:
            st.caption("关键字段和主要指标完整。")


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

    core_summary = diagnostics.get("core_factor_summary") or {}
    if core_summary:
        parts = []
        for name, item in core_summary.items():
            passed = int((item or {}).get("passed", 0))
            failed = int((item or {}).get("failed", 0))
            total = passed + failed
            if total:
                parts.append(f"{html.escape(str(name))} {passed}/{total}")
        if parts:
            st.caption("核心因子命中：" + "；".join(parts))

    data_quality = diagnostics.get("deep_data_quality") or {}
    if data_quality:
        parts = []
        for name, item in data_quality.items():
            available = int((item or {}).get("available", 0))
            missing = int((item or {}).get("missing", 0))
            source_failed = int((item or {}).get("source_failed", 0))
            source_empty = int((item or {}).get("source_empty", 0))
            total = available + missing + source_failed + source_empty
            if total:
                unavailable = total - available
                parts.append(f"{html.escape(str(name))} 可用{available}/{total}，不可用{unavailable}")
        if parts:
            st.caption("深度数据可用性：" + "；".join(parts))


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


def _render_short_term_diagnostics(diagnostics):
    if not diagnostics:
        return
    st.markdown("**筛选诊断**")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("热门板块", diagnostics.get("hot_boards", 0))
    col2.metric("候选池", diagnostics.get("raw_pool", 0))
    col3.metric("已分析", diagnostics.get("analyzed", 0))
    col4.metric("技术通过", diagnostics.get("technical_passed", 0))
    pattern_passed = diagnostics.get("pattern_passed")
    col5.metric("最终命中", diagnostics.get("result_count", 0))
    if pattern_passed is not None:
        st.caption(f"全部短线形态通过：{pattern_passed} 只。")
    failures = diagnostics.get("failures") or {}
    if failures:
        top_failures = sorted(failures.items(), key=lambda item: item[1], reverse=True)[:8]
        st.caption("主要卡点：" + "；".join(f"{html.escape(str(reason))} {count}只" for reason, count in top_failures))


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


def _fmt_profile_money_yi(value):
    try:
        if value is None or value == "":
            return "--"
        number = float(value)
        if number != number:
            return "--"
        return f"{number / 100000000:.2f}亿"
    except (TypeError, ValueError):
        return "--"


def _fmt_profile_number(value, suffix="", precision=2):
    try:
        if value is None or value == "":
            return "--"
        number = float(value)
        if number != number:
            return "--"
        return f"{number:.{precision}f}{suffix}"
    except (TypeError, ValueError):
        return "--"


def _render_recommendation_profile(stock):
    profile = stock.get("profile") if isinstance(stock.get("profile"), dict) else {}
    if not profile:
        st.caption("基础资料：暂无返回，已不使用假数据补齐。")
        return
    industry = profile.get("industry") or "--"
    market_cap = _fmt_profile_money_yi(profile.get("market_cap") or stock.get("market_cap"))
    pe = _fmt_profile_number(profile.get("pe_ttm") or profile.get("pe"))
    pb = _fmt_profile_number(profile.get("pb"))
    turnover = _fmt_profile_number(profile.get("turnover_rate"), "%")
    source = profile.get("source") or "公开数据源"
    st.caption(
        "基础资料："
        f"行业 {html.escape(str(industry))}｜"
        f"市值 {market_cap}｜"
        f"PE {pe}｜"
        f"PB {pb}｜"
        f"换手率 {turnover}｜"
        f"来源 {html.escape(str(source))}"
    )


def _render_trade_plan(stock):
    plan = stock.get("trade_plan") if isinstance(stock.get("trade_plan"), dict) else {}
    if not plan:
        return
    with st.expander("买卖点计划", expanded=True):
        cols = st.columns(4)
        cols[0].metric("买入观察区", plan.get("buy_zone") or "--")
        cols[1].metric("止损线", _fmt_profile_number(plan.get("stop_loss")))
        cols[2].metric("第一压力", _fmt_profile_number(plan.get("take_profit_1")))
        cols[3].metric("建议仓位", plan.get("position") or "--")
        if plan.get("add_condition"):
            st.markdown(f"**加仓确认**：{html.escape(str(plan['add_condition']))}")
        invalid = plan.get("invalid_conditions") or []
        if invalid:
            st.markdown("**失效条件**")
            st.markdown("\n".join(f"- {html.escape(str(item))}" for item in invalid[:4]))
        if plan.get("take_profit_2") is not None:
            st.caption(f"第二目标位：{_fmt_profile_number(plan.get('take_profit_2'))}")
        if plan.get("data_basis"):
            st.caption(html.escape(str(plan["data_basis"])))


def _fmt_hit_number(value, precision=2):
    try:
        if value is None or value == "":
            return "--"
        number = float(value)
        if number != number:
            return "--"
        return f"{number:.{precision}f}"
    except (TypeError, ValueError):
        return "--"


def _strategy_check_detail(label, stock, details):
    ind = stock.get("indicators") if isinstance(stock.get("indicators"), dict) else {}
    sig = stock.get("signals") if isinstance(stock.get("signals"), dict) else {}
    if label == "成交量":
        if details.get(label):
            return html.escape(str(details[label]))
        return "近一日成交量需满足5日量比>=1.10；当前量能请结合下方成交量/K线图复核。"
    if label == "MACD":
        return (
            f"{html.escape(str(sig.get('macd') or '--'))}；"
            f"DIF {_fmt_hit_number(ind.get('macd'))} / DEA {_fmt_hit_number(ind.get('macd_signal'))} / "
            f"柱 {_fmt_hit_number(ind.get('macd_hist'))}"
        )
    if label == "RSI":
        return (
            f"{html.escape(str(sig.get('rsi') or '--'))}；"
            f"RSI6 {_fmt_hit_number(ind.get('rsi_6', ind.get('rsi')))} / "
            f"RSI12 {_fmt_hit_number(ind.get('rsi_12'))} / RSI24 {_fmt_hit_number(ind.get('rsi_24'))}；"
            "短线主筛区间为 25-70"
        )
    if label == "KDJ":
        return (
            f"{html.escape(str(sig.get('kdj') or '--'))}；"
            f"K {_fmt_hit_number(ind.get('kdj_k'))} / D {_fmt_hit_number(ind.get('kdj_d'))} / "
            f"J {_fmt_hit_number(ind.get('kdj_j'))}"
        )
    if label == "BOLL":
        return (
            f"{html.escape(str(sig.get('boll') or '--'))}；"
            f"现价 {_fmt_hit_number(stock.get('latest_price'))} / 上轨 {_fmt_hit_number(ind.get('boll_upper'))} / "
            f"中轨 {_fmt_hit_number(ind.get('boll_mid'))} / 下轨 {_fmt_hit_number(ind.get('boll_lower'))}"
        )
    if label == "技术命中数":
        if details.get(label):
            return html.escape(str(details[label]))
        return "成交量、MACD、RSI、KDJ、BOLL 五项中至少命中 3 项，才进入短线候选。"
    if details.get(label):
        return html.escape(str(details[label]))
    return "该项暂无更细返回，按策略结果展示。"


def _render_strategy_checks(stock):
    checks = stock.get("strategy_checks") if isinstance(stock.get("strategy_checks"), dict) else {}
    if not checks:
        return
    details = stock.get("strategy_details") if isinstance(stock.get("strategy_details"), dict) else {}
    st.markdown("**策略命中**")
    primary_order = ["成交量", "MACD", "RSI", "KDJ", "BOLL", "技术命中数"]
    ordered = [key for key in primary_order if key in checks]
    ordered.extend(key for key in checks if key not in ordered)
    lines = []
    for label in ordered:
        value = checks.get(label)
        status = f"{int(value or 0)}/5" if label == "技术命中数" else ("命中" if value else "未命中")
        lines.append(
            f"- **{html.escape(str(label))}**：{status}。"
            f"{_strategy_check_detail(label, stock, details)}"
        )
    st.markdown("\n".join(lines))


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
        elif "短线经典版" in strategy_name:
            _render_short_term_diagnostics(diagnostics or {})
            st.info("短线经典版先看热门板块候选池与成交量、MACD、RSI、KDJ、BOLL，不检查二板以上、回调天数、回调幅度、放量反包/涨停板四项形态硬过滤。上方诊断会显示具体卡点。")
        elif "短线" in strategy_name:
            _render_short_term_diagnostics(diagnostics or {})
            st.info("短线先看热门板块候选池与成交量、MACD、RSI、KDJ、BOLL；全部还会检查二板以上、回调天数、回调幅度、放量反包/涨停板。上方诊断会显示具体卡点。")
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
            st.markdown(f"#### #{i} {stock['symbol']} {stock['name']}")
            st.markdown(
                f"**综合评分:** {stock['score']}/100 | "
                f"**建议:** {stock['rating']} | "
                f"**当前价:** {stock['latest_price']:.2f} {arrow}{change_pct:+.2f}% | "
                f"**范围:** {stock.get('board', '沪深主板')}"
            )
            if stock.get("alpha_score") is not None:
                reasons = "；".join(str(item) for item in (stock.get("rank_reason") or [])[:3])
                penalties = "；".join(str(item) for item in (stock.get("rank_penalty") or [])[:2])
                alpha_line = (
                    f"**Alpha评分**：{stock.get('alpha_score')}/100（{html.escape(str(stock.get('alpha_grade', '--')))}）"
                )
                if reasons:
                    alpha_line += f"｜排序理由：{html.escape(reasons)}"
                if penalties:
                    alpha_line += f"｜扣分：{html.escape(penalties)}"
                st.caption(alpha_line)
            if stock.get("learning_status"):
                learning_line = (
                    f"**短线学习**：{html.escape(str(stock.get('learning_status')))}"
                    f"｜学习加权 {stock.get('learning_bonus', 0):+.1f}"
                )
                if stock.get("learned_alpha_score") is not None:
                    learning_line += f"｜学习后Alpha {stock.get('learned_alpha_score')}/100"
                if stock.get("learning_reason"):
                    learning_line += f"｜{html.escape(str(stock.get('learning_reason')))}"
                st.caption(learning_line)
            _render_recommendation_profile(stock)
            _render_trade_plan(stock)

            explanation = stock.get("explanation") if isinstance(stock.get("explanation"), dict) else {}
            if explanation:
                with st.expander("推荐解释与数据缺口", expanded=False):
                    reasons = explanation.get("why_selected") or []
                    risks = explanation.get("risk_flags") or []
                    missing = explanation.get("missing_data") or []
                    note = explanation.get("confidence_note") or ""
                    if reasons:
                        st.markdown("**入选依据**")
                        st.markdown("\n".join(f"- {html.escape(str(item))}" for item in reasons[:5]))
                    failed_reasons = [item for item in risks if str(item).startswith("未通过：")]
                    other_risks = [item for item in risks if item not in failed_reasons]
                    if failed_reasons:
                        st.markdown("**未通过条件**")
                        st.markdown("\n".join(f"- {html.escape(str(item))}" for item in failed_reasons[:5]))
                    if other_risks:
                        st.markdown("**风险/扣分**")
                        st.markdown("\n".join(f"- {html.escape(str(item))}" for item in other_risks[:5]))
                    if missing:
                        st.caption("缺失证据：" + "；".join(html.escape(str(item)) for item in missing[:8]))
                    entry_conditions = explanation.get("entry_conditions") or []
                    invalid_conditions = explanation.get("invalid_conditions") or []
                    if entry_conditions:
                        st.markdown("**入场条件**")
                        st.markdown("\n".join(f"- {html.escape(str(item))}" for item in entry_conditions[:4]))
                    if invalid_conditions:
                        st.markdown("**失效条件**")
                        st.markdown("\n".join(f"- {html.escape(str(item))}" for item in invalid_conditions[:4]))
                    if note:
                        st.caption(note)

            _render_strategy_checks(stock)

            ind = stock["indicators"]
            sig = stock["signals"]
            cols = st.columns(5)
            with cols[0]:
                macd_hist = ind.get("macd_hist", 0)
                st.markdown(f"**MACD:** 柱:{macd_hist:.2f} DIF:{ind['macd']:.2f} DEA:{ind['macd_signal']:.2f}")
                st.caption(str(sig.get("macd", sig.get("技术形态", "--"))))
            with cols[1]:
                rsi6 = ind.get("rsi_6", ind.get("rsi", 0))
                rsi12 = ind.get("rsi_12", 0)
                rsi24 = ind.get("rsi_24", 0)
                st.markdown(f"**RSI:** 6:{rsi6:.2f} 12:{rsi12:.2f} 24:{rsi24:.2f}")
                st.caption(str(sig.get("rsi", "--")))
            with cols[2]:
                st.markdown(f"**KDJ:** K:{ind['kdj_k']:.2f} D:{ind['kdj_d']:.2f} J:{ind['kdj_j']:.2f}")
                st.caption(str(sig.get("kdj", "--")))
            with cols[3]:
                boll_up = ind.get("boll_upper", 0)
                boll_mid = ind.get("boll_mid", 0)
                boll_low = ind.get("boll_lower", 0)
                st.markdown(f"**布林带:** UP:{boll_up:.2f} MID:{boll_mid:.2f} LOW:{boll_low:.2f}")
                st.caption(str(sig.get("boll", sig.get("卖出纪律", "--"))))
            with cols[4]:
                ma5 = ind.get("ma5", 0)
                ma10 = ind.get("ma10", 0)
                ma20 = ind.get("ma20", 0)
                ma30 = ind.get("ma30", 0)
                st.markdown(f"**均线:** MA5:{ma5:.2f} MA10:{ma10:.2f}")
                st.caption(f"MA20:{ma20:.2f} MA30:{ma30:.2f}")
            if stock.get("display_indicator_context"):
                st.caption("指标口径：1年前复权日K，公式与个股分析页一致。")

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
        st.session_state.rec_manual_trade_review = None

    def on_num_stocks_change():
        st.session_state.rec_num_stocks = st.session_state.rec_num_slider
        st.session_state.rec_data_loaded = False
        st.session_state.rec_results = None

    def on_strategy_change():
        st.session_state.rec_strategy = st.session_state.rec_strategy_radio
        valid_sectors = _sector_options_for_strategy(st.session_state.rec_strategy)
        if st.session_state.get("rec_sector") not in valid_sectors:
            st.session_state.rec_sector = "全部"
            st.session_state.rec_sector_select = "全部"
        st.session_state.rec_data_loaded = False
        st.session_state.rec_results = None
        st.session_state.rec_manual_trade_review = None

    strategy = st.session_state.rec_strategy
    sector = st.session_state.rec_sector
    num_stocks = st.session_state.rec_num_stocks

    st.markdown(f"# 智能选股推荐 - {strategy}")
    render_scheduler_status()

    strategy_options = ["短线", "短线经典版", "激进突破型", "多因子稳健型"]
    if strategy not in strategy_options:
        strategy = "短线"
        st.session_state.rec_strategy = strategy
    st.radio("策略选择", options=strategy_options, index=strategy_options.index(strategy),
             horizontal=True, key="rec_strategy_radio", on_change=on_strategy_change)

    if strategy == "短线":
        st.info("基于MACD、RSI、KDJ、布林带等技术指标，筛选沪深主板短线候选；创业板、科创板、北交所不进入推荐池。")
    elif strategy == "短线经典版":
        st.info("经典短线：沿用短线热门板块候选池与成交量、MACD、RSI、KDJ、BOLL 技术过滤，不启用二板以上、2-8天回调、回撤不超50%、放量反包/涨停板四项形态硬过滤。")
    elif strategy == "激进突破型":
        st.info("纯量价突破策略：市值300亿以下、MA5>MA10>MA20、收盘价创20日新高、成交量大于前5日均量1.2倍；范围为沪深主板+创业板，排除科创板/北交所/ST。")
    else:
        st.info("多因子稳健型：先硬性过滤市值300亿以上、短期过热和重大风险事件；再按均线金叉/多头+放量、财务确认、连涨3日、主力净流入趋势≥3000万、既往15日内涨停评分，核心因子至少3/5且综合分≥70进入候选。")

    sector_options = _sector_options_for_strategy(strategy)
    if st.session_state.rec_sector not in sector_options:
        st.session_state.rec_sector = "全部"
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
    if 'rec_manual_trade_review' not in st.session_state:
        st.session_state.rec_manual_trade_review = None
    if 'rec_is_running' not in st.session_state:
        st.session_state.rec_is_running = False
    if 'rec_last_error' not in st.session_state:
        st.session_state.rec_last_error = None
    if 'rec_active_request_key' not in st.session_state:
        st.session_state.rec_active_request_key = None
    if 'rec_progress_snapshots' not in st.session_state:
        st.session_state.rec_progress_snapshots = {}

    service = RecommendationService()
    current_request_key = _request_key(strategy, sector, num_stocks)
    if st.session_state.rec_manual_trade_review is None and not st.session_state.rec_is_running:
        st.session_state.rec_manual_trade_review = service.evaluate_manual_trade_success_rate(limit=200)
    running_request_key = st.session_state.get("rec_active_request_key")
    is_current_request_running = bool(st.session_state.rec_is_running and running_request_key == current_request_key)
    is_other_request_running = bool(st.session_state.rec_is_running and running_request_key != current_request_key)
    running_label = _format_request_key_label(running_request_key)
    if st.session_state.rec_results and not _result_matches_request(st.session_state.rec_results, current_request_key):
        st.session_state.rec_results = None
        st.session_state.rec_data_loaded = False
        st.session_state.rec_entry_check = None
        st.session_state.rec_manual_trade_review = None
    if not st.session_state.rec_results and not st.session_state.rec_is_running:
        latest_result = service.latest_t1_plan(strategy, sector, num_stocks)
        if (
            latest_result
            and _result_matches_request(latest_result, current_request_key)
            and _has_recommendations(latest_result)
        ):
            st.session_state.rec_results = latest_result
            st.session_state.rec_data_loaded = True
            pass
        elif latest_result and _result_matches_request(latest_result, current_request_key):
            st.session_state.rec_last_error = "读取到的 T+1 推荐计划缓存为空，已跳过展示；请点击“生成 T+1 推荐计划”重新扫描。"

    generate_label = "生成 T+1 推荐计划"
    if is_current_request_running:
        generate_label = "本策略生成中..."
    elif is_other_request_running:
        generate_label = "其他计划生成中"

    col_generate, col_entry, col_refresh = st.columns([2.0, 1.7, 1.4])
    with col_generate:
        generate_clicked = st.button(
            generate_label,
            type="primary",
            disabled=st.session_state.rec_is_running,
            use_container_width=True,
        )
    with col_entry:
        entry_check_clicked = st.button(
            "检查当前是否适合入场",
            type="secondary",
            disabled=st.session_state.rec_is_running or not bool(st.session_state.rec_results),
            use_container_width=True,
        )
    with col_refresh:
        if st.button(
            "刷新K线缓存",
            type="secondary",
            disabled=st.session_state.rec_is_running,
            use_container_width=True,
        ):
            with status_loading("正在更新推荐策略日K缓存，不是读取T+1推荐计划缓存，请稍候...", 20):
                cache_result = service.refresh_strategy_kline_cache()
            st.session_state.rec_data_loaded = False
            st.session_state.rec_results = None
            st.session_state.rec_entry_check = None
            st.session_state.rec_manual_trade_review = None
            st.session_state.rec_last_error = None
            st.success(
                f"推荐策略日K缓存已刷新：成功 {cache_result.get('refreshed', 0)} / "
                f"{cache_result.get('total', 0)}，失败 {cache_result.get('failed', 0)}"
            )

    if generate_clicked:
        st.session_state.rec_results = None
        st.session_state.rec_data_loaded = False
        st.session_state.rec_entry_check = None
        st.session_state.rec_manual_trade_review = None
        st.session_state.rec_last_error = None
        st.session_state.rec_is_running = True
        st.session_state.rec_active_request_key = current_request_key
        progress_placeholder = st.empty()
        progress_callback = _make_progress_callback(progress_placeholder, strategy, sector, current_request_key)
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
            _clear_progress_snapshot(current_request_key)
            progress_placeholder.empty()

    if entry_check_clicked:
        st.session_state.rec_entry_check = service.check_entry_plan(st.session_state.rec_results)

    if st.session_state.rec_last_error:
        st.error(st.session_state.rec_last_error)

    if is_current_request_running:
        progress_placeholder = st.empty()
        _render_saved_progress(progress_placeholder, current_request_key, strategy, sector)
        st.info("当前策略正在生成 T+1 推荐计划，完成前不会展示旧推荐或旧诊断。")
        return
    if is_other_request_running:
        st.info(f"其他 T+1 计划正在生成：{running_label}。当前策略尚未开始生成，完成后可再点击生成。")

    if not st.session_state.rec_data_loaded:
        st.info("选择策略和板块后，点击“生成 T+1 推荐计划”开始收盘后/盘后计划分析。")

    manual_trade_history_rows = service.list_t1_plan_history(limit=5000)
    _render_manual_trade_form(
        st.session_state.rec_results,
        service,
        strategy,
        sector,
        manual_trade_history_rows,
    )
    _render_manual_trade_review(st.session_state.rec_manual_trade_review, service)

    if st.session_state.rec_results and _result_matches_request(st.session_state.rec_results, current_request_key):
        st.session_state.rec_results = service.ensure_t1_plan_display_profiles(st.session_state.rec_results)
        _render_t1_plan_meta(st.session_state.rec_results)
        st.caption("已读取 T+1 推荐计划缓存；未重新扫描股票池。只有点击“生成 T+1 推荐计划”才会重新运行策略。")
        _render_entry_check(st.session_state.rec_entry_check)
        _render_quality_diagnostics(st.session_state.rec_results.get("diagnostics"))
        display_recommendation_list(
            st.session_state.rec_results["recommended"],
            st.session_state.rec_results["title"],
            st.session_state.rec_results.get("diagnostics"),
        )
