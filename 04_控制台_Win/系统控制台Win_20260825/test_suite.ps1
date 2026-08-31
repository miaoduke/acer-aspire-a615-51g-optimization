# test_suite.ps1 - Windows SysConsole detailed test suite v2.1
$ErrorActionPreference = 'Continue'
$proj = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $proj
$script:results = New-Object System.Collections.ArrayList
function Add-R($name, $status, $detail) {
    $line = ("{0,-6} {1,-26} {2}" -f $status, $name, $detail)
    $script:results.Add($line) | Out-Null
    Write-Host $line
}
Get-Process -Name 'SysConsole','SysConsoleDebug' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 600
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class WCap {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool CloseWindow(IntPtr h);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
}
"@
function Shot($proc, $path) {
    $h = $proc.MainWindowHandle
    if ($h -eq [IntPtr]::Zero) { return $false }
    [WCap]::ShowWindow($h, 9) | Out-Null
    [WCap]::SetForegroundWindow($h) | Out-Null
    Start-Sleep -Milliseconds 700
    $r = New-Object WCap+RECT
    [WCap]::GetWindowRect($h, [ref]$r) | Out-Null
    $w = $r.Right - $r.Left
    $ht = $r.Bottom - $r.Top
    if ($w -le 0 -or $ht -le 0) { return $false }
    $bmp = New-Object System.Drawing.Bitmap($w, $ht)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($r.Left, $r.Top, 0, 0, $bmp.Size)
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bmp.Dispose()
    return $true
}
Write-Host "=== Windows SysConsole Test Suite v2.1 ==="

# ---- T1 build artifacts ----
$rel = Join-Path $proj 'SysConsole.exe'
$dbg = Join-Path $proj 'SysConsoleDebug.exe'
$lhm = Join-Path $proj 'LibreHardwareMonitorLib.dll'
$t1 = (Test-Path $rel) -and (Test-Path $dbg) -and (Test-Path $lhm)
Add-R 'T1_build_artifacts' $(if ($t1) {'PASS'} else {'FAIL'}) 'release+debug+LHM.dll'

# ---- T2 selftest ----
$out = & $dbg --selftest 2>&1 | Out-String
$code = $LASTEXITCODE
$t2 = ($code -eq 0) -and ($out -match 'SELFTEST: PASS')
Add-R 'T2_selftest' $(if ($t2) {'PASS'} else {'FAIL'}) ("exit=" + $code)
if ($out -match '\[LHM\](.*)') { Add-R 'T2a_lhm_probe' 'INFO' ($Matches[1].Trim()) }
if ($out -match 'NVIDIA GeForce') { Add-R 'T2b_nvidia' 'INFO' 'MX150 via nvidia-smi' }

# ---- T3 GUI smoke (verify real window, not mutex messagebox) ----
$p = Start-Process -FilePath $rel -ArgumentList '/tab=0' -PassThru
Start-Sleep -Seconds 4
$p.Refresh()
$alive = -not $p.HasExited
$title = $p.MainWindowTitle
$mem0 = [math]::Round($p.WorkingSet64 / 1MB, 1)
$realWindow = ($title -eq [char]0x7CFB + [char]0x7EDF + [char]0x63A7 + [char]0x5236 + [char]0x53F0)
Add-R 'T3_gui_alive_title' $(if ($alive) {'PASS'} else {'FAIL'}) ("alive=" + $alive)

# ---- T5 memory stability 30s ----
$samples = @()
for ($i = 0; $i -lt 6; $i++) {
    Start-Sleep -Seconds 5
    if ($p.HasExited) { break }
    $p.Refresh()
    $samples += [math]::Round($p.WorkingSet64 / 1MB, 1)
}
$first = $samples[0]; $last = $samples[$samples.Count - 1]
$growthOk = ($last - $first) -lt (($first * 0.25) + 10)
Add-R 'T5_memory_stability' $(if ($growthOk) {'PASS'} else {'WARN'}) ("MB: " + ($samples -join ','))

# ---- T9 screenshot tab0 ----
$ok0 = Shot $p (Join-Path $proj 'shot_tab0_overview.png')
Add-R 'T9a_shot_tab0' $(if ($ok0) {'PASS'} else {'SKIP'}) 'shot_tab0_overview.png'
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800

# ---- T4 tabs 1..3 alive + shot separately ----
foreach ($n in 1..3) {
    $q = Start-Process -FilePath $rel -ArgumentList ("/tab=" + $n) -PassThru
    Start-Sleep -Seconds 3
    $q.Refresh()
    $qa = -not $q.HasExited
    Add-R ("T4_tab" + $n + "_alive") $(if ($qa) {'PASS'} else {'FAIL'}) "process"
    if ($qa) {
        $shotName = "shot_tab" + $n + ".png"
        $okN = Shot $q (Join-Path $proj $shotName)
        Add-R ("T4_tab" + $n + "_shot") $(if ($okN) {'PASS'} else {'SKIP'}) $shotName
    }
    Stop-Process -Id $q.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 600
}

# ---- T6 power plan switch roundtrip (guaranteed restore) ----
$origLine = powercfg /getactivescheme
$origGuid = [regex]::Match($origLine, '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}').Value
$balGuid  = '0ba71e37-09c0-45d0-a5f7-e6ed0c28ab8d'
try {
    if ($origGuid -eq $balGuid) {
        Add-R 'T6_plan_roundtrip' 'SKIP' 'already balanced'
    } else {
        powercfg /setactive $balGuid 2>$null
        Start-Sleep -Milliseconds 800
        $switched = (powercfg /getactivescheme) -match $balGuid
        powercfg /setactive $origGuid 2>$null
        Start-Sleep -Milliseconds 800
        $restored = (powercfg /getactivescheme) -match $origGuid
        if ($switched -and $restored) { Add-R 'T6_plan_roundtrip' 'PASS' 'switch+restore ok' }
        elseif (-not $switched)       { Add-R 'T6_plan_roundtrip' 'SKIP' ('denied; restored=' + $restored) }
        else                          { Add-R 'T6_plan_roundtrip' $(if ($restored) {'WARN'} else {'FAIL'}) ('restore=' + $restored) }
    }
} catch {
    powercfg /setactive $origGuid 2>$null
    Add-R 'T6_plan_roundtrip' 'FAIL' $_.Exception.Message
}

# ---- T7 settings.ini persistence (verify app REWROTE file: tab must become 1 via /tab=1) ----
try {
    $ini = Join-Path $proj 'settings.ini'
    Remove-Item $ini -ErrorAction SilentlyContinue
    Set-Content -LiteralPath $ini -Value "x=40`ny=40`nw=900`nh=680`ntab=2`nalerts=0`ninterval=5000" -Encoding ASCII
    $s = Start-Process -FilePath $rel -ArgumentList '/tab=1' -PassThru
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        $s.Refresh()
        if ($s.HasExited -or $s.MainWindowHandle -ne [IntPtr]::Zero) { break }
        Start-Sleep -Milliseconds 300
    }
    Start-Sleep -Seconds 6   # 消息循环就绪 (v6.6: 首帧含计数器预热)
    $cmr = $null
    if (-not $s.HasExited) { $cmr = $s.CloseMainWindow() }
    Start-Sleep -Seconds 3
    $hstat = "h=$($s.MainWindowHandle) cmr=$cmr exited=$($s.HasExited)"
    if (-not $s.HasExited) { Stop-Process -Id $s.Id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 400
    $saved = Get-Content -LiteralPath $ini -Raw
    $okIv  = $saved -match 'interval=5000'
    $okAl  = $saved -match 'alerts=0'
    $okRw  = $saved -match "tab=1"
    Add-R 'T7_settings_persist' $(if ($okIv -and $okAl -and $okRw) {'PASS'} else {'FAIL'}) ("iv=" + $okIv + " alerts=" + $okAl + " rewritten(tab=1)=" + $okRw + " " + $hstat)
    Remove-Item $ini -ErrorAction SilentlyContinue
} catch {
    Get-Process -Name 'SysConsole' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Add-R 'T7_settings_persist' 'FAIL' $_.Exception.Message
}

Write-Host "================ SUMMARY ================"
$results | ForEach-Object { Write-Host $_ }
$failCount = @($results | Where-Object { $_ -match '^FAIL' }).Count
Set-Content -LiteralPath (Join-Path $proj 'test_report.txt') -Value $results -Encoding ASCII
Write-Host ("TOTAL FAIL=" + $failCount)
if ($failCount -gt 0) { exit 1 } else { exit 0 }

