# battery-care.ps1 — Windows 侧电池保养 (提醒 + 可选局域网插座限充80%)  2026-08-28
# 用法:
#   手动:   powershell -NoProfile -File battery-care.ps1 [-PlugUrl http://192.168.x.x/relay/0] [-KeepOn] [-SelfTest]
#   常驻:   schtasks /Create /TN battery-care /SC MINUTE /MO 5 /TR "powershell -NoProfile -WindowStyle Hidden -File \"I:\AItest\battery-care-win_20260828\battery-care.ps1\""
#           (仅"只在用户登录时运行", 气球通知需要交互会话)
#   出门模式: -KeepOn → 12h 内强制允许充电(充满带走), 到期自动恢复管控
# 插座模式安全链: 关=79.5%以上, 开=75%以下(迟滞); ≤40%无条件强制开电; 命令失败只告警不改状态;
#   脚本死掉时插座保持最后命令态——若停在"关"会持续掉电, 故任务计划必须常开且 KeepOn 兜底。
# 插座本地API: Shelly Gen2+ GET /relay/0?turn=on|off (本脚本内建, 零依赖);
#   小米(SNZB-043等)/博联(SP3) 需 python-miio / mjg59-python-broadlink, 用户自备 python 后改 SetPlug 即可, 不默认引入。
# 口径对齐 Linux battery-care v2.2: ≥80%拔电提醒(60min去重)/浮充分钟计时(每5min采样+1)/20%、10%两级低电。
param([string]$PlugUrl='', [switch]$KeepOn, [switch]$SelfTest)
$ErrorActionPreference='SilentlyContinue'
$dir="$env:LOCALAPPDATA\battery-care"; New-Item -ItemType Directory -Path $dir -Force | Out-Null
$stf="$dir\state.json"; $now=Get-Date
$st=@{floatMinutes=0;floatDate='';lastUnplugTip='';lastLowTip='';plugState='on';keepOnUntil=''}
if(Test-Path $stf){ try{ $st=[pscustomobject](Get-Content $stf -Raw|ConvertFrom-Json) }catch{} }

function ReadBattery{ # -> @{soc;ac;chg;full} 或 $null
  $b=Get-CimInstance -Namespace root/WMI -ClassName BatteryStatus
  $w=Get-CimInstance Win32_Battery
  if(-not $b -and -not $w){ return $null }
  # 本机ACPI BatteryStatus 实例字段全空 → soc/ac 均需 Win32_Battery 兜底 (实测 2026-08-28)
  $soc=if($b){$b.ChargePercent}else{$null}
  if($soc -eq $null){ $soc=$w.EstimatedChargeRemaining }
  if($soc -eq $null -or $soc -lt 0 -or $soc -gt 100){ return $null }
  $acv=if($b){$b.BatteryStatus}else{$null}
  if($acv -eq $null){ $acv=$w.BatteryStatus }   # Win32: 2=在AC 1=离电
  @{soc=[int]$soc; ac=($acv -eq 2); chg=$false; full=$false} }

function SetPlug([string]$want){ # 仅 Shelly 形态; 失败返回 $false 且不改状态
  if(-not $PlugUrl){ return $true }
  try{ Invoke-RestMethod -Uri "$($PlugUrl.TrimEnd('/'))/0?turn=$want" -TimeoutSec 5 | Out-Null; return $true }catch{ return $false } }

function Notify([string]$title,[string]$msg){
  Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing
  $ni=New-Object System.Windows.Forms.NotifyIcon
  $ni.Icon=[System.Drawing.SystemIcons]::Information; $ni.Visible=$true
  $ni.ShowBalloonTip(6000,$title,$msg,'Warning'); Start-Sleep -Seconds 6; $ni.Dispose() }

function Decide($b,$st,$keepOnActive){ # 纯函数: 返回动作列表 (供 SelfTest 断言)
  $acts=@()
  if($b -eq $null){ return $acts }
  $soc=$b.soc
  if($soc -ge 80 -and $b.ac){ $acts+='unplug_tip'; $acts+='float_tick' }
  if($soc -le 10){ $acts+='low_tip' } elseif($soc -le 20){ $acts+='low_tip' }
  if($PlugUrl -and -not $keepOnActive){
    if($b.ac -and $soc -ge 80 -and $st.plugState -ne 'off'){ $acts+='plug_off' }
    elseif($soc -le 75 -and $st.plugState -ne 'on'){ $acts+='plug_on' } }
  if($soc -le 40 -and $st.plugState -eq 'off'){ $acts=@('plug_on') } # fail-safe 最高优先(插座曾断=硬件存在)
  return $acts }

if($SelfTest){ # ponytail: 逻辑自检; SOC|状态 → 期望动作
  $cases=@(
    @{b=@{soc=85;ac=$true;chg=$true;full=$false};  keep=$false; exp=@('unplug_tip','float_tick')},
    @{b=@{soc=60;ac=$true;chg=$false;full=$false}; keep=$false; exp=@()},
    @{b=@{soc=15;ac=$false;chg=$false;full=$false};keep=$false; exp=@('low_tip')},
    @{b=@{soc=8;ac=$false;chg=$false;full=$false}; keep=$false; exp=@('low_tip')},
    @{b=$null;                                     keep=$false; exp=@()})
  $fail=0
  foreach($c in $cases){ $got=@(Decide $c.b ([pscustomobject]@{plugState='on'}) $c.keep)
    if(($got -join ',') -ne ($c.exp -join ',')){ $fail++; "FAIL: soc=$($c.b.soc) got=[$($got -join ',')] exp=[$($c.exp -join ',')]" } }
  # 迟滞+断电保护
  $g1=@(Decide @{soc=78;ac=$true;chg=$false;full=$false} ([pscustomobject]@{plugState='off'}) $false) -join ','
  if($g1 -ne ''){ $fail++; "FAIL: 迟滞带78%应保持, got=$g1" }
  $g2=@(Decide @{soc=30;ac=$true;chg=$false;full=$false} ([pscustomobject]@{plugState='off'}) $false) -join ','
  if($g2 -ne 'plug_on'){ $fail++; "FAIL: 30%断电保护 got=$g2" }
  $g3=@(Decide @{soc=90;ac=$true;chg=$true;full=$false} ([pscustomobject]@{plugState='on'}) $true) -join ','
  if($g3 -notmatch 'plug_(on|off)'){ "OK: KeepOn 屏蔽插头动作" } else { $fail++; "FAIL: KeepOn got=$g3" }
  if($fail){"SelfTest: $fail FAIL"}else{"SelfTest: ALL PASS"}; exit $fail }

# ———— 单次采样主流程 ————
$b=ReadBattery; if(-not $b){ exit 0 }   # 台式机无电池
if($KeepOn){ $st.keepOnUntil=$now.AddHours(12).ToString('o') }
$keepActive=($st.keepOnUntil -and [datetime]$st.keepOnUntil -gt $now)
$acts=Decide $b $st $keepActive
$flog="$dir\float_log.tsv"
foreach($a in $acts){
  switch($a){
    'float_tick'{ if($now.ToString('yyyy-MM-dd') -ne $st.floatDate){$st.floatMinutes=0;$st.floatDate=$now.ToString('yyyy-MM-dd')}
                  $st.floatMinutes+=5
                  "$(Get-Date -f s)`t$($b.soc)`t$($st.floatMinutes)" | Add-Content $flog }
    'unplug_tip'{ $last=if($st.lastUnplugTip){[datetime]$st.lastUnplugTip}else{[datetime]::MinValue}
                  if(($now-$last).TotalMinutes -ge 60){ Notify '电池保养' "已充到 $($b.soc)%（≥80% 高损伤区）。建议拔电。今日浮充 $($st.floatMinutes) 分钟"; $st.lastUnplugTip=$now.ToString('o') } }
    'low_tip'{    $last=if($st.lastLowTip){[datetime]$st.lastLowTip}else{[datetime]::MinValue}
                  if(($now-$last).TotalMinutes -ge 30){ Notify '低电量' "剩余 $($b.soc)%，深放段损伤≈满循环，请尽快充电"; $st.lastLowTip=$now.ToString('o') } }
    'plug_off'{   if(SetPlug 'off'){ $st.plugState='off'; Notify '电池保养' "80% 上限：已断插座（$($b.soc)%）" } else { Notify '电池保养' '插座断电信令失败，请检查' } }
    'plug_on'{    if(SetPlug 'on'){ $st.plugState='on'; Notify '电池保养' "插座已恢复供电（$($b.soc)%）" } else { Notify '电池保养' '插座通电信令失败，请检查' } }
  } }
$st|ConvertTo-Json -Compress|Set-Content $stf -Encoding UTF8
