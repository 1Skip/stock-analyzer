---
name: bug fixes and context 2026-05-12
description: 运行缓存迁移、全量A股名称索引、搜索性能优化、API安全提示与测试验证
type: project
---

# 2026-05-12 更新记录

## 主要修复

### 1. A股中文名称搜索改为全量索引

**问题**：股票代码可以查询全市场，但中文名称搜索只依赖 `stock_names.py` 的静态表和旧主板缓存，覆盖不完整，导致 `大唐电信`、`报喜鸟` 等名称搜索失败。

**修复**：
- 在 `data_fetcher.py` 新增全量 A 股名称索引，使用 AKShare `stock_info_a_code_name()` 获取 5515+ 只 A 股代码和名称。
- 名称索引缓存到 `.cache/stock_name_index.json`，24 小时内复用。
- 名称匹配前做 NFKC 规范化、去空格、统一大小写，兼容 `万  科Ａ` / `万科A` 等差异。
- `resolve_stock_input()` 和代码反查名称均使用全量索引。
- 保留静态表、主板缓存和全市场行情快照作为 fallback。

**验证**：
- `报喜鸟 -> ('002154', '报喜鸟')`，约 0.006 秒。
- `002154 -> ('002154', '报喜鸟')`。
- `大唐电信 -> ('600198', '大唐电信')`。
- `万科A -> ('000002', '万科A')`。

### 2. 个股分析查询性能优化

**问题**：搜索后页面串行获取股票信息、K线、实时行情、分时数据，辅助数据会拖慢主体图表渲染。

**修复**：
- `ui/analyze_page.py` 改为并行发起 K线、股票信息、实时行情、分时数据请求。
- 页面优先等待 K线主数据，股票信息/实时行情/分时数据最多短暂等待，未返回则不阻塞主体渲染。
- 中文名称解析加入 Streamlit 缓存，并增加缓存版本号，避免旧的“未找到”结果残留。

**验证**：
- 本地模拟慢辅助请求各 3 秒时，主流程约 0.61 秒继续执行。

### 3. 运行缓存目录迁移

**修复**：
- 新增 `RUNTIME_CACHE_DIR`，默认 `.cache/`。
- 离线行情缓存迁到 `.cache/stock_cache.json`。
- 主板股票池缓存迁到 `.cache/main_board_cache.json`。
- 兼容读取旧根目录 `.stock_cache.json` / `.main_board_cache.json`。
- `.gitignore` 忽略 `.cache/`。

### 4. 日志与安全提示

**修复**：
- 关键缓存/数据源/API 异常从静默吞掉改为 `logger.warning(..., exc_info=True)`。
- FastAPI 在非本地监听且未设置 `API_AUTH_KEY` 时输出 warning。
- 侧边栏自选股缓存 TTL 收敛到 `config.py`。

### 5. 依赖与文档

**修复**：
- `requirements.txt` 补充 `beautifulsoup4>=4.12`。
- README 更新全量名称搜索、缓存配置、测试数量。
- CLAUDE.md 更新架构约定、常见问题、测试数量。

### 6. 数据层按 `a-stock-data` 思路分层

**背景**：用户希望把 `simonlin1212/a-stock-data` 的架构思路用到本项目里，并且不要再出现“报一只股票补一只”的零散修复。

**落地**：
- 新增 `data/` 包，按 provider / service / cache / health / model 分层。
- `data/providers/akshare_provider.py` 封装 AKShare 个股基础资料接口，并用腾讯行情补充 PE/PB/换手率。
- `data/services/fundamental_service.py` 提供 `get_stock_profile(symbol, market)` 业务接口。
- `data/cache.py` 统一 JSON 文件缓存，基础资料缓存到 `.cache/fundamentals.json`。
- `data/models.py` 新增 `StockProfile` 标准模型，避免 UI 直接依赖原始接口字段。
- `ui/cached_data.py` 新增 `get_cached_stock_profile()`，`ui/analyze_page.py` 并行获取基础资料，避免阻塞 K线主流程。
- 个股分析页新增“基础资料 / 估值”折叠区，展示行业、上市日期、市值、股本、PE/PB、换手率。

**验证**：
- `tests/test_data_services.py` 覆盖 provider 标准化、腾讯估值补充、健康状态、service 缓存。
- 聚焦测试：`22 passed`。

### 7. 新股短历史提示文案优化

**问题**：新股/次新股（如 `301513 尚水智能`）上市时间短，实际只有十几个交易日数据，但页面显示“数据不足，部分指标可能无法计算”，用户容易误以为搜索或行情接口出错。

**修复**：
- `ui/analyze_page.py` 新增 `_build_short_history_notice()`，把短历史情况解释为新股/次新股或数据源只返回上市后行情。
- 将原 `st.warning()` 改为 `st.info()`，并提示长周期指标（MA20/MA60、RSI24、BOLL）暂不完整，建议优先参考分时图、价格走势和短线指标。
- 提示挪到股票名称解析之后，文案显示 `代码 + 名称`，不再像异常告警。

**验证**：
- `tests/test_ui_utils.py` 新增短历史提示测试。
- 聚焦测试：`20 passed`。

### 8. 阶段 2：行情服务接缝迁移

**目标**：先把 UI 对 `data_fetcher.py` 的行情直连收敛到分层服务，为后续拆新浪、腾讯、AKShare 独立 provider 做准备。

**落地**：
- 新增 `data/providers/legacy_quote_provider.py`，把现有 `StockDataFetcher` 包成 provider 适配层。
- 新增 `data/services/quote_service.py`，统一提供 K线、实时行情、分时、批量报价、股票名称、大盘指数和数据源切换入口。
- `ui/cached_data.py` 的股票数据/实时行情/分时缓存改走 `QuoteDataService`。
- `ui/compare_page.py`、`ui/recommend_page.py`、`ui/sidebar.py` 改走 `quote_service`，页面层不再直接调用行情 fetcher 方法。
- `ui/analyze_page.py` 移除未使用的 `fetcher` 导入，继续通过缓存函数访问行情服务。

**验证**：
- `tests/test_data_services.py` 新增 `QuoteDataService` 委托、代码规范化、非 A 股分时拦截、批量过滤、批量 K 线入口测试。
- 聚焦测试：`58 passed`。

### 9. 阶段 3：扩展信息服务

**目标**：按 `a-stock-data` 的多接口思路，为个股页补充基本面/资金面/消息面，但不影响技术分析主流程速度。

**落地**：
- 新增 `data/providers/akshare_info_provider.py`，封装 AKShare 财务摘要、资金流、个股新闻接口。
- 新增 `data/services/info_service.py`，提供 `StockInfoService.get_stock_extended_info(symbol, market)`。
- 新增 `CACHE_TTL_STOCK_EXTENDED_INFO=1800`，扩展信息缓存到 `.cache/stock_extended_info.json`。
- `ui/cached_data.py` 新增 `get_cached_stock_extended_info()`。
- `ui/analyze_page.py` 新增“财务 / 资金 / 新闻”折叠区，展示最新财报期的营业收入/归母净利润/经营现金流、主力资金净流入/占比/近5日净流入、相关新闻。
- 扩展信息最多短暂等待，失败返回空结构，不阻塞 K线、分时图和技术指标。

**验证**：
- `tests/test_data_services.py` 覆盖财务摘要规范化、资金流规范化、扩展信息缓存和非 A 股忽略。
- 聚焦测试：`64 passed`。

### 10. 阶段 4：统一运行治理

**落地**：
- 新增 `data/runtime.py`，统一第三方接口超时包装 `run_with_timeout()` 和非关键数据源安全调用 `safe_call()`。
- `AkShareProvider` 与 `AkShareInfoProvider` 复用统一超时包装，避免各 provider 重复写线程超时代码。

**验证**：
- `tests/test_data_services.py` 覆盖 `safe_call()` 成功和异常默认值。

## 测试结果

- `py_compile` 通过。
- 全量测试：`542 passed, 22 warnings`。
- `git diff --check` 通过。

## 注意事项

- `test_ime_search.py` 是临时 Streamlit 对比页面，当前未纳入正式提交。
- 旧 Streamlit 进程可能持有旧代码和旧 cache，验证搜索修复前应重启 `localhost:8501` 服务。
