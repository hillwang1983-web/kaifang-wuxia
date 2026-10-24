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
# 冒烟（AI 代玩，四倍速，不许有脚本报错）：四条出身各走到山门并计时、跳过开场、一条出身跑全程
# 跑一次代玩，返回日志（标准输出 + 标准错误）；最多等 5 分钟：脚本编译失败时游戏不会自己退出，不能让测试一直挂着
function Invoke-Auto([string[]]$flags) {
  $out = [IO.Path]::GetTempFileName()
  $err = [IO.Path]::GetTempFileName()
  $proc = Start-Process -FilePath $godot -ArgumentList (@('--headless', '--path', "`"$project`"", '--', 'auto', 'quit') + $flags) `
    -RedirectStandardOutput $out -RedirectStandardError $err -NoNewWindow -PassThru
  if (-not $proc.WaitForExit(300000)) { $proc.Kill(); Write-Output '冒烟超时（5 分钟没打完），已结束进程' }
  $log = (Get-Content $out -Raw -Encoding UTF8) + (Get-Content $err -Raw -Encoding UTF8)
  Remove-Item $out, $err
  return $log
}
$smoke = 0
$origins = @('shenjia', 'tiejiang', 'xiban', 'langzhong')
# 四条出身各跑到山门：开场必须在 5 分钟（游戏时间）内走到山门（规格书第九节验收）
foreach ($o in $origins) {
  $log = Invoke-Auto @("origin=$o", 'until=shanmen')
  $m = [regex]::Match($log, '代玩计时：.*从开场到山门 (\d+) 秒')
  if ($m.Success -and [int]$m.Groups[1].Value -le 300 -and $log -notmatch 'SCRIPT ERROR') { Write-Output "通过  冒烟 · $($m.Value)" }
  else { $smoke = 1; Write-Output "失败  冒烟 · 出身 $o 没在 5 分钟内走到山门"; Write-Output $log }
}
# 跳过开场：一开场就走暂停菜单的「跳过开场」，直接到山门
$log = Invoke-Auto @('origin=xiban', 'skipintro', 'until=shanmen')
if ($log -match '（跳过开场），从开场到山门' -and $log -notmatch 'SCRIPT ERROR') { Write-Output '通过  冒烟 · 跳过开场直接到山门' }
else { $smoke = 1; Write-Output '失败  冒烟 · 跳过开场'; Write-Output $log }
# 全程：出身按日期轮换，打到 Boss 三结算，还要拾取玄诚掉落并自动装备上（结算里 equipped 不为空）
$full = $origins[(Get-Date).DayOfYear % 4]
$log = Invoke-Auto @("origin=$full")
if ($log -match '自动试玩结算' -and $log -match '"equipped": "[^"]+' -and $log -match '"boss2": true' -and $log -match '"boss3": true' -and $log -match "`"origin`": `"$full`"" -and $log -notmatch 'SCRIPT ERROR') {
  Write-Output "通过  冒烟 · 出身 $full 全程：开场 → 山门 → 藏经阁 → 大雄宝殿，打完三个 Boss，拾取并装备掉落"
} else { $smoke = 1; Write-Output "失败  冒烟 · 出身 $full 全程"; Write-Output $log }
exit [Math]::Max($unit, $smoke)
