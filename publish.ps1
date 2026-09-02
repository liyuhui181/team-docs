#Requires -Version 5.1
<#
  团队技术手册 · 国内加速版发布脚本
  ----------------------------------
  用清华 TUNA 镜像装 Git，纯 git 推送，无需 GitHub CLI（避免从 GitHub 下载慢）。
  在你自己的 PowerShell 里运行（不要在 TRAE 里运行，沙箱会拦截）。

  运行方式：打开 PowerShell，粘贴下面这一行回车：
  Set-ExecutionPolicy -Scope Process Bypass -Force; & "c:\Users\LIYUHUI\Desktop\ai\tech-docs\publish.ps1"

  流程：检查 Git（没装则给国内镜像链接让你装）→ 网页建空仓库 → 脚本提交推送
        （首次推送会弹浏览器登录授权）→ 网页开启 Pages → 拿到网址。
#>

$ErrorActionPreference = 'Continue'
$repo = 'team-docs'          # 仓库名，如被占用可改
$siteDir = $PSScriptRoot
$mirror = 'https://mirrors.tuna.tsinghua.edu.cn/github-release/git-for-windows/git/LatestRelease/'

Write-Host ''
Write-Host '【1/4】检查 Git 是否已安装...' -ForegroundColor Cyan
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Host ''
  Write-Host '未检测到 Git。请按下面步骤安装（国内镜像，下载很快）：' -ForegroundColor Yellow
  Write-Host "  1) 浏览器打开：$mirror"
  Write-Host '  2) 找到 Git-2.55.0.3-64-bit.exe（或目录里版本号最大的 64-bit.exe），点击下载'
  Write-Host '  3) 双击安装，一路 Next 保持默认（确保 "Git from the command line" 选项是选中的，默认即是）'
  Write-Host '  4) 装完后，关闭这个 PowerShell 窗口，重新打开一个新的，再运行本脚本'
  Write-Host ''
  exit 1
}
Write-Host "   已检测到 Git：$(git --version)" -ForegroundColor Green

Write-Host ''
Write-Host '【2/4】准备 GitHub 空仓库（网页操作，约 1 分钟）...' -ForegroundColor Cyan
$user = Read-Host '请输入你的 GitHub 用户名（小写，例如 zhangsan）'
if (-not $user) { Write-Host '用户名不能为空。' -ForegroundColor Red; exit 1 }
$user = $user.Trim()
Write-Host ''
Write-Host '现在去浏览器完成一件事（建一个空仓库）：' -ForegroundColor Yellow
Write-Host '  1) 打开 https://github.com/new'
Write-Host "  2) Repository name 填：$repo"
Write-Host '  3) 选 Public（公开，Pages 免费需要公开仓库）'
Write-Host '  4) 下方的 Add a README / Add .gitignore / Choose a license 三个都不要勾（保持空仓库）'
Write-Host '  5) 点绿色的 Create repository 按钮'
Write-Host ''
Write-Host '建好后回到这个窗口，按回车继续...'
[void](Read-Host)

Write-Host ''
Write-Host '【3/4】提交并推送到 GitHub（首次推送会弹浏览器让你登录授权）...' -ForegroundColor Cyan
Set-Location $siteDir
if (-not (Test-Path '.git')) { git init; git branch -M main }
git config user.name 'Team Docs' 2>$null
git config user.email 'team-docs@local' 2>$null
git add .
git commit -m ('update: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm')) 2>$null | Out-Null
$remotes = @(git remote 2>$null)
if ($remotes -contains 'origin') { git remote remove origin 2>$null | Out-Null }
git remote add origin "https://github.com/$user/$repo.git"
Write-Host '   正在推送（如弹出浏览器，请登录 GitHub 并点 Authorize 授权）...'
git push -u origin main 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host ''
  Write-Host '推送失败。常见原因：' -ForegroundColor Red
  Write-Host '  - 建仓库时勾了 README/.gitignore：删掉该仓库重建一个空仓库再运行本脚本'
  Write-Host '  - 用户名拼错：改本脚本顶部或重新运行输入正确用户名'
  Write-Host '  - 浏览器授权没完成：重新运行本脚本，完成浏览器授权'
  exit 1
}

Write-Host ''
Write-Host '【4/4】最后一步：在网页开启 GitHub Pages...' -ForegroundColor Cyan
Write-Host ''
Write-Host '去浏览器做最后一步：' -ForegroundColor Yellow
Write-Host "  1) 打开 https://github.com/$user/$repo/settings/pages"
  Write-Host '  2) Source 选 Deploy from a branch'
  Write-Host '  3) Branch 选 main，右边选 /(root)，点 Save'
  Write-Host '  4) 等 30~60 秒，页面顶部会显示你的网址'
Write-Host ''
Write-Host '========================================' -ForegroundColor Green
Write-Host '发布完成！你的网址（首次生效约需 1 分钟）：' -ForegroundColor Green
Write-Host "   https://$user.github.io/$repo/" -ForegroundColor Green
Write-Host '========================================' -ForegroundColor Green
Write-Host ''
Write-Host '说明：'
Write-Host '  · 站点和 downloads/ 里的文件都托管在 GitHub 云端，你的电脑关机不影响访问。'
Write-Host '  · 以后更新内容（改 index.html 或往 downloads 加文件）后，再运行一次本脚本即可一键推送。'
Write-Host ''
