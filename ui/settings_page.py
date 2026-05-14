"""Runtime settings and notification test page."""
from __future__ import annotations

import os

import streamlit as st

from config import FEISHU_WEBHOOK_URL, NOTIFY_CHANNELS, WECHAT_WEBHOOK_URL
from notification import send_push


def settings_page() -> None:
    st.markdown('<h1 class="main-header">配置与推送测试</h1>', unsafe_allow_html=True)
    st.caption("这里用于检查当前运行环境配置；持久配置仍建议写入系统环境变量或 GitHub Actions Secrets。")

    col_channels, col_feishu, col_wechat = st.columns(3)
    with col_channels:
        st.metric("通知通道", ", ".join(NOTIFY_CHANNELS) or "未开启")
    with col_feishu:
        st.metric("飞书 Webhook", "已配置" if FEISHU_WEBHOOK_URL else "未配置")
    with col_wechat:
        st.metric("企业微信 Webhook", "已配置" if WECHAT_WEBHOOK_URL else "未配置")

    st.divider()
    st.subheader("本机每日推送配置")
    tab_feishu, tab_wechat, tab_both = st.tabs(["飞书", "企业微信", "同时推送"])
    with tab_feishu:
        st.markdown(
            """
            1. 在飞书群里添加 **自定义机器人**，复制 Webhook。
            2. 本机执行下面命令后，重新打开终端或重启 Streamlit。
            3. 运行 `python main.py --schedule` 后，本机保持开机即可按 `SCHEDULE_TIME` 推送。
            """
        )
        st.code(
            'setx NOTIFY_CHANNELS "feishu"\n'
            'setx FEISHU_WEBHOOK_URL "你的飞书机器人Webhook"\n'
            'setx SCHEDULE_ENABLED "true"\n'
            'setx SCHEDULE_TIME "15:30"\n'
            'python main.py --schedule',
            language="powershell",
        )
    with tab_wechat:
        st.markdown(
            """
            1. 在企业微信群中点击 **群机器人 > 添加机器人**，复制 Webhook。
            2. 本机执行下面命令后，重新打开终端或重启 Streamlit。
            3. 企业微信通道名是 `wechat`，对应环境变量是 `WECHAT_WEBHOOK_URL`。
            """
        )
        st.code(
            'setx NOTIFY_CHANNELS "wechat"\n'
            'setx WECHAT_WEBHOOK_URL "你的企业微信机器人Webhook"\n'
            'setx SCHEDULE_ENABLED "true"\n'
            'setx SCHEDULE_TIME "15:30"\n'
            'python main.py --schedule',
            language="powershell",
        )
    with tab_both:
        st.markdown("如果你希望飞书和企业微信同时收到同一份推送，把两个 Webhook 都配置，并把通道写成逗号分隔。")
        st.code(
            'setx NOTIFY_CHANNELS "feishu,wechat"\n'
            'setx FEISHU_WEBHOOK_URL "你的飞书机器人Webhook"\n'
            'setx WECHAT_WEBHOOK_URL "你的企业微信机器人Webhook"\n'
            'setx SCHEDULE_ENABLED "true"\n'
            'setx SCHEDULE_TIME "15:30"\n'
            'python main.py --schedule',
            language="powershell",
        )
    st.info("如果使用 GitHub Actions 云端定时推送，企业微信同样可用：把仓库 Secret 配成 `WECHAT_WEBHOOK_URL`，并把工作流中的 `NOTIFY_CHANNELS` 改为 `wechat` 或 `feishu,wechat`。")

    st.divider()
    st.subheader("一键测试推送")
    st.caption("这里仅测试 Webhook 是否打通；交易计划卡片和风控防御看板会出现在正式的每日推送、自选股推送和推荐股推送中。")
    default_channels = [channel for channel in ["feishu", "wechat"] if channel in NOTIFY_CHANNELS]
    channel_labels = {"feishu": "飞书", "wechat": "企业微信"}
    channels = st.multiselect(
        "测试通道",
        ["feishu", "wechat"],
        default=default_channels or ["feishu"],
        format_func=lambda channel: channel_labels.get(channel, channel),
    )
    title = st.text_input("标题", value="股票分析系统推送测试")
    body = st.text_area("内容", value="如果你看到这条消息，说明 Webhook 推送已经打通。", height=120)

    if st.button("发送测试推送", type="primary"):
        missing = []
        if "feishu" in channels and not os.getenv("FEISHU_WEBHOOK_URL"):
            missing.append("FEISHU_WEBHOOK_URL")
        if "wechat" in channels and not os.getenv("WECHAT_WEBHOOK_URL"):
            missing.append("WECHAT_WEBHOOK_URL")
        if missing:
            st.error(f"缺少环境变量：{', '.join(missing)}")
            return
        results = send_push(title, body, channels=channels)
        if any(results.values()):
            st.success(f"推送完成：{results}")
        else:
            st.error(f"推送失败：{results}")
