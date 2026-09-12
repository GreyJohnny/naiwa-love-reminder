# 奶蛙的爱意提醒物语 · Windows 打包脚本
#
# 用 PyInstaller 打成免安装的 exe：产物在 dist\NaiwaReminder\，整个文件夹拷到哪都能跑。
#
# 用法：右键"使用 PowerShell 运行"，或在终端里
#       powershell -ExecutionPolicy Bypass -File build.ps1
#
# 注意：这个文件必须存成 UTF-8 with BOM，否则 Windows PowerShell 5.1 会按 GBK 读，
#       中文会乱码甚至报语法错误。

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

Write-Host "[1/4] 检查 PyInstaller ..."
& $python -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "      没装，正在安装 ..."
    & $python -m pip install pyinstaller
}

Write-Host "[2/4] 清理旧产物 ..."
Remove-Item -Recurse -Force "$PSScriptRoot\build" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$PSScriptRoot\dist" -ErrorAction SilentlyContinue

Write-Host "[3/4] 打包中（第一次会比较慢）..."
& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name NaiwaReminder `
    --icon "assets\naiwa.ico" `
    --add-data "assets;assets" `
    "app\naiwa_app.py"

if ($LASTEXITCODE -ne 0) {
    Write-Host "打包失败，把上面的报错发我看一下。"
    exit 1
}

Write-Host "[4/4] 收拾 PyInstaller 从 PATH 上顺来的假 ICU ..."
# 本机 PATH 里有 Codex 运行时自带的 poppler 依赖，其中的 icuuc.dll 是只导出 C++ 符号的
# ICU 78，而 Qt6Core.dll 要找的 ucnv_open 等 C API 它一个都没有 —— 结果就是双击 exe 报
# "DLL load failed while importing QtCore: 找不到指定的程序"。
# 删掉它（以及配套的 icudt78.dll），让 Qt 去用 Windows 自带的系统 ICU（Win10 1703+ 都有）。
$runtimeDir = Join-Path $PSScriptRoot "dist\NaiwaReminder\_internal"
foreach ($name in @("icuuc.dll", "icuin.dll", "icudt78.dll")) {
    $target = Join-Path $runtimeDir $name
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Force
        Write-Host "      已移除不兼容的 $name（改用系统 ICU）"
    }
}

Write-Host ""
Write-Host "搞定！产物：dist\NaiwaReminder\NaiwaReminder.exe"
Write-Host "想开机自启的话：Win+R 输入 shell:startup，把 exe 的快捷方式丢进去。"
