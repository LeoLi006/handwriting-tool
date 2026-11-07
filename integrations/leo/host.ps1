param(
    [Parameter(Mandatory=$true)][ValidateSet('Shortcut','Stop','Start')][string]$Mode,
    [string]$LeoDirectory,
    [string]$ShortcutPath,
    [string]$ToolDirectory
)
$ErrorActionPreference='Stop'
if($Mode -eq 'Shortcut') {
    $launcher=Join-Path $ToolDirectory '启动GUI.vbs'
    if(-not(Test-Path -LiteralPath $launcher -PathType Leaf)){throw 'Tool launcher not found'}
    $shell=New-Object -ComObject WScript.Shell
    $shortcut=$shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath=Join-Path $env:SystemRoot 'System32/wscript.exe'
    $shortcut.Arguments='"'+$launcher+'"'
    $shortcut.WorkingDirectory=$ToolDirectory
    $shortcut.WindowStyle=7
    $shortcut.Description='Mojian handwriting tool for Leo'
    $shortcut.Save()
    exit 0
}
$exe=[IO.Path]::GetFullPath((Join-Path $LeoDirectory 'LeoLauncher.exe'))
if(-not(Test-Path -LiteralPath $exe -PathType Leaf)){throw 'LeoLauncher.exe not found'}
if($Mode -eq 'Start') {
    if(-not(Get-Process LeoLauncher -ErrorAction SilentlyContinue | Where-Object {$_.Path -eq $exe})) {
        Start-Process -FilePath $exe -WorkingDirectory $LeoDirectory -WindowStyle Hidden
    }
    exit 0
}
$count=0
foreach($process in @(Get-Process LeoLauncher -ErrorAction SilentlyContinue | Where-Object {$_.Path -eq $exe})) {
    $count++
    if($process.CloseMainWindow()){$null=$process.WaitForExit(5000)}
    if(-not $process.HasExited){throw 'Leo did not exit cleanly. Exit Leo yourself, then retry; no settings were changed.'}
}
Write-Output $count
