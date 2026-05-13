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
    .select-row-button-spacer {
        height: 1.75rem;
        margin: 0;
        padding: 0;
    }
    .select-row-button-spacer + div [data-testid="stButton"] button,
    .select-row-button-spacer + div button {
        min-height: 2.55rem;
    }

    /* ===== 分析中占位卡片 ===== */
    .analysis-loading-card {
        border: 1px solid rgba(0,113,227,0.16);
        background: linear-gradient(135deg, rgba(0,113,227,0.10), rgba(0,113,227,0.03));
        border-radius: 18px;
        padding: 18px 20px;
        margin: 18px 0 14px 0;
        box-shadow: 0 12px 28px rgba(0,0,0,0.04);
    }
    .analysis-loading-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
    }
    .analysis-loading-kicker {
        font-size: 0.78rem;
        opacity: 0.62;
        font-weight: 700;
        margin-bottom: 4px;
    }
    .analysis-loading-title {
        font-size: 1.25rem;
        font-weight: 800;
        letter-spacing: -0.02em;
    }
    .analysis-loading-percent {
        font-size: 1.45rem;
        font-weight: 800;
        color: var(--color-primary);
    }
    .analysis-loading-bar {
        width: 100%;
        height: 8px;
        overflow: hidden;
        border-radius: 999px;
        background: rgba(0,113,227,0.12);
        margin: 16px 0 10px 0;
    }
    .analysis-loading-bar > div {
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, var(--color-primary), #5ac8fa);
        transition: width 0.24s ease;
    }
    .analysis-loading-step {
        font-weight: 700;
        margin-bottom: 4px;
    }
    .analysis-loading-hint {
        font-size: 0.84rem;
        opacity: 0.62;
    }
    .hot-loading-strip {
        border: 1px solid rgba(0,113,227,0.12);
        background: rgba(0,113,227,0.045);
        border-radius: 14px;
        padding: 10px 12px 9px 12px;
        margin: 8px 0 14px 0;
        box-shadow: 0 6px 18px rgba(0,0,0,0.025);
    }
    .hot-loading-main {
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .hot-loading-dot {
        width: 8px;
        height: 8px;
        flex: 0 0 8px;
        border-radius: 999px;
        background: var(--color-primary);
        box-shadow: 0 0 0 5px rgba(0,113,227,0.10);
        animation: hotPulse 1.35s ease-in-out infinite;
    }
    .hot-loading-copy {
        min-width: 0;
        flex: 1 1 auto;
    }
    .hot-loading-title {
        font-size: 0.92rem;
        font-weight: 700;
        line-height: 1.35;
    }
    .hot-loading-step {
        margin-top: 1px;
        color: rgba(49, 58, 70, 0.62);
        font-size: 0.8rem;
        line-height: 1.4;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .hot-loading-percent {
        flex: 0 0 auto;
        border-radius: 999px;
        padding: 3px 8px;
        background: rgba(0,113,227,0.10);
        color: var(--color-primary);
        font-size: 0.78rem;
        font-weight: 800;
        font-variant-numeric: tabular-nums;
    }
    .hot-loading-bar {
        width: 100%;
        height: 3px;
        overflow: hidden;
        border-radius: 999px;
        background: rgba(0,113,227,0.10);
        margin-top: 9px;
    }
    .hot-loading-bar > div {
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, var(--color-primary), #5ac8fa);
        transition: width 0.24s ease;
    }
    .status-loading-strip {
        border: 1px solid rgba(0,113,227,0.12);
        background: rgba(0,113,227,0.045);
        border-radius: 14px;
        padding: 10px 12px;
        margin: 8px 0 12px 0;
        box-shadow: 0 6px 18px rgba(0,0,0,0.025);
    }
    .status-loading-main {
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .status-loading-dot {
        width: 8px;
        height: 8px;
        flex: 0 0 8px;
        border-radius: 999px;
        background: var(--color-primary);
        box-shadow: 0 0 0 5px rgba(0,113,227,0.10);
        animation: hotPulse 1.35s ease-in-out infinite;
    }
    .status-loading-copy {
        min-width: 0;
        flex: 1 1 auto;
        color: rgba(49, 58, 70, 0.76);
        font-size: 0.88rem;
        font-weight: 700;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .status-loading-percent {
        flex: 0 0 auto;
        border-radius: 999px;
        padding: 3px 8px;
        background: rgba(0,113,227,0.10);
        color: var(--color-primary);
        font-size: 0.78rem;
        font-weight: 800;
        font-variant-numeric: tabular-nums;
    }
    .status-loading-bar {
        width: 100%;
        height: 3px;
        overflow: hidden;
        border-radius: 999px;
        background: rgba(0,113,227,0.10);
        margin-top: 9px;
    }
    .status-loading-bar > div {
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, var(--color-primary), #5ac8fa);
        transition: width 0.24s ease;
    }
    [data-testid="stSpinner"] {
        display: none !important;
    }
    @keyframes hotPulse {
        0%, 100% { transform: scale(1); opacity: 0.75; }
        50% { transform: scale(1.25); opacity: 1; }
    }
    .analysis-inline-note {
        margin: 18px 0 22px 0;
        padding: 13px 16px;
        border-radius: 14px;
        border: 1px solid rgba(0,113,227,0.14);
        background: rgba(0,113,227,0.08);
        color: inherit;
        font-size: 0.92rem;
        line-height: 1.5;
    }
    .chart-header-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin: 10px 0 6px 0;
        min-height: 28px;
    }
    .chart-header-row .chart-section-title {
        margin: 0 !important;
        flex: 0 0 auto;
    }
    .chart-value-row {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        justify-content: flex-end;
        margin: 0;
        min-height: 22px;
        pointer-events: none;
        flex: 1 1 auto;
    }
    .chart-value-chip {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 3px 8px;
        border-radius: 999px;
        background: rgba(128,128,128,0.06);
        border: 1px solid rgba(128,128,128,0.10);
        color: rgba(49, 58, 70, 0.78);
        font-size: 0.75rem;
        line-height: 1.3;
        white-space: nowrap;
    }
    .quick-match-row {
        margin: 6px 0 12px 0;
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

    /* ===== 决策仪表盘 ===== */
    .decision-card {
        border-left: 4px solid var(--color-primary);
        border-radius: 14px;
        padding: 14px 16px;
        min-height: 132px;
        box-shadow: 0 8px 22px rgba(0,0,0,0.04);
        border-top: 1px solid rgba(128,128,128,0.08);
        border-right: 1px solid rgba(128,128,128,0.08);
        border-bottom: 1px solid rgba(128,128,128,0.08);
    }
    .decision-card-title {
        font-size: 0.82rem;
        font-weight: 800;
        opacity: 0.68;
        margin-bottom: 8px;
    }
    .decision-card-body {
        font-size: 0.94rem;
        line-height: 1.55;
    }
    .decision-score {
        font-size: 2.45rem;
        line-height: 1;
        font-weight: 800;
        letter-spacing: -0.04em;
    }
</style>
""".lstrip()
