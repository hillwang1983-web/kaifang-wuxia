# 重启原版服务端（它被探针弄崩 / 要重新载入数据库时用）。MySQL 必须已经在运行。
$srvdir = "C:\游戏\网金最原始文件\网金最原始文件\服务端"
Get-Process -Name "服务端" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 2
Start-Process -FilePath "$srvdir\服务端.exe" -WorkingDirectory $srvdir
Start-Sleep 8
$l = netstat -ano | Select-String ":6731 .*LISTENING"
if ($l) { "original server listening" } else { "original server NOT listening" }
