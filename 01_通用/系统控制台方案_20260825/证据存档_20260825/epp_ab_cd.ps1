# EPP A/B Test - controlled burst load measurement (NO stress tools)
# Phase A: EPP=0 (current value, untouched) -> measure
# Phase B: EPP=70 applied -> measure -> ALWAYS restore original in finally
param([Parameter(Mandatory=$true)][ValidateSet('A','B','C','D','Analyze')][string]$Phase)
$ErrorActionPreference='Continue'

$dir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$dataD = Join-Path $dir 'data'
if(!(Test-Path $dataD)){ New-Item -ItemType Directory -Path $dataD | Out-Null }

$subProc='54533251-82be-4824-96c1-47b60b740d00'
$eppGuid='36687f9e-e3a5-4dbf-b1dc-15eb381c6863'
$userBase='HKLM:\SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes'

function Get-ActiveScheme { (Get-ItemProperty $userBase -ErrorAction SilentlyContinue).ActivePowerScheme }
function Read-EppAc {
    $k="$userBase\$(Get-ActiveScheme)\$subProc\$eppGuid"
    if(Test-Path $k){ return [int](Get-ItemProperty $k).AcSettingIndex }
    return -1
}
function Set-EppAc {
    param([int]$val)
    powercfg /setacvalueindex SCHEME_CURRENT $subProc $eppGuid $val 2>&1 | Out-Null
    powercfg /setactive SCHEME_CURRENT 2>&1 | Out-Null
}
function Get-FreqSample {
    $c=Get-CimInstance -ClassName Win32_PerfFormattedData_Counters_ProcessorInformation -Filter "Name='_Total'" -ErrorAction SilentlyContinue
    if($c){ return @([double]$c.PercentProcessorPerformance,[double]$c.PercentProcessorUtility) }
    return @(-1.0,-1.0)
}
function Get-GpuTempC {
    $smi="$env:SystemRoot\System32\nvidia-smi.exe"
    if(!(Test-Path $smi)){ $smi="$env:SystemRoot\Sysnative\nvidia-smi.exe" }
    if(Test-Path $smi){
        $o=& $smi --query-gpu=temperature.gpu --format=csv,noheader,nounits 2>$null
        if($o){ try { return [double]($o | Select-Object -First 1) } catch {} }
    }
    return -1.0
}
function Start-Workers {
    param([int]$count,[int]$seconds)
    $tpl='param($p) $end=(Get-Date).AddSeconds(__SEC__); $x=1.0; while((Get-Date) -lt $end){ for($i=0;$i -lt 80000;$i++){ $x=[math]::Sqrt($x+$i) } }'
    $src=$tpl.Replace('__SEC__',"$seconds")
    $enc=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($src))
    $procs=@()
    for($i=0;$i -lt $count;$i++){
        $p=Start-Process powershell -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-EncodedCommand',$enc) -WindowStyle Hidden -PassThru
        $procs+=$p
    }
    return ,$procs
}
function Stop-Workers {
    param($procs)
    foreach($p in $procs){
        if($p -and -not $p.HasExited){ try{ Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }catch{} }
    }
}

# ---- measurement protocol shared by A and B ----
function Run-Protocol {
    param([string]$prefix,[System.Collections.ArrayList]$rows)
    $watch=[System.Diagnostics.Stopwatch]::StartNew()
    $aborted=$false

    # idle block 30s
    Write-Host "[$prefix] idle sampling 30s..."
    $idleEnd=(Get-Date).AddSeconds(30)
    while((Get-Date) -lt $idleEnd){
        $f=Get-FreqSample
        [void]$rows.Add([pscustomobject]@{tag="${prefix}_idle";t=(Get-Date -Format 'HH:mm:ss');perf=$f[0];util=$f[1];gpuC=-1})
        Start-Sleep -Milliseconds 700
    }
    $g=Get-GpuTempC; Write-Host "[$prefix] idle done. GPU=${g}C"

    # 8 bursts x (load 16s, sample 12s), cooldown 8s
    for($b=1;$b -le 8;$b++){
        if($aborted -or $watch.Elapsed.TotalSeconds -gt 300){ break }
        $gt=Get-GpuTempC
        if($gt -ge 80){ Write-Host "ABORT: GPU ${gt}C >= 80C before burst $b"; $aborted=$true; break }
        Write-Host ("[{0}] burst {1}/8 starting (GPU={2}C)..." -f $prefix,$b,$gt)
        $procs=Start-Workers -count 4 -seconds 16
        Start-Sleep -Milliseconds 2000   # let workers spin up
        $sampEnd=(Get-Date).AddSeconds(12)
        while((Get-Date) -lt $sampEnd){
            $f=Get-FreqSample
            [void]$rows.Add([pscustomobject]@{tag="${prefix}_b$b";t=(Get-Date -Format 'HH:mm:ss');perf=$f[0];util=$f[1];gpuC=-1})
            Start-Sleep -Milliseconds 700
        }
        Stop-Workers $procs
        $g2=Get-GpuTempC
        [void]$rows.Add([pscustomobject]@{tag="${prefix}_bursttemp";t=(Get-Date -Format 'HH:mm:ss');perf=-1;util=-1;gpuC=$g2})
        Write-Host ("[{0}] burst {1} done. GPU={2}C" -f $prefix,$b,$g2)
        Start-Sleep -Seconds 8           # cooldown
    }
    $gf=Get-GpuTempC
    Write-Host "[$prefix] protocol finished. aborted=$aborted finalGPU=${gf}C elapsed=$([int]$watch.Elapsed.TotalSeconds)s"
    return $aborted
}

function Summarize {
    param($rows,[string]$label)
    $idle =$rows | Where-Object {$_.tag -like '*_idle' -and $_.perf -ge 0}
    $burst=$rows | Where-Object {$_.tag -match '_b\d+$' -and $_.perf -ge 0}
    $temps=$rows | Where-Object {$_.tag -like '*_bursttemp'} | ForEach-Object{$_.gpuC} | Where-Object{$_ -gt 0}
    $r=[ordered]@{}
    $r.idlePerf = if($idle){ [math]::Round(($idle.perf | Measure-Object -Average).Average,1) } else { -1 }
    $r.idleUtil = if($idle){ [math]::Round(($idle.util | Measure-Object -Average).Average,1) } else { -1 }
    if($burst){
        $r.loadPerfMean=[math]::Round(($burst.perf | Measure-Object -Average).Average,1)
        $r.loadPerfMax =[math]::Round(($burst.perf | Measure-Object -Maximum).Maximum,1)
        $r.loadUtilMean=[math]::Round(($burst.util | Measure-Object -Average).Average,1)
        $r.loadPoints  =$burst.Count
    } else { $r.loadPerfMean=-1; $r.loadPerfMax=-1; $r.loadUtilMean=-1; $r.loadPoints=0 }
    if($temps){ $r.gpuMax=[math]::Round(($temps | Measure-Object -Maximum).Maximum,1); $r.gpuLast=$temps[-1] } else { $r.gpuMax=-1; $r.gpuLast=-1 }
    Write-Host "---- Summary [$label] ----"
    $r.GetEnumerator() | ForEach-Object { Write-Host ("  {0} = {1}" -f $_.Key,$_.Value) }
    return $r
}

# ================= main =================
if($Phase -eq 'A'){
    $orig=Read-EppAc
    Write-Host "=== PHASE A (EPP untouched, expect AC=0) ==="
    Write-Host "EPP AC before: $orig"
    $rows=New-Object System.Collections.ArrayList
    $null = Run-Protocol -prefix 'A' -rows $rows
    $csv=Join-Path $dataD 'A.csv'
    $rows | Export-Csv -NoTypeInformation -Encoding ASCII -Path $csv
    Write-Host "Saved: $csv ($($rows.Count) rows)"
    Summarize -rows $rows -label 'A: EPP=0'
}
elseif($Phase -eq 'B' -or $Phase -eq 'C' -or $Phase -eq 'D'){
    $orig=Read-EppAc
    Write-Host "=== PHASE B (apply EPP=70, restore $orig after) ==="
    $tgt = 40; if($Phase -eq 'D') { $tgt = 50 }
    Set-EppAc -val $tgt
    Start-Sleep -Seconds 2
    $now=Read-EppAc
    Write-Host "EPP AC readback after apply: $now"
    if($now -ne $tgt){ Write-Host "FATAL: apply failed, aborting (no state change risk)"; exit 2 }
    $rows=New-Object System.Collections.ArrayList
    try {
        Start-Sleep -Seconds 15   # settle
        $null = Run-Protocol -prefix 'B' -rows $rows
    } finally {
        Write-Host "RESTORING EPP AC -> $orig"
        Set-EppAc -val $orig
        Start-Sleep -Seconds 2
        $chk=Read-EppAc
        if($chk -eq $orig){ Write-Host "RESTORE VERIFIED: EPP AC=$chk" }
        else { Write-Host "RESTORE FAILED! current=$chk expected=$orig" ; exit 3 }
    }
    $csv=Join-Path $dataD ("$Phase.csv")
    $rows | Export-Csv -NoTypeInformation -Encoding ASCII -Path $csv
    Write-Host "Saved: $csv ($($rows.Count) rows)"
    Summarize -rows $rows -label 'B: EPP=70'
}
elseif($Phase -eq 'Analyze'){
    $a=Import-Csv (Join-Path $dataD 'A.csv')
    $bn="C.csv"; if($Phase -eq "D"){$bn="D.csv"}; $b=Import-Csv (Join-Path $dataD $bn)
    foreach($x in @($a,$b)){ foreach($r in $x){ $r.perf=[double]$r.perf; $r.util=[double]$r.util; $r.gpuC=[double]$r.gpuC } }
    $sa=Summarize -rows $a -label 'A: EPP=0'
    $sb=Summarize -rows $b -label 'B: EPP=70'
    Write-Host ""
    Write-Host "================ COMPARISON ================"
    Write-Host ("Idle  avg perf%% : A={0}  B={1}" -f $sa.idlePerf,$sb.idlePerf)
    Write-Host ("Load  avg perf%% : A={0}  B={1}  delta={2}%" -f $sa.loadPerfMean,$sb.loadPerfMean,[math]::Round($sb.loadPerfMean-$sa.loadPerfMean,1))
    Write-Host ("Load  max perf%% : A={0}  B={1}" -f $sa.loadPerfMax,$sb.loadPerfMax)
    Write-Host ("Load  avg util%% : A={0}  B={1} (sanity: should be similar & high)" -f $sa.loadUtilMean,$sb.loadUtilMean)
    Write-Host ("GPU max temp     : A={0}C  B={1}C" -f $sa.gpuMax,$sb.gpuMax)
    Write-Host ("GPU last temp    : A={0}C  B={1}C" -f $sa.gpuLast,$sb.gpuLast)
    $d=$sb.loadPerfMean-$sa.loadPerfMean
    if($sa.loadPoints -eq 0 -or $sb.loadPoints -eq 0){
        Write-Host "VERDICT: INCOMPLETE DATA"
    } elseif($d -le -3){
        Write-Host ("VERDICT: EPP EFFECT CONFIRMED - load frequency dropped {0}% with EPP 0->70" -f [math]::Abs([math]::Round($d,1)))
    } elseif($d -ge 3){
        Write-Host "VERDICT: UNEXPECTED - B faster than A (investigate)"
    } else {
        Write-Host "VERDICT: NO SIGNIFICANT DIFFERENCE (<3%) - HWP autonomy dominates at this load level"
    }
}
