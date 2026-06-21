# 2026-06-21 更新记录

## 同花顺热门板块口径对齐

- 按用户要求，将项目热门板块口径改为优先使用同花顺热榜：热门板块拆分为概念板块、行业板块、指数板块，字段包含排名、板块、涨跌幅、热度、热度排名变化、代码、类别、数据源。
- 新增同花顺热门指数板块入口；行业/概念热榜优先走同花顺 App 热度接口，失败时再回退问财、东方财富、新浪和缓存，失败或缓存会保留真实数据源标记。
- 新增板块统计入口，支持全部、行业、概念三类；板块统计会按同花顺官方行业/概念名单过滤到 App 同层级，避免把钨、稀土、昨日换手前十等细分或风格项混入行业/全部。
- 短线推荐内部热门板块列表改为概念和行业交错合并，避免行业榜先占满导致 PCB、存储芯片、CPO 等概念热榜被挤出；因此短线「全部」和苹果/特斯拉的热门板块辅助评分会优先参考同花顺热度榜。
- 涨跌排行页新增「热门板块」区域（概念板块/行业板块/指数板块）和「板块统计」区域（全部/行业/概念），用于和同花顺 App 口径核对。

## 验证

- `py_compile stock_recommendation.py recommendation_modules/board_rankings.py ui/hot_stocks_page.py tests/test_board_rankings.py tests/test_stock_recommendation.py` 通过。
- `pytest tests\test_board_rankings.py tests\test_stock_recommendation.py::TestGetHotSectorsCN tests\test_stock_recommendation.py::TestGetHotConceptsCN tests\test_stock_recommendation.py::TestGetHotIndicesCN tests\test_stock_recommendation.py::TestBoardStatisticsCN -q` -> `31 passed`。
- 真实接口验证通过：热门概念返回存储芯片、PCB概念、共封装光学(CPO)等；热门行业返回半导体、电力、小金属等；热门指数返回人工智能、半导体材料设备、中证医疗等。
- 板块统计真实验证通过：全部前排返回非金属材料、牙科医疗、科创次新股、培育钻石等；行业前排返回非金属材料、金属新材料、半导体、小金属等；概念前排返回牙科医疗、科创次新股、培育钻石、稀土永磁等。
- `ui.hot_stocks_page.fetch_hot_stocks("CN")` 真实运行返回：个股涨幅榜 10、个股跌幅榜 10、热门概念 20、热门行业 20、热门指数 20、板块统计全部 30、行业 21、概念 30。

## 短线推荐「全部」暂无修复

- 真实排查确认：短线「全部」热榜接口能返回，但同花顺板块详情页成分股当前返回 403，东方财富成分股源在本机代理环境下也会失败，导致热门板块到个股候选池一度变成 0。
- 修复：短线「全部」保留同花顺热榜优先；板块成分股源失败时，用同花顺真实全市场涨幅榜多页结果作为兜底候选，并继续按成交量、MACD、RSI、KDJ、BOLL、二板以上、回调天数、回调幅度、放量反包/涨停板过滤；缺失或失败不造数据。
- 修复：短线诊断透传到推荐服务和页面，暂无时显示热门板块数、候选池、已分析、技术通过、形态通过、主要卡点，不再只显示笼统“数据获取失败”。
- 修复：短线 T+1 结果增加 `selection_data_version=short_term_hot_board_constituents_v2`，旧空缓存和旧 session 结果不会继续自动展示。
- 修复：本机代理污染 AKShare/腾讯/东财请求的问题，相关基础资料和热榜请求在关键路径上临时禁用系统代理读取。
- 真实验证：短线「全部」本轮返回 2 只（爱迪特、鑫宏业），诊断为候选池 8、技术通过 4、形态通过 2；短线「苹果概念」返回 5 只；短线「特斯拉概念」返回 5 只。
- 回归验证：`pytest tests\test_recommendation_service.py tests\test_stock_recommendation.py::TestGetShortTermRecommendations tests\test_data_services.py tests\test_ui_enhancements.py -q` -> `206 passed`。

## 短线「全部」主板边界修正

- 按用户确认，短线「全部」只能推荐沪深主板，不包含创业板、科创板、北交所；此前真实涨幅榜兜底误用了沪深主板 + 创业板的通用推荐池，导致出现 300/301 开头股票。
- 修复：短线「全部」的热门板块成分股候选和真实涨幅榜兜底候选均改回 `_is_main_board`，只允许 600/601/603/605/000/001/002/003 开头；苹果概念/特斯拉概念仍按原专题池逻辑。
- 真实验证：短线「全部」本轮返回 0 只，`non_main=[]`，说明不再混入创业板；暂无由主板候选不足/硬条件过滤导致。
- 回归验证：`pytest tests\test_stock_recommendation.py::TestGetShortTermRecommendations tests\test_recommendation_service.py -q` -> `41 passed`。

## 板块统计同花顺口径闭合修复

- 用户截图复核发现涨跌排行页「板块统计」仍混入钨、稀土、研究和试验发展指数等非同花顺行业/概念同层级项目。
- 根因：AKShare 的同花顺行业/概念名称接口当前解析失败时，板块统计仍会继续放行问财泛化返回结果；同时旧 `board_statistics_全部/行业/概念` 缓存和 Streamlit session 可能继续展示旧脏数据。
- 修复：板块统计缓存升级为 `board_statistics_ths_filtered_v2_*`，不再读取旧未过滤缓存；行业/概念必须先拿到同花顺官方名单或已缓存的 `ths_board_code_map` 名称表才能过滤；官方名单不可用时停止使用问财泛化结果，不再把错层级数据标成同花顺板块统计。
- 修复：涨跌排行页新增 `HOT_STOCKS_DATA_VERSION`，代码更新后自动失效旧 `st.session_state.hot_data`，避免页面继续显示旧板块统计结果。
- 真实验证：`ui.hot_stocks_page.fetch_hot_stocks("CN")` 返回板块统计全部 30、行业 21、概念 30；行业前排为非金属材料、金属新材料、半导体、小金属等；概念前排为牙科医疗、科创次新股、培育钻石、稀土永磁、共封装光学(CPO)等。
- 回归验证：`pytest tests\test_board_rankings.py tests\test_stock_recommendation.py::TestBoardStatisticsCN tests\test_stock_recommendation.py::TestGetHotSectorsCN tests\test_stock_recommendation.py::TestGetHotConceptsCN tests\test_stock_recommendation.py::TestGetHotIndicesCN tests\test_ui_enhancements.py -q` -> `137 passed`。
