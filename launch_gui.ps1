$ErrorActionPreference = 'Stop'
$candidates = @((Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'),
                (Join-Path $PSScriptRoot 'runtime\pythonw.exe'))
foreach ($name in @('pythonw.exe', 'python.exe', 'python3.exe', 'pyw.exe', 'py.exe')) {
    $candidates += @(Get-Command $name -All -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
}
$candidates += @("$env:USERPROFILE\anaconda3\python.exe")
$launcher = Join-Path $PSScriptRoot 'gui_launcher.py'
foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if ($candidate -match 'WindowsApps' -or -not (Test-Path -LiteralPath $candidate)) { continue }
    $windowless = Join-Path (Split-Path -Parent $candidate) 'pythonw.exe'
    if ((Split-Path -Leaf $candidate) -eq 'py.exe') {
        $windowless = Join-Path (Split-Path -Parent $candidate) 'pyw.exe'
    }
    if (Test-Path -LiteralPath $windowless) { $candidate = $windowless }
    try {
        $probe = New-Object System.Diagnostics.ProcessStartInfo
        $probe.FileName = $candidate
        $probe.Arguments = '-c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3,10) else 1)"'
        $probe.UseShellExecute = $false
        $probe.CreateNoWindow = $true
        $process = [System.Diagnostics.Process]::Start($probe)
        if (-not $process.WaitForExit(8000)) { $process.Kill(); continue }
        if ($process.ExitCode -ne 0) { continue }
        Start-Process -FilePath $candidate -ArgumentList ('"' + $launcher + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
        exit 0
    } catch { continue }
}
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.MessageBox]::Show('No usable Python was found. Install Python 3.10+ with tkinter and add it to PATH. Fully extract the ZIP first.', 'Mojian') | Out-Null
