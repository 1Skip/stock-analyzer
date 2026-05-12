"""CSS 样式定义 — Apple × Tesla 设计体系

8px 间距梯度 / 四级字体层级 / 完整色板 / 亮暗双主题兼容
"""

CUSTOM_CSS = """
<style>
    /* ===== 设计变量 ===== */
    :root {
        --space-4: 4px;
        --space-8: 8px;
        --space-12: 12px;
        --space-16: 16px;
        --space-24: 24px;
        --space-32: 32px;
        --space-48: 48px;
        --font-title: 1.5rem;
        --font-section: 1.1rem;
        --font-body: 0.9rem;
        --font-caption: 0.75rem;
        --color-primary: #0071e3;
        --color-rise: #ff3b30;
        --color-fall: #34c759;
        --color-warning: #ff9500;
        --color-flat: #8e8e93;
    }

    /* ===== 全局字体 ===== */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
        font-size: var(--font-body);
        font-weight: 400;
    }

    /* ===== 等宽数字 ===== */
    [data-testid="stMetricValue"], [data-testid="stDataFrame"] td {
        font-feature-settings: "tnum";
        font-variant-numeric: tabular-nums;
    }

    /* ===== 页面标题 ===== */
    .main-header {
        font-size: var(--font-title);
        font-weight: 600;
        letter-spacing: -0.02em;
        color: inherit;
        margin-bottom: var(--space-24);
    }

    /* ===== 信号徽章 ===== */
    .signal-badge {
        display: inline-block;
        padding: var(--space-4) var(--space-12);
        border-radius: 20px;
        font-size: var(--font-caption);
        font-weight: 500;
        margin: 0 2px;
    }
    .signal-badge.buy  { background: rgba(229,57,53,0.08); color: var(--color-rise); }
    .signal-badge.sell { background: rgba(46,125,50,0.08); color: var(--color-fall); }
    .signal-badge.neutral { background: rgba(128,128,128,0.06); color: inherit; opacity: 0.5; }

    /* ===== 卡片 ===== */
    .stock-card {
        background: rgba(128, 128, 128, 0.03);
        border-radius: 12px;
        padding: 1.25rem;
        margin: 0.6rem 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        transition: background 0.2s ease;
    }
    .stock-card:hover {
        background: rgba(128, 128, 128, 0.06);
    }

    /* ===== 自选股条目 ===== */
    .watchlist-item {
        background: rgba(128, 128, 128, 0.03);
        border-radius: var(--space-8);
        padding: var(--space-8);
        margin: var(--space-4) 0;
        box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        transition: background 0.2s ease;
    }
    .watchlist-item:hover {
        background: rgba(128, 128, 128, 0.06);
    }

    /* ===== 按钮 ===== */
    .stButton button {
        border-radius: var(--space-12) !important;
        font-weight: 500;
        border: none;
        transition: all 0.15s ease;
    }
    .stButton button:active {
        transform: scale(0.97);
    }
    .stButton button[data-kind="primary"] {
        background-color: var(--color-primary);
        color: #fff;
    }
    .stButton button[data-kind="secondary"] {
        background-color: rgba(128, 128, 128, 0.08);
        color: inherit;
    }

    /* ===== 侧边栏 ===== */
    [data-testid="stSidebar"] {
        background-color: rgba(128, 128, 128, 0.02);
    }
    [data-testid="stSidebar"] .stRadio label {
        padding: 0.4rem 0.75rem;
        border-radius: 10px;
        transition: background 0.2s ease;
    }
    [data-testid="stSidebar"] hr {
        margin: 0.8rem 0;
        opacity: 0.2;
    }

    /* ===== Metric 指标卡片 ===== */
    [data-testid="stMetric"] {
        background: rgba(128, 128, 128, 0.03);
        border-radius: var(--space-12);
        padding: 0.75rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        transition: background 0.2s ease;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.75rem !important;
        font-weight: 600 !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 1rem !important;
        font-weight: 500 !important;
    }

    /* ===== Tab ===== */
    .stTabs [role="tab"] {
        font-weight: 500;
        border-radius: 10px;
        transition: background 0.2s ease;
    }

    /* ===== DataFrame ===== */
    [data-testid="stDataFrame"] {
        border-radius: var(--space-12);
        overflow: hidden;
    }
    [data-testid="stDataFrame"] table {
        border-radius: var(--space-12);
    }
    [data-testid="stDataFrame"] th {
        font-weight: 500;
        font-size: var(--font-caption);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        opacity: 0.6;
    }

    /* ===== Expander ===== */
    [data-testid="stExpander"] {
        border-radius: var(--space-12);
        border: none !important;
    }

    /* ===== SelectBox / TextInput ===== */
    [data-testid="stTextInput"] input,
    [data-testid="stSelectbox"] div[role="combobox"],
    .stSelectbox [data-baseweb="select"] {
        border-radius: 10px !important;
    }

    /* ===== 搜索区域 ===== */
    [data-testid="stForm"] {
        border: none !important;
        padding: 0 !important;
        margin-bottom: var(--space-8) !important;
    }

    /* 搜索输入框增大字号 */
    [data-testid="stForm"] [data-testid="stTextInput"] input {
        font-size: var(--font-section) !important;
        padding: 0.7rem 0.9rem !important;
        border: 1px solid rgba(128,128,128,0.2) !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    [data-testid="stForm"] [data-testid="stTextInput"] input:focus {
        border-color: var(--color-primary) !important;
        box-shadow: 0 0 0 3px rgba(0,113,227,0.15) !important;
    }

    /* 紧凑型 selectbox（无标签模式） */
    .compact-select [data-baseweb="select"] {
        font-size: var(--font-caption) !important;
    }

    /* ===== Divider ===== */
    hr {
        opacity: 0.2;
        margin: var(--space-24) 0;
    }

    /* ===== 图表区块小标题 ===== */
    .chart-section-title {
        font-size: var(--font-caption);
        font-weight: 500;
        opacity: 0.45;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin: 20px 0 6px 0;
    }
</style>
""".lstrip()
