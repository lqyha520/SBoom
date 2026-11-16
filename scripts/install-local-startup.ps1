$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$adminDir = Join-Path $projectRoot 'admin'
$collectorScript = Join-Path $adminDir 'scripts\xhs-local-collector.mjs'
$runnerScript = Join-Path $adminDir 'scripts\run-xhs-collector-hidden.vbs'
$wslExe = Join-Path $env:WINDIR 'System32\wsl.exe'
$wscriptExe = Join-Path $env:WINDIR 'System32\wscript.exe'
$distro = 'Debian'

if (-not (Test-Path -LiteralPath $collectorScript) -or -not (Test-Path -LiteralPath $runnerScript)) {
  throw '项目里的本机采集器启动文件不完整。'
}
if (-not (Test-Path -LiteralPath $wslExe)) { throw '找不到 WSL，请先安装并启动 Debian。' }

$nodePath = $null
foreach ($candidate in Get-Command node.exe -All -ErrorAction Stop) {
  try {
    $versionText = (& $candidate.Source --version 2>$null | Select-Object -First 1) -replace '^v', ''
    if ([version]$versionText -ge [version]'22.12.0') { $nodePath = $candidate.Source; break }
  } catch { continue }
}
if (-not $nodePath) { throw '需要安装 Node.js 22.12 或更新版本。' }

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$wslTaskName = 'Learn Coach WSL Local Backend'
$collectorTaskName = 'Learn Coach XHS Local Collector'

$wslAction = New-ScheduledTaskAction -Execute $wslExe -Argument "--distribution $distro --exec /bin/true"
$wslSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $wslTaskName -Description '启动 Learn Coach 本机 WSL 后台（仅当前 Windows 用户）' `
  -Action $wslAction -Trigger $trigger -Settings $wslSettings -Principal $principal -Force | Out-Null

$collectorArguments = '//B //NoLogo "' + $runnerScript + '" "' + $nodePath + '" "' + $collectorScript + '" "' + $adminDir + '"'
$collectorAction = New-ScheduledTaskAction -Execute $wscriptExe -Argument $collectorArguments -WorkingDirectory $adminDir
$collectorSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -MultipleInstances IgnoreNew -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $collectorTaskName -Description '登录 Windows 后在后台启动 Learn Coach 小红书采集器' `
  -Action $collectorAction -Trigger $trigger -Settings $collectorSettings -Principal $principal -Force | Out-Null

$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop '小红书工作台.url'
$shortcutContent = "[InternetShortcut]`r`nURL=https://localhost/admin/#xhsResearch`r`n"
if (Test-Path -LiteralPath $shortcutPath) {
  $currentShortcut = Get-Content -LiteralPath $shortcutPath -Raw
  if ($currentShortcut -notmatch 'URL=https://localhost/admin/#xhsResearch') {
    throw "桌面已有不同内容的「小红书工作台.url」，为避免覆盖，启动任务已配置但没有改动该文件。"
  }
} else {
  Set-Content -LiteralPath $shortcutPath -Value $shortcutContent -Encoding ASCII
}

Start-ScheduledTask -TaskName $wslTaskName
Start-ScheduledTask -TaskName $collectorTaskName
Write-Output '已设置当前 Windows 用户登录后自动启动本机 WSL 后台和小红书采集器。'
Write-Output "桌面入口：$shortcutPath"
Write-Output "采集器日志：$(Join-Path $env:LOCALAPPDATA 'learn-coach\xhs-collector.log')"
