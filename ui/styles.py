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
        --color-primary: #55c7ff;
        --color-primary-strong: #17a8ff;
        --color-accent: #015697;
        --color-panel: rgba(13, 28, 42, 0.82);
        --color-panel-soft: rgba(9, 20, 34, 0.72);
        --color-border: rgba(85, 199, 255, 0.16);
        --color-rise: #ff5a52;
        --color-fall: #35e46f;
        --color-warning: #015697;
        --color-flat: #8fa2b8;
        --text-main: #eef5ff;
        --text-muted: #9fb0c4;
        --shadow-glow: 0 18px 55px rgba(0,0,0,0.36), 0 0 34px rgba(30,168,255,0.08);
    }

    /* ===== 全局字体 ===== */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
        font-size: var(--font-body);
        font-weight: 400;
        color: var(--text-main);
    }
    .stApp {
        background:
            radial-gradient(circle at 86% 10%, rgba(28, 83, 145, 0.26), transparent 34%),
            radial-gradient(circle at 10% 4%, rgba(85, 199, 255, 0.13), transparent 30%),
            radial-gradient(circle at 52% 58%, rgba(12, 81, 122, 0.18), transparent 42%),
            linear-gradient(180deg, #030611 0%, #07111f 44%, #061522 100%);
        color: var(--text-main);
    }
    .stApp::before {
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        background:
            linear-gradient(rgba(85,199,255,0.035) 1px, transparent 1px),
            linear-gradient(90deg, rgba(85,199,255,0.025) 1px, transparent 1px);
        background-size: 44px 44px;
        mask-image: linear-gradient(to bottom, rgba(0,0,0,0.9), transparent 72%);
        z-index: 0;
    }
    .stApp > header {
        background: rgba(3,6,17,0.70) !important;
        backdrop-filter: blur(16px);
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
        color: var(--text-main);
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
    .signal-badge.neutral { background: rgba(143,162,184,0.12); color: var(--text-muted); opacity: 0.82; }

    /* ===== 卡片 ===== */
    .stock-card {
        background: var(--color-panel);
        border: 1px solid var(--color-border);
        border-radius: 16px;
        padding: 1.25rem;
        margin: 0.6rem 0;
        box-shadow: var(--shadow-glow);
        transition: background 0.2s ease;
    }
    .stock-card:hover {
        background: rgba(15, 35, 52, 0.92);
        border-color: rgba(85,199,255,0.30);
    }

    /* ===== 自选股条目 ===== */
    .watchlist-item {
        background: rgba(11, 25, 39, 0.82);
        border: 1px solid rgba(85,199,255,0.10);
        border-radius: 14px;
        padding: var(--space-8);
        margin: var(--space-4) 0;
        box-shadow: 0 8px 22px rgba(0,0,0,0.18);
        transition: background 0.2s ease;
    }
    .watchlist-item:hover {
        background: rgba(16, 39, 58, 0.94);
    }

    /* ===== 按钮 ===== */
    .stButton button {
        border-radius: var(--space-12) !important;
        font-weight: 800;
        border: 1px solid rgba(85,199,255,0.18) !important;
        transition: all 0.15s ease;
        box-shadow: 0 10px 24px rgba(0,0,0,0.24);
    }
    .stButton button:hover {
        border-color: rgba(85,199,255,0.42) !important;
        box-shadow: 0 12px 30px rgba(23,168,255,0.18);
        transform: translateY(-1px);
    }
    .stButton button:active {
        transform: scale(0.97);
    }
    .stButton button[data-kind="primary"] {
        background: linear-gradient(135deg, #0174c6, var(--color-accent)) !important;
        border-color: rgba(1,86,151,0.72) !important;
        color: #ffffff !important;
        box-shadow: 0 12px 32px rgba(1,86,151,0.26), 0 0 18px rgba(1,86,151,0.18) !important;
    }
    .stButton button[data-kind="secondary"] {
        background: rgba(13, 28, 42, 0.78) !important;
        color: var(--text-main) !important;
    }

    /* ===== 侧边栏 ===== */
    [data-testid="stSidebar"] {
        background:
            radial-gradient(circle at 40% 0%, rgba(85,199,255,0.14), transparent 28%),
            linear-gradient(180deg, rgba(8,18,31,0.96), rgba(4,9,19,0.98)) !important;
        border-right: 1px solid rgba(85,199,255,0.12);
    }
    [data-testid="stSidebar"] .stRadio label {
        padding: 0.4rem 0.75rem;
        border-radius: 10px;
        transition: background 0.2s ease;
    }
    [data-testid="stSidebar"] .stRadio label:hover {
        background: rgba(85,199,255,0.08);
    }
    [data-testid="stSidebar"] hr {
        margin: 0.8rem 0;
        opacity: 0.2;
    }

    /* ===== Metric 指标卡片 ===== */
    [data-testid="stMetric"] {
        background: rgba(12, 26, 40, 0.80);
        border: 1px solid rgba(85,199,255,0.12);
        border-radius: 16px;
        padding: 0.75rem;
        box-shadow: 0 12px 32px rgba(0,0,0,0.22);
        transition: background 0.2s ease;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.75rem !important;
        font-weight: 600 !important;
        color: var(--text-main) !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 1rem !important;
        font-weight: 500 !important;
    }

    /* ===== Tab ===== */
    .stTabs [role="tab"] {
        font-weight: 500;
        border-radius: 10px;
        color: var(--text-muted) !important;
        transition: background 0.2s ease;
    }
    .stTabs [role="tab"]:hover {
        color: var(--text-main) !important;
        background: rgba(85,199,255,0.08);
    }
    .stTabs [role="tab"][aria-selected="true"] {
        color: #ffffff !important;
        background: transparent !important;
    }
    .stTabs [role="tab"][aria-selected="true"] p,
    .stTabs [role="tab"][aria-selected="true"] span {
        color: #ffffff !important;
    }
    .stTabs [data-baseweb="tab-highlight"] {
        background-color: #015697 !important;
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
        border: 1px solid rgba(85,199,255,0.13) !important;
        background: rgba(8, 20, 33, 0.62) !important;
    }

    /* ===== SelectBox / TextInput ===== */
    [data-testid="stTextInput"] input,
    [data-testid="stSelectbox"] div[role="combobox"],
    .stSelectbox [data-baseweb="select"] {
        border-radius: 10px !important;
        background: rgba(10, 23, 37, 0.92) !important;
        border-color: rgba(85,199,255,0.18) !important;
        color: var(--text-main) !important;
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
        border: 1px solid rgba(85,199,255,0.22) !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    [data-testid="stForm"] [data-testid="stTextInput"] input:focus {
        border-color: var(--color-primary) !important;
        box-shadow: 0 0 0 3px rgba(85,199,255,0.16), 0 0 28px rgba(85,199,255,0.12) !important;
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
        border: 1px solid rgba(85,199,255,0.20);
        background: linear-gradient(135deg, rgba(19, 52, 78, 0.78), rgba(8, 18, 31, 0.76));
        border-radius: 18px;
        padding: 18px 20px;
        margin: 18px 0 14px 0;
        box-shadow: var(--shadow-glow);
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
        background: rgba(85,199,255,0.12);
        margin: 16px 0 10px 0;
    }
    .analysis-loading-bar > div {
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, var(--color-primary), var(--color-accent));
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
        border: 1px solid rgba(85,199,255,0.16);
        background: rgba(9, 22, 36, 0.78);
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
        color: var(--text-muted);
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
        background: rgba(85,199,255,0.12);
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
        background: rgba(85,199,255,0.12);
        margin-top: 9px;
    }
    .hot-loading-bar > div {
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, var(--color-primary), var(--color-accent));
        transition: width 0.24s ease;
    }
    .status-loading-strip {
        border: 1px solid rgba(85,199,255,0.16);
        background: rgba(9, 22, 36, 0.78);
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
        color: var(--text-muted);
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
        background: rgba(85,199,255,0.12);
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
        background: rgba(85,199,255,0.12);
        margin-top: 9px;
    }
    .status-loading-bar > div {
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, var(--color-primary), var(--color-accent));
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
        border: 1px solid rgba(85,199,255,0.16);
        background: rgba(9, 22, 36, 0.76);
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
        background: rgba(9, 22, 36, 0.72);
        border: 1px solid rgba(85,199,255,0.12);
        color: var(--text-muted);
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
    .decision-hero {
        display: flex;
        gap: 18px;
        align-items: center;
        padding: 18px;
        margin: 8px 0 14px 0;
        border-radius: 22px;
        border: 1px solid rgba(85,199,255,0.18);
        background: linear-gradient(135deg, rgba(13, 34, 52, 0.88), rgba(7, 17, 31, 0.82));
        box-shadow: var(--shadow-glow);
    }
    .decision-hero.bullish {
        background: linear-gradient(135deg, rgba(255,90,82,0.16), rgba(8,18,31,0.84));
    }
    .decision-hero.bearish {
        background: linear-gradient(135deg, rgba(53,228,111,0.14), rgba(8,18,31,0.84));
    }
    .decision-hero.watch {
        background: linear-gradient(135deg, rgba(1,86,151,0.26), rgba(8,18,31,0.84));
    }
    .decision-score-ring {
        width: 112px;
        min-width: 112px;
        height: 112px;
        border-radius: 50%;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        background: rgba(3, 10, 19, 0.82);
        border: 8px solid var(--color-primary);
        box-shadow: inset 0 0 0 1px rgba(85,199,255,0.10), 0 10px 26px rgba(0,0,0,0.28);
    }
    .decision-score-ring.bullish { border-color: var(--color-rise); }
    .decision-score-ring.bearish { border-color: var(--color-fall); }
    .decision-score-ring.watch { border-color: var(--color-warning); }
    .decision-score-ring strong {
        font-size: 2.35rem;
        line-height: 1;
        letter-spacing: -0.05em;
    }
    .decision-score-ring span {
        font-size: 0.75rem;
        opacity: 0.55;
        margin-top: 2px;
    }
    .decision-hero-main {
        min-width: 0;
        flex: 1;
    }
    .decision-eyebrow {
        font-size: 0.72rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        opacity: 0.52;
        font-weight: 800;
        margin-bottom: 4px;
    }
    .decision-hero-title {
        font-size: 1.55rem;
        line-height: 1.2;
        font-weight: 850;
        letter-spacing: -0.04em;
        margin-bottom: 6px;
    }
    .decision-hero-summary {
        font-size: 0.92rem;
        opacity: 0.78;
        line-height: 1.55;
        margin-bottom: 12px;
    }
    .decision-chip-row {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
    }
    .decision-chip {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        padding: 5px 10px;
        font-size: 0.78rem;
        font-weight: 800;
        border: 1px solid rgba(85,199,255,0.14);
        background: rgba(10, 25, 39, 0.72);
    }
    .decision-chip.bullish {
        color: var(--color-rise);
        background: rgba(255,59,48,0.10);
        border-color: rgba(255,59,48,0.18);
    }
    .decision-chip.bearish {
        color: var(--color-fall);
        background: rgba(52,199,89,0.10);
        border-color: rgba(52,199,89,0.18);
    }
    .decision-chip.watch {
        color: var(--color-warning);
        background: rgba(1,86,151,0.22);
        border-color: rgba(1,86,151,0.42);
    }
    .decision-panel {
        border-radius: 18px;
        padding: 15px 16px;
        min-height: 150px;
        margin-bottom: 12px;
        border: 1px solid rgba(85,199,255,0.14);
        background: linear-gradient(145deg, rgba(13, 30, 45, 0.86), rgba(7, 17, 31, 0.76));
        backdrop-filter: blur(14px);
        box-shadow: var(--shadow-glow);
        overflow: hidden;
    }
    .decision-panel.compact {
        min-height: 0;
        padding: 12px 14px;
    }
    .decision-panel.bullish { border-left: 4px solid var(--color-rise); }
    .decision-panel.bearish { border-left: 4px solid var(--color-fall); }
    .decision-panel.watch { border-left: 4px solid var(--color-warning); }
    .decision-panel.neutral { border-left: 4px solid var(--color-primary); }
    .decision-panel-title {
        font-size: 0.80rem;
        font-weight: 850;
        opacity: 0.66;
        margin-bottom: 9px;
    }
    .decision-panel-body {
        font-size: 0.92rem;
        line-height: 1.55;
    }
    .decision-action {
        font-size: 1.05rem;
        font-weight: 850;
        line-height: 1.45;
        margin-bottom: 12px;
    }
    .decision-mini-note {
        margin-top: 9px;
        font-size: 0.78rem;
        opacity: 0.60;
    }
    .decision-meter {
        position: relative;
        height: 22px;
        border-radius: 999px;
        overflow: hidden;
        background: rgba(3, 10, 19, 0.70);
        border: 1px solid rgba(85,199,255,0.12);
    }
    .decision-meter-fill {
        height: 100%;
        min-width: 4px;
        border-radius: 999px;
        background: var(--color-primary);
    }
    .decision-meter-fill.bullish { background: var(--color-rise); }
    .decision-meter-fill.bearish { background: var(--color-fall); }
    .decision-meter-fill.watch { background: var(--color-warning); }
    .decision-meter span {
        position: absolute;
        inset: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.72rem;
        font-weight: 850;
    }
    .decision-level-row {
        display: grid;
        grid-template-columns: 64px 1fr auto;
        align-items: center;
        gap: 8px;
        padding: 6px 0;
        border-bottom: 1px solid rgba(128,128,128,0.08);
    }
    .decision-level-row:last-child {
        border-bottom: none;
    }
    .decision-level-row b {
        font-feature-settings: "tnum";
        font-variant-numeric: tabular-nums;
    }
    .decision-level-row span:last-child {
        font-size: 0.72rem;
        opacity: 0.48;
    }
    .trade-plan-action {
        font-size: 1.18rem;
        font-weight: 900;
        line-height: 1.35;
        margin-bottom: 12px;
        letter-spacing: -0.02em;
    }
    .trade-plan-hero {
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 4px 10px;
        align-items: center;
        padding: 12px 13px;
        margin-bottom: 10px;
        border-radius: 16px;
        background: linear-gradient(135deg, rgba(85,199,255,0.13), rgba(6,14,26,0.70));
        border: 1px solid rgba(85,199,255,0.20);
    }
    .trade-plan-hero span {
        grid-column: 1 / -1;
        font-size: 0.68rem;
        opacity: 0.58;
        font-weight: 850;
    }
    .trade-plan-hero strong {
        font-size: 1.28rem;
        font-weight: 950;
        letter-spacing: -0.03em;
    }
    .trade-plan-hero em {
        padding: 4px 10px;
        border-radius: 999px;
        background: rgba(1,86,151,0.22);
        color: var(--color-warning);
        font-size: 0.72rem;
        font-style: normal;
        font-weight: 900;
        white-space: nowrap;
    }
    .trade-plan-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 8px;
    }
    .trade-plan-row {
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: 3px;
        justify-content: center;
        min-height: 68px;
        padding: 9px 10px;
        border-radius: 14px;
        background: rgba(7, 18, 31, 0.70);
        border: 1px solid rgba(85,199,255,0.10);
    }
    .trade-plan-row:last-of-type {
        border-bottom: 1px solid rgba(85,199,255,0.10);
    }
    .trade-plan-row > span:first-child {
        font-size: 0.74rem;
        opacity: 0.58;
        font-weight: 750;
    }
    .trade-plan-row b {
        font-size: 0.90rem;
        font-weight: 850;
        word-break: break-word;
        line-height: 1.25;
    }
    .trade-plan-row > span:last-child {
        font-size: 0.66rem;
        opacity: 0.48;
        white-space: normal;
    }
    .defense-dashboard-layout {
        display: flex;
        flex-direction: column;
        gap: 12px;
    }
    .defense-top-row {
        display: grid;
        grid-template-columns: 0.9fr 1.6fr;
        gap: 12px;
        align-items: stretch;
    }
    .defense-overall {
        display: flex;
        gap: 12px;
        align-items: center;
        padding: 11px 12px;
        border-radius: 16px;
        background: rgba(7, 18, 31, 0.70);
        margin-bottom: 0;
        min-height: 92px;
    }
    .defense-overall strong {
        width: 54px;
        min-width: 54px;
        height: 54px;
        border-radius: 50%;
        display: inline-flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        font-size: 1.32rem;
        background: rgba(3, 10, 19, 0.84);
        border: 4px solid var(--color-primary);
        line-height: 1.05;
    }
    .defense-overall strong em {
        display: block;
        font-size: 0.54rem;
        font-style: normal;
        font-weight: 850;
        opacity: 0.58;
        margin-bottom: 2px;
    }
    .defense-overall.bullish strong { border-color: var(--color-rise); }
    .defense-overall.bearish strong { border-color: var(--color-fall); }
    .defense-overall.watch strong { border-color: var(--color-warning); }
    .defense-overall span {
        font-weight: 850;
        line-height: 1.35;
    }
    .signal-state-card {
        border-radius: 16px;
        padding: 12px;
        margin-bottom: 0;
        border: 1px solid rgba(85,199,255,0.12);
        background: linear-gradient(135deg, rgba(10, 26, 40, 0.76), rgba(6, 14, 26, 0.70));
    }
    .signal-state-card.bullish {
        background: linear-gradient(135deg, rgba(255,90,82,0.14), rgba(6,14,26,0.70));
        border-color: rgba(255,59,48,0.16);
    }
    .signal-state-card.bearish {
        background: linear-gradient(135deg, rgba(53,228,111,0.14), rgba(6,14,26,0.70));
        border-color: rgba(52,199,89,0.16);
    }
    .signal-state-card.watch {
        background: linear-gradient(135deg, rgba(1,86,151,0.24), rgba(6,14,26,0.70));
        border-color: rgba(1,86,151,0.38);
    }
    .signal-state-card div {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
    }
    .signal-state-card span {
        font-size: 0.72rem;
        opacity: 0.60;
        font-weight: 800;
    }
    .signal-state-card strong {
        font-size: 1.08rem;
        font-weight: 950;
    }
    .signal-state-card p {
        margin: 6px 0 8px;
        font-size: 0.78rem;
        opacity: 0.72;
    }
    .signal-state-card ul {
        margin: 0;
        padding-left: 18px;
        font-size: 0.70rem;
        opacity: 0.72;
        line-height: 1.45;
    }
    .defense-metric-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(150px, 1fr));
        gap: 10px;
        margin: 0;
    }
    .defense-metric {
        min-width: 0;
        padding: 10px;
        border-radius: 16px;
        background: linear-gradient(145deg, rgba(10, 25, 39, 0.84), rgba(5, 13, 24, 0.78));
        border: 1px solid rgba(85,199,255,0.12);
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.06);
    }
    .defense-metric.ok,
    .defense-metric.derived {
        border-color: rgba(85,199,255,0.28);
    }
    .defense-metric.source_failed {
        border-color: rgba(255,59,48,0.26);
        background: linear-gradient(145deg, rgba(255,90,82,0.12), rgba(5,13,24,0.78));
    }
    .defense-metric.source_empty,
    .defense-metric.insufficient {
        border-color: rgba(1,86,151,0.42);
        background: linear-gradient(145deg, rgba(1,86,151,0.18), rgba(5,13,24,0.78));
    }
    .defense-metric.missing {
        border-color: rgba(143,162,184,0.18);
    }
    .defense-metric-head {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        align-items: center;
    }
    .defense-metric span {
        font-size: 0.68rem;
        opacity: 0.58;
        font-weight: 800;
    }
    .defense-metric i {
        display: inline-flex;
        align-items: center;
        height: 18px;
        padding: 0 7px;
        border-radius: 999px;
        background: rgba(85,199,255,0.12);
        color: var(--color-primary);
        font-size: 0.58rem;
        font-style: normal;
        font-weight: 900;
        white-space: nowrap;
    }
    .defense-metric.source_failed i {
        background: rgba(255,59,48,0.12);
        color: var(--color-rise);
    }
    .defense-metric.source_empty i,
    .defense-metric.insufficient i {
        background: rgba(1,86,151,0.24);
        color: var(--color-warning);
    }
    .defense-metric.missing i {
        background: rgba(143,162,184,0.12);
        color: var(--color-flat);
    }
    .defense-metric strong {
        display: block;
        margin-top: 6px;
        font-size: 1.02rem;
        font-weight: 950;
        font-feature-settings: "tnum";
        font-variant-numeric: tabular-nums;
    }
    .defense-metric em {
        display: block;
        margin-top: 4px;
        font-size: 0.62rem;
        opacity: 0.60;
        line-height: 1.32;
        font-style: normal;
        min-height: 2.5em;
    }
    .defense-bottom-grid {
        display: grid;
        grid-template-columns: minmax(290px, 0.8fr) minmax(420px, 1.2fr);
        gap: 14px;
        align-items: start;
    }
    .defense-dimension-list {
        padding: 10px 12px;
        border-radius: 16px;
        background: rgba(7, 18, 31, 0.62);
        border: 1px solid rgba(85,199,255,0.10);
    }
    .defense-dimension {
        display: grid;
        grid-template-columns: 106px 1fr;
        gap: 8px;
        align-items: center;
        padding: 6px 0;
        border-bottom: 1px solid rgba(85,199,255,0.08);
    }
    .defense-dimension:last-of-type {
        border-bottom: none;
    }
    .defense-dimension b {
        display: block;
        font-size: 0.82rem;
    }
    .defense-dimension span {
        display: block;
        font-size: 0.64rem;
        opacity: 0.50;
        line-height: 1.35;
        margin-top: 2px;
    }
    .capital-trace-block {
        min-width: 0;
    }
    .capital-trace-title {
        margin: 0 0 6px;
        font-size: 0.78rem;
        font-weight: 900;
        opacity: 0.70;
    }
    .capital-trace-table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        overflow: hidden;
        border-radius: 14px;
        border: 1px solid rgba(85,199,255,0.10);
        font-size: 0.68rem;
    }
    .capital-trace-table th,
    .capital-trace-table td {
        padding: 8px 9px;
        text-align: left;
        border-bottom: 1px solid rgba(85,199,255,0.08);
        vertical-align: top;
    }
    .capital-trace-table th:nth-child(4),
    .capital-trace-table td:nth-child(4) {
        display: none;
    }
    .capital-trace-table th {
        background: rgba(85,199,255,0.08);
        font-weight: 900;
        opacity: 0.70;
    }
    .capital-trace-table td {
        background: rgba(7, 18, 31, 0.56);
        font-feature-settings: "tnum";
        font-variant-numeric: tabular-nums;
    }
    .capital-trace-table tr:last-child td {
        border-bottom: none;
    }
    .decision-list {
        list-style: none;
        padding: 0;
        margin: 0;
        display: flex;
        flex-direction: column;
        gap: 7px;
    }
    .decision-list li {
        display: flex;
        gap: 8px;
        align-items: flex-start;
        min-width: 0;
        word-break: break-word;
    }
    .decision-list-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 24px;
        height: 20px;
        border-radius: 999px;
        font-size: 0.68rem;
        font-weight: 850;
        color: var(--text-muted);
        background: rgba(143,162,184,0.12);
        border: 1px solid rgba(143,162,184,0.12);
    }
    .decision-list-icon.bullish {
        color: var(--color-rise);
        background: rgba(255,90,82,0.13);
        border-color: rgba(255,90,82,0.20);
    }
    .decision-list-icon.bearish {
        color: var(--color-fall);
        background: rgba(53,228,111,0.12);
        border-color: rgba(53,228,111,0.18);
    }
    .decision-list-icon.watch {
        color: var(--color-warning);
        background: rgba(1,86,151,0.22);
        border-color: rgba(1,86,151,0.42);
    }
    .agent-card-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        gap: 12px;
    }
    .agent-card {
        border-radius: 18px;
        padding: 14px;
        border: 1px solid rgba(85,199,255,0.14);
        background: linear-gradient(145deg, rgba(12, 28, 43, 0.86), rgba(5, 13, 24, 0.74));
        border-left: 4px solid var(--color-primary);
        box-shadow: 0 14px 34px rgba(0,0,0,0.24), inset 0 1px 0 rgba(255,255,255,0.04);
    }
    .agent-card.bullish {
        border-left-color: var(--color-rise);
        background: linear-gradient(145deg, rgba(49, 20, 25, 0.76), rgba(5, 13, 24, 0.74));
    }
    .agent-card.bearish {
        border-left-color: var(--color-fall);
        background: linear-gradient(145deg, rgba(15, 43, 31, 0.76), rgba(5, 13, 24, 0.74));
    }
    .agent-card-head {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        align-items: flex-start;
        margin-bottom: 10px;
    }
    .agent-name {
        font-weight: 850;
        line-height: 1.25;
    }
    .agent-summary {
        font-size: 0.76rem;
        color: var(--text-muted);
        line-height: 1.45;
        margin-top: 3px;
    }
    .agent-score-pill {
        min-width: 42px;
        text-align: center;
        border-radius: 999px;
        padding: 4px 8px;
        font-size: 0.78rem;
        font-weight: 850;
        color: var(--color-primary);
        background: rgba(85,199,255,0.12);
        border: 1px solid rgba(85,199,255,0.20);
    }
    .agent-score-pill.bullish {
        color: var(--color-rise);
        background: rgba(255,90,82,0.13);
        border-color: rgba(255,90,82,0.22);
    }
    .agent-score-pill.bearish {
        color: var(--color-fall);
        background: rgba(53,228,111,0.12);
        border-color: rgba(53,228,111,0.20);
    }
    .agent-meta-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 6px;
        margin-bottom: 10px;
        font-size: 0.74rem;
        opacity: 0.78;
    }
    .agent-meta-grid span {
        border-radius: 10px;
        padding: 6px 8px;
        background: rgba(85,199,255,0.07);
        border: 1px solid rgba(85,199,255,0.10);
    }
    .agent-detail-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: 9px;
        margin-top: 10px;
        font-size: 0.80rem;
    }

    /* ===== A股决策委员会状态卡片 ===== */
    .committee-status-card {
        margin: 14px 0 10px 0;
        padding: 14px;
        border-radius: 18px;
        border: 1px solid rgba(85,199,255,0.16);
        background:
            radial-gradient(circle at 10% 0%, rgba(85,199,255,0.16), transparent 34%),
            linear-gradient(145deg, rgba(12, 28, 43, 0.88), rgba(5, 13, 24, 0.78));
        box-shadow: 0 16px 40px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.04);
    }
    .committee-status-eyebrow {
        font-size: 0.66rem;
        font-weight: 850;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--color-primary);
        opacity: 0.90;
        margin-bottom: 2px;
    }
    .committee-status-title {
        font-size: 1rem;
        font-weight: 850;
        letter-spacing: -0.03em;
    }
    .committee-status-subtitle {
        font-size: 0.74rem;
        color: var(--text-muted);
        margin: 3px 0 10px 0;
    }
    .committee-stage-list {
        display: flex;
        flex-direction: column;
        gap: 6px;
    }
    .committee-stage-row {
        display: grid;
        grid-template-columns: 48px 1fr auto;
        align-items: center;
        gap: 6px;
        padding: 7px 8px;
        border-radius: 12px;
        background: rgba(7, 18, 31, 0.64);
        border: 1px solid rgba(85,199,255,0.10);
        font-size: 0.72rem;
    }
    .committee-stage-row span {
        font-weight: 850;
        color: var(--text-muted);
    }
    .committee-stage-row strong {
        font-weight: 760;
        min-width: 0;
    }
    .committee-stage-row em {
        border-radius: 999px;
        padding: 2px 6px;
        font-style: normal;
        font-size: 0.66rem;
        font-weight: 850;
        color: var(--color-primary);
        background: rgba(85,199,255,0.12);
        border: 1px solid rgba(85,199,255,0.18);
    }
    .committee-stage-row.done em {
        color: var(--color-rise);
        background: rgba(255,90,82,0.13);
        border-color: rgba(255,90,82,0.20);
    }
    .committee-stage-row.inactive em {
        color: var(--color-warning);
        background: rgba(1,86,151,0.22);
        border-color: rgba(1,86,151,0.42);
    }
    .committee-stage-row.active em {
        color: var(--color-rise);
        background: rgba(255,90,82,0.14);
        border-color: rgba(255,90,82,0.24);
    }
    .committee-status-grid {
        display: grid;
        grid-template-columns: 1fr;
        gap: 5px;
        margin-top: 10px;
        font-size: 0.72rem;
    }
    .committee-status-grid span {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        padding-top: 5px;
        border-top: 1px solid rgba(85,199,255,0.10);
        color: var(--text-muted);
    }
    .committee-status-grid b {
        font-weight: 850;
    }
    @media (max-width: 760px) {
        .decision-hero {
            align-items: flex-start;
            flex-direction: column;
        }
        .decision-score-ring {
            width: 96px;
            min-width: 96px;
            height: 96px;
        }
        .trade-plan-row {
            grid-template-columns: 1fr;
            gap: 3px;
        }
        .trade-plan-row > span:last-child {
            white-space: normal;
        }
        .defense-dimension {
            grid-template-columns: 1fr;
            gap: 5px;
        }
        .defense-metric-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }
        .capital-trace-table {
            display: block;
            overflow-x: auto;
            white-space: nowrap;
        }
        .agent-meta-grid {
            grid-template-columns: 1fr;
        }
    }
</style>
""".lstrip()
