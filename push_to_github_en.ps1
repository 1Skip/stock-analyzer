# PowerShell Script - Push to GitHub
# Usage: Right click -> Run with PowerShell

$ErrorActionPreference = "Stop"

# Configuration
$repoPath = "C:\Users\skip8\stock_analyzer"
$repoName = "1Skip/stock-analyzer"

# Read token from file if exists
$tokenFile = "$repoPath\.github_token"
if (Test-Path $tokenFile) {
    $token = Get-Content $tokenFile -Raw
    $token = $token.Trim()
} else {
    # First run, ask for token
    $token = Read-Host "Enter GitHub Personal Access Token (first time only, will be saved)"
    $token = $token.Trim()
    $token | Out-File $tokenFile -Encoding utf8
    Write-Host "Token saved locally" -ForegroundColor Green
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    Push to GitHub" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check directory
Set-Location $repoPath

# Check git installation
try {
    $gitVersion = git --version 2>$null
    if (-not $gitVersion) {
        Write-Host "Error: Git not installed" -ForegroundColor Red
        Write-Host "Download from https://git-scm.com/download/win" -ForegroundColor Yellow
        Read-Host "Press Enter to exit"
        exit 1
    }
} catch {
    Write-Host "Error: Git not installed" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Git version: $gitVersion" -ForegroundColor Green
Write-Host ""

# Check remote repository
$remoteUrl = git remote get-url origin 2>$null
if (-not $remoteUrl) {
    Write-Host "Configuring GitHub remote..." -ForegroundColor Yellow
    git remote add origin "https://$token@github.com/$repoName.git"
} else {
    git remote set-url origin "https://$token@github.com/$repoName.git"
}

# Get current branch
$branch = git branch --show-current
Write-Host "Current branch: $branch" -ForegroundColor Green
Write-Host ""

# Pull latest changes
Write-Host "Syncing remote changes..." -ForegroundColor Yellow
try {
    git pull origin $branch --rebase 2>$null
    Write-Host "Sync complete" -ForegroundColor Green
} catch {
    Write-Host "Sync failed, continuing..." -ForegroundColor Yellow
}
Write-Host ""

# Add all changes
Write-Host "Adding changes..." -ForegroundColor Yellow
git add -A

# Check if there are changes
$status = git status --porcelain
if (-not $status) {
    Write-Host "No changes to commit" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 0
}

# Show changed files
Write-Host "Changed files:" -ForegroundColor Cyan
git status --short
Write-Host ""

# Commit changes
$commitMessage = Read-Host "Enter commit message (or press Enter for default)"
if (-not $commitMessage) {
    $commitMessage = "Update: $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
}

git commit -m "$commitMessage"
Write-Host "Commit complete" -ForegroundColor Green
Write-Host ""

# Push to GitHub
Write-Host "Pushing to GitHub..." -ForegroundColor Yellow
try {
    git push origin $branch
    Write-Host "Push successful!" -ForegroundColor Green
    Write-Host ""
    Write-Host "GitHub repository:" -ForegroundColor Cyan
    Write-Host "https://github.com/$repoName" -ForegroundColor Blue
} catch {
    Write-Host "Push failed: $_" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Read-Host "Press Enter to exit"
