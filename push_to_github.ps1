# PowerShell脚本 - 一键推送到GitHub
# 用法: 右键点击 → 使用PowerShell运行

$ErrorActionPreference = "Stop"

# 配置
$repoPath = "C:\Users\skip8\stock_analyzer"
$repoName = "1Skip/stock-analyzer"

# 从配置文件读取token（如果存在）
$tokenFile = "$repoPath\.github_token"
if (Test-Path $tokenFile) {
    $token = Get-Content $tokenFile -Raw
    $token = $token.Trim()
} else {
    # 首次运行，询问token
    $token = Read-Host "请输入GitHub Personal Access Token (首次使用需要输入，之后会自动保存)"
    $token = $token.Trim()
    # 保存到本地文件
    $token | Out-File $tokenFile -Encoding utf8
    Write-Host "Token已保存到本地，下次无需再次输入" -ForegroundColor Green
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    推送到 GitHub 脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查是否在正确的目录
Set-Location $repoPath

# 检查git是否安装
try {
    $gitVersion = git --version 2>$null
    if (-not $gitVersion) {
        Write-Host "错误: 未安装Git" -ForegroundColor Red
        Write-Host "请访问 https://git-scm.com/download/win 下载安装" -ForegroundColor Yellow
        Read-Host "按回车键退出"
        exit 1
    }
} catch {
    Write-Host "错误: 未安装Git" -ForegroundColor Red
    Write-Host "请访问 https://git-scm.com/download/win 下载安装" -ForegroundColor Yellow
    Read-Host "按回车键退出"
    exit 1
}

Write-Host "Git版本: $gitVersion" -ForegroundColor Green
Write-Host ""

# 检查远程仓库
$remoteUrl = git remote get-url origin 2>$null
if (-not $remoteUrl) {
    Write-Host "配置GitHub远程仓库..." -ForegroundColor Yellow
    git remote add origin "https://$token@github.com/$repoName.git"
} else {
    # 更新远程URL使用token
    git remote set-url origin "https://$token@github.com/$repoName.git"
}

# 获取当前分支
$branch = git branch --show-current
Write-Host "当前分支: $branch" -ForegroundColor Green
Write-Host ""

# 拉取最新更改
Write-Host "同步远程更改..." -ForegroundColor Yellow
try {
    git pull origin $branch --rebase 2>$null
    Write-Host "同步完成" -ForegroundColor Green
} catch {
    Write-Host "同步失败，但继续推送..." -ForegroundColor Yellow
}
Write-Host ""

# 添加所有更改
Write-Host "添加文件更改..." -ForegroundColor Yellow
git add -A

# 检查是否有更改
$status = git status --porcelain
if (-not $status) {
    Write-Host "没有需要提交的更改" -ForegroundColor Yellow
    Read-Host "按回车键退出"
    exit 0
}

# 显示更改的文件
Write-Host "更改的文件:" -ForegroundColor Cyan
git status --short
Write-Host ""

# 提交更改
$commitMessage = Read-Host "输入提交说明 (直接回车使用默认说明)"
if (-not $commitMessage) {
    $commitMessage = "Update: $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
}

git commit -m "$commitMessage"
Write-Host "提交完成" -ForegroundColor Green
Write-Host ""

# 推送到GitHub
Write-Host "推送到GitHub..." -ForegroundColor Yellow
try {
    git push origin $branch
    Write-Host "推送成功!" -ForegroundColor Green
    Write-Host ""
    Write-Host "GitHub仓库地址:" -ForegroundColor Cyan
    Write-Host "https://github.com/$repoName" -ForegroundColor Blue
} catch {
    Write-Host "推送失败: $_" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}

Write-Host ""
Read-Host "按回车键退出"
