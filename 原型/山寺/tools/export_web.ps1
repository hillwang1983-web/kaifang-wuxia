# 导出山寺网页版到 原型/山寺/build/web/（手机与电脑浏览器试玩用）。需要已装 Godot 4.7.2 导出模板。
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
$out = Join-Path $project 'build\web'
New-Item -ItemType Directory -Force $out | Out-Null
& $godot --headless --path $project --import | Out-Null
& $godot --headless --path $project --export-release 'Web' (Join-Path $out 'index.html')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Get-ChildItem $out | Select-Object Name, Length | Format-Table -AutoSize
