# 跑山寺 Godot 工程的无界面测试。Godot 路径：先看环境变量 GODOT，再在 PATH 里找 Godot_v4*_console.exe。
$ErrorActionPreference = 'Stop'
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
exit $LASTEXITCODE
