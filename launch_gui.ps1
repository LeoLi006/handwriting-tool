$ErrorActionPreference = 'Stop'
$candidates = @()
foreach ($name in @('pythonw.exe', 'python.exe', 'python3.exe', 'pyw.exe', 'py.exe')) {
    $candidates += @(Get-Command $name -All -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
}
$candidates += @("$env:USERPROFILE\anaconda3\python.exe", 'D:\Users\lwz\anaconda3\python.exe')
$launcher = Join-Path $PSScriptRoot 'gui_launcher.py'
foreach ($candidate in $candidates) {
    if ($candidate -match 'WindowsApps' -or -not (Test-Path -LiteralPath $candidate)) { continue }
    $windowless = Join-Path (Split-Path -Parent $candidate) 'pythonw.exe'
    if ((Split-Path -Leaf $candidate) -eq 'py.exe') {
        $windowless = Join-Path (Split-Path -Parent $candidate) 'pyw.exe'
    }
    if (Test-Path -LiteralPath $windowless) { $candidate = $windowless }
    try {
        Start-Process -FilePath $candidate -ArgumentList ('"' + $launcher + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
        exit 0
    } catch { continue }
}
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.MessageBox]::Show('No usable Python was found. Install Python 3.9+ and add it to PATH.', 'Mojian') | Out-Null
