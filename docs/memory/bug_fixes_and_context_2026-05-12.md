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

## 测试结果

- `py_compile` 通过。
- 全量测试：`533 passed, 22 warnings`。
- `git diff --check` 通过。

## 注意事项

- `test_ime_search.py` 是临时 Streamlit 对比页面，当前未纳入正式提交。
- 旧 Streamlit 进程可能持有旧代码和旧 cache，验证搜索修复前应重启 `localhost:8501` 服务。
