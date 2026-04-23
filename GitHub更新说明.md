# GitHub 更新说明

## 方法一：一键推送（推荐）

### 前提条件
需要安装 Git：
1. 访问 https://git-scm.com/download/win
2. 下载并安装 Git（全部默认选项即可）

### 使用步骤

1. **修改代码后**，双击运行：
   ```
   一键推送到GitHub.bat
   ```

2. **输入提交说明**（或直接回车使用默认说明）

3. **等待完成**，会自动推送到GitHub

### 优点
- 一键完成，自动处理所有步骤
- 自动同步远程更改
- 自动显示更改的文件

---

## 方法二：手动网页更新（备用）

如果一键推送失败，使用此方法：

1. 打开 https://github.com/1Skip/stock-analyzer
2. 点击要修改的文件
3. 点击右上角的铅笔图标（Edit）
4. 修改代码
5. 滚动到底部，点击 "Commit changes"

---

## 更新后自动部署

推送到GitHub后：
1. Streamlit Cloud 会自动重新部署（约1-2分钟）
2. 刷新网页即可看到更新

强制刷新方法：
- Windows: `Ctrl + F5`
- Mac: `Cmd + Shift + R`

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `一键推送到GitHub.bat` | 一键推送脚本入口 |
| `push_to_github.ps1` | PowerShell推送脚本 |
| `GitHub更新说明.md` | 本说明文件 |

---

## 常见问题

### Q: 提示 "未安装Git"
A: 访问 https://git-scm.com/download/win 下载安装Git

### Q: 推送失败
A: 可能是网络问题，重试几次或使用方法二手动更新

### Q: 如何查看是否推送成功
A: 访问 https://github.com/1Skip/stock-analyzer 查看最新提交时间
