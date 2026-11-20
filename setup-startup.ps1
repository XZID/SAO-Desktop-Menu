# SAO Desktop Menu - by Arthur_Zid - Copyright (c) 2026 Arthur_Zid - MIT License (see LICENSE.txt)
# Makes the menu start when you log in (or stops that).
#   powershell -ExecutionPolicy Bypass -File setup-startup.ps1          (add)
#   powershell -ExecutionPolicy Bypass -File setup-startup.ps1 -Remove  (remove)
# Adds a shortcut to your Startup folder. You can also see / switch it in
# Task Manager > Startup apps.
param([switch]$Remove)

$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'SAO Desktop Menu.lnk'
if ($Remove) {
    $done = $false
    if (Test-Path $lnk) { Remove-Item $lnk; $done = $true }
    # an older version may have used a Task Scheduler task instead
    if (Get-ScheduledTask -TaskName 'SAO Desktop Menu' -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName 'SAO Desktop Menu' -Confirm:$false; $done = $true
    }
    if ($done) { 'Removed from startup.' } else { 'It was not in startup.' }
    return
}
if (Get-ScheduledTask -TaskName 'SAO Desktop Menu' -ErrorAction SilentlyContinue) {
    'Already starts at login (Task Scheduler) - nothing to do.'; return
}
$pyw = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $pyw) { 'pythonw was not found - is Python installed and on PATH?'; exit 1 }
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = $pyw
$s.Arguments = '"' + (Join-Path $PSScriptRoot 'launcher.py') + '" --startup'
$s.WorkingDirectory = $PSScriptRoot
$s.Description = 'SAO-style desktop menu (hold middle button + drag down on the desktop)'
$s.WindowStyle = 7
$s.Save()
'Added to startup: it will turn on by itself when you log in.'
