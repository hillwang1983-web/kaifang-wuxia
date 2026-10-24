# 跑山寺 Godot 工程的无界面测试。Godot 路径：先看环境变量 GODOT，再在 PATH 里找 Godot_v4*_console.exe。
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$godot = $env:GODOT
if (-not $godot) {
  $hit = Get-Command 'Godot_v4*_console.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $hit) {
    $hit = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\GodotEngine.GodotEngine*" -Recurse -Filter 'Godot_v4*_console.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
  }
  if (-not $hit) { throw '没找到 Godot 4：先 winget install GodotEngine.GodotEngine，或设置环境变量 GODOT' }
  $godot = if ($hit.Source) { $hit.Source } else { $hit.FullName }
}
$project = Split-Path -Parent $PSScriptRoot
& $godot --headless --path $project --import | Out-Null
& $godot --headless --path $project --script res://tests/run_tests.gd
$unit = $LASTEXITCODE
# 冒烟：AI 代玩整段山门（四倍速），必须打到结算、且没有脚本报错
$out = [IO.Path]::GetTempFileName()
$err = [IO.Path]::GetTempFileName()
Start-Process -FilePath $godot -ArgumentList @('--headless', '--path', "`"$project`"", '--', 'auto', 'quit') `
  -RedirectStandardOutput $out -RedirectStandardError $err -Wait -NoNewWindow
$log = (Get-Content $out -Raw -Encoding UTF8) + (Get-Content $err -Raw -Encoding UTF8)
Remove-Item $out, $err
$smoke = if ($log -match '自动试玩结算' -and $log -notmatch 'SCRIPT ERROR') { 0 } else { 1 }
if ($smoke -eq 0) { Write-Output '通过  冒烟 · AI 代玩山门到结算' } else { Write-Output '失败  冒烟 · AI 代玩山门'; Write-Output $log }
exit [Math]::Max($unit, $smoke)
