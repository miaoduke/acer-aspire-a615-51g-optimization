// Collector.cs — 数据采集层
// 原则(对齐 Linux 版): 直读系统 API、无第三方依赖、全部 try/except 绝不崩溃、差分计算
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Management;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;

namespace SysConsole
{
    // ---- 快照结构 ----
    public class Snapshot
    {
        public float CpuTotal;
        public float[] CpuPerCore = new float[0];
        public long MemTotalMB, MemUsedMB;
        public float MemUsedPct;
        public Nullable<float> Gpu3D;                 // 可为 null(计数器缺失)
        public Nullable<long> GpuDedicatedMB;
        public float DiskBusy, DiskBytesPerSec;
        public Dictionary<string, float[]> NetPerNic = new Dictionary<string, float[]>(); // [rx,tx] B/s
        public int BatteryPct = -1;                   // -1 无电池/未知
        public string PowerLine = "未知";
        public long BatteryLifeSec = -1;
        public bool TempNeedsAdmin;
        public List<string> TempZones = new List<string>();
        public string UptimeText = "";
        public string ActivePlanName = "";
        // ---- v2 新增 ----
        public bool Elevated;
        public bool LhmActive;
        public string LhmError = "";
        public int LhmHardwareCount;
        public List<string> LhmTemps = new List<string>();
        public List<string> LhmFans = new List<string>();
        public Nullable<float> LhmCpuTempBest;
        public Nullable<float> LhmCpuPowerW;
        public string NvidiaName = "";
        public Nullable<float> NvidiaUtil;
        public Nullable<float> NvidiaTemp;
        public Nullable<long> NvidiaMemMB;
        public Nullable<float> NvidiaPowerW;
        // ---- v3 新增: CPU 频率 + 电池深度数据 ----
        public Nullable<int> CpuFreqMHz;              // 当前频率 (WMI)
        public Nullable<int> CpuFreqMaxMHz;           // 最大频率 (WMI)
        public Nullable<float> BatteryTempC;          // 电池温度 °C (WMI)
        public Nullable<long> BatteryChargeRateMW;    // 充电功率 mW (WMI, 正=充电)
        public Nullable<long> BatteryDischargeRateMW; // 放电功率 mW (WMI, 正=放电)
        public Nullable<long> BatteryDesignCapMWh;    // 设计容量 mWh
        public Nullable<long> BatteryFullCapMWh;      // 实际满充容量 mWh
        public Nullable<float> BatteryVoltageV;       // 电压 V
        public Nullable<float> BatteryHealthPct;      // 健康度 % = FullCap/DesignCap*100
        // ---- v3.2: 充电阶段 + 健康趋势 + 进程排行 ----
        public string BatteryChargePhase = "";        // CC(恒流)/CV(恒压)/--(未知)
        public float BatteryHealthSlope;              // 健康趋势斜率 (%/天, 负=衰退)
        public List<ProcessPowerInfo> TopProcesses = new List<ProcessPowerInfo>();
        // ---- v3.3: 系统维护 ----
        public List<ServiceInfo> Services = new List<ServiceInfo>();
        public string KernelVersion = "";
        public string[] StartupItems = new string[0];
        // ---- v5: 对标热门监控工具新增 ----
        public Dictionary<int, float> GpuPerProc = new Dictionary<int, float>();      // pid → GPU%
        public Dictionary<int, float> DiskPerProc = new Dictionary<int, float>();     // pid → IO Bytes/s
        public long SysProcCount, SysThreadCount, SysHandleCount;                    // 系统进程/线程/句柄总数
        public List<string> LhmAllSensors = new List<string>();                      // 全部 LHM 传感器 "名称=值 单位"
        public List<string> NicInfos = new List<string>();                           // 网卡详情
        public List<string> DiskHealth = new List<string>();                         // 磁盘健康+剩余空间
        public List<string> RecentEvents = new List<string>();                       // 最近系统事件(错误/警告)
        public double TodayRxMB, TodayTxMB;                                          // 今日累计流量
    }

    public class ProcessPowerInfo
    {
        public string Name;
        public int Pid;
        public float CpuPct;
        public long MemMB;
    }

    public class ServiceInfo
    {
        public string Name;
        public string Status;  // Running/Stopped/NotFound
        public string DisplayName;
    }

    public class PowerPlan
    {
        public string Guid;
        public string Name;
        public bool IsActive;
    }

    public class Collector : IDisposable
    {
        // ---- CPU ----
        private PerformanceCounter _cpuTotal;
        private PerformanceCounter[] _cpuCores;
        // ---- GPU ----
        private List<PerformanceCounter> _gpu3D = new List<PerformanceCounter>();
        private PerformanceCounter _gpuMem;
        private bool _gpuBroken;
        private int _tickSinceGpuInit = 999;
        // ---- 磁盘 ----
        private PerformanceCounter _diskBusy, _diskBytes; // _diskBusy 实为 % Idle Time (v6.8)
        private PerformanceCounter _cpuPerf;              // % Processor Performance (真实频率)
        private int _cpuBaseMHz, _cpuMaxMHz;              // 基频/最大频 (WMI 一次缓存)
        // ---- 网络 ----
        private Dictionary<string, PerformanceCounter> _netRx = new Dictionary<string, PerformanceCounter>();
        private Dictionary<string, PerformanceCounter> _netTx = new Dictionary<string, PerformanceCounter>();
        // ---- 温度 ----
        private bool? _tempAdminBlocked;   // null=未探测 true=拒绝访问 false=可读
        // ---- LibreHardwareMonitor(反射可选加载, 需管理员) ----
        private object _lhmComputer;
        private bool _lhmTried;
        private volatile bool _lhmActive;        // M: InitLhm 后台化, volatile 保证发布顺序
        private volatile string _lhmError = "";
        private int _lhmHardwareCount;
        // ---- nvidia-smi ----
        private string _nvidiaSmi;
        private int _tickSinceNv = 999;
        private volatile string _nvCacheName = "";   // M: QueryNvidia 后台写, volatile 发布
        private Nullable<float> _nvU, _nvT, _nvP;
        private Nullable<long> _nvM;
        // ---- v3: 性能日志 ----
        private string _logDir;
        private DateTime _lastLogTime = DateTime.MinValue;
        private int _logIntervalSec = 30;
        // ---- v3.2: 充电阶段检测 + 健康趋势 ----
        private List<float> _healthHistory = new List<float>();  // 最近 20 次健康度采样
        private List<DateTime> _healthTimes = new List<DateTime>();  // H4: 配对时间戳, 回归 x 轴用天
        private List<float> _voltageHistory = new List<float>(); // 最近 5 次电压
        private List<float> _currentHistory = new List<float>(); // 最近 5 次电流(mA)

        public Collector()
        {
            // v3: 初始化性能日志目录
            try
            {
                _logDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "SysConsole", "logs");
                if (!Directory.Exists(_logDir)) Directory.CreateDirectory(_logDir);
            }
            catch { _logDir = null; }

            try
            {
                _cpuTotal = new PerformanceCounter("Processor", "% Processor Time", "_Total", true);
                string[] inst = new PerformanceCounterCategory("Processor").GetInstanceNames();
                List<PerformanceCounter> cores = new List<PerformanceCounter>();
                foreach (string s in inst)
                {
                    if (s == "_Total") continue;
                    int n;
                    if (int.TryParse(s, out n)) cores.Add(new PerformanceCounter("Processor", "% Processor Time", s, true));
                }
                cores.Sort(delegate(PerformanceCounter a, PerformanceCounter b)
                { return string.Compare(a.InstanceName, b.InstanceName, StringComparison.Ordinal); });
                _cpuCores = cores.ToArray();

                // % Disk Time 未对并发队列校正可>100% → 用 100-%Idle Time (恒在 0..100)
                            _diskBusy = new PerformanceCounter("PhysicalDisk", "% Idle Time", "_Total", true);
                _diskBytes = new PerformanceCounter("PhysicalDisk", "Disk Bytes/sec", "_Total", true);

                InitNetwork();
                InitGpuAsync();   // v6.6: 后台化 (断电后 GPU 计数器构造可挂死, 不阻塞 ctor)

                // 预热: 首次 NextValue 恒为 0, 丢弃
                WarmUp();
            }
            catch (Exception ex) { Program.Trace("Collector ctor 计数器初始化失败: " + ex.Message); /* 计数器缺失也不崩溃 */ }

            InitLhmAsync();
            ResolveNvidia();
        }

        /// M修复: LHM Open+枚举最多 5 秒, 移入线程池防阻塞 UI/ctor; LhmActive 由后续快照生效
        private void InitLhmAsync()
        {
            if (_lhmTried) return;
            _lhmTried = true;
            System.Threading.ThreadPool.QueueUserWorkItem(delegate { InitLhm(); });
        }

        private void WarmUp()
        {
            try { if (_cpuTotal != null) _cpuTotal.NextValue(); } catch { }
            if (_cpuCores != null) foreach (PerformanceCounter c in _cpuCores) { try { c.NextValue(); } catch { } }
            try { if (_diskBusy != null) _diskBusy.NextValue(); } catch { }
            try { if (_diskBytes != null) _diskBytes.NextValue(); } catch { }
            foreach (PerformanceCounter c in _netRx.Values) { try { c.NextValue(); } catch { } }
            foreach (PerformanceCounter c in _netTx.Values) { try { c.NextValue(); } catch { } }
            foreach (PerformanceCounter c in _gpu3D) { try { c.NextValue(); } catch { } }
            try { if (_gpuMem != null) _gpuMem.NextValue(); } catch { }
        }

        private void InitNetwork()
        {
            _netRx.Clear(); _netTx.Clear();
            try
            {
                foreach (string name in new PerformanceCounterCategory("Network Interface").GetInstanceNames())
                {
                    _netRx[name] = new PerformanceCounter("Network Interface", "Bytes Received/sec", name, true);
                    _netTx[name] = new PerformanceCounter("Network Interface", "Bytes Sent/sec", name, true);
                }
            }
            catch { }
        }

        private int _gpuInitBg = 0;
        /// v6.6: InitGpu 后台化 — GPU 计数器构造在断电后可挂死, 线程池跑, 完成后原子替换引用
        private void InitGpuAsync()
        {
            if (System.Threading.Interlocked.CompareExchange(ref _gpuInitBg, 1, 0) != 0) return;
            System.Threading.ThreadPool.QueueUserWorkItem(delegate
            {
                try { InitGpu(); }
                finally { _gpuInitBg = 0; }
            });
        }

        private void InitGpu()
        {
            List<PerformanceCounter> fresh = new List<PerformanceCounter>();
            PerformanceCounter freshMem = null;
            try
            {
                PerformanceCounterCategory cat = new PerformanceCounterCategory("GPU Engine");
                foreach (string inst in cat.GetInstanceNames())
                {
                    if (inst.IndexOf("engtype_3D", StringComparison.OrdinalIgnoreCase) >= 0)
                        fresh.Add(new PerformanceCounter("GPU Engine", "Utilization Percentage", inst, true));
                }
                foreach (PerformanceCounter c in fresh) { try { c.NextValue(); } catch { } }
                _tickSinceGpuInit = 0;
                _gpuBroken = false;
            }
            catch { _gpuBroken = fresh.Count == 0; }
            try
            {
                foreach (string inst in new PerformanceCounterCategory("GPU Adapter Memory").GetInstanceNames())
                {
                    freshMem = new PerformanceCounter("GPU Adapter Memory", "Dedicated Usage", inst, true);
                    break;
                }
                try { if (freshMem != null) freshMem.NextValue(); } catch { }
            }
            catch { freshMem = null; }
            List<PerformanceCounter> old3D = _gpu3D;
            PerformanceCounter oldMem = _gpuMem;
            _gpu3D = fresh;          // 原子替换 (读端在 try/catch 内, 拿旧引用最坏丢一帧)
            _gpuMem = freshMem;
            // H1修复: 重建后释放旧计数器, 防每 60 tick 泄漏一批句柄
            foreach (PerformanceCounter c in old3D) { try { c.Dispose(); } catch { } }
            if (oldMem != null) { try { oldMem.Dispose(); } catch { } }
        }
        [StructLayout(LayoutKind.Sequential)]
        private class MEMORYSTATUSEX
        {
            public uint dwLength = (uint)Marshal.SizeOf(typeof(MEMORYSTATUSEX));
            public uint dwMemoryLoad;
            public ulong ullTotalPhys;
            public ulong ullAvailPhys;
            public ulong ullTotalPageFile;
            public ulong ullAvailPageFile;
            public ulong ullTotalVirtual;
            public ulong ullAvailVirtual;
            public ulong ullAvailExtendedVirtual;
        }
        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool GlobalMemoryStatusEx([In, Out] MEMORYSTATUSEX lpBuffer);

        [DllImport("kernel32.dll")]
        private static extern ulong GetTickCount64();

        // ---- LibreHardwareMonitor 反射集成 ----
        public static bool IsElevated()
        {
            try
            {
                using (System.Security.Principal.WindowsIdentity id = System.Security.Principal.WindowsIdentity.GetCurrent())
                {
                    System.Security.Principal.WindowsPrincipal pr = new System.Security.Principal.WindowsPrincipal(id);
                    return pr.IsInRole(System.Security.Principal.WindowsBuiltInRole.Administrator);
                }
            }
            catch { return false; }
        }

        private void InitLhm()
        {
            try
            {
                if (!IsElevated()) { _lhmError = "需要管理员权限"; return; }
                string dll = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "LibreHardwareMonitorLib.dll");
                if (!File.Exists(dll)) { _lhmError = "缺少 LibreHardwareMonitorLib.dll"; return; }
                System.Reflection.Assembly asm = System.Reflection.Assembly.LoadFrom(dll);
                Type tComp = asm.GetType("LibreHardwareMonitor.Hardware.Computer");
                if (tComp == null) { _lhmError = "类型 LibreHardwareMonitor.Hardware.Computer 未找到(v" + asm.GetName().Version + ")"; return; }
                _lhmComputer = Activator.CreateInstance(tComp);
                SetProperty(_lhmComputer, "IsCpuEnabled", true);
                SetProperty(_lhmComputer, "IsGpuEnabled", true);
                SetProperty(_lhmComputer, "IsMemoryEnabled", true);
                SetProperty(_lhmComputer, "IsStorageEnabled", false);
                SetProperty(_lhmComputer, "IsMotherboardEnabled", false);
                SetProperty(_lhmComputer, "IsNetworkEnabled", false);
                SetProperty(_lhmComputer, "IsControllerEnabled", false);
                SetProperty(_lhmComputer, "IsPsuEnabled", false);
                tComp.GetMethod("Open").Invoke(_lhmComputer, null);
                // LHM 异步枚举硬件, 等待后台线程完成首次发现(最多 5 秒)
                for (int i = 0; i < 10; i++)
                {
                    System.Threading.Thread.Sleep(500);
                    System.Reflection.PropertyInfo hwProp = tComp.GetProperty("Hardware");
                    object hwColl = hwProp.GetValue(_lhmComputer, null);
                    int count = (int)hwColl.GetType().GetProperty("Count").GetValue(hwColl, null);
                    _lhmHardwareCount = count;
                    if (count > 0) break;
                }
                _lhmActive = true;
            }
            catch (Exception ex)
            {
                _lhmActive = false; _lhmComputer = null;
                _lhmError = ex.GetType().Name + ": " + ex.Message;
                if (ex.InnerException != null) _lhmError += " | 内层: " + ex.InnerException.Message;
            }
        }

        private static void SetProperty(object obj, string name, object val)
        {
            obj.GetType().GetProperty(name).SetValue(obj, val, null);
        }

        private void CollectLhm(Snapshot s)
        {
            if (!_lhmActive || _lhmComputer == null) return;
            float bestCore = float.MinValue; bool havePkg = false; float pkg = 0; float cpuPow = 0;
            try
            {
                Type tComp = _lhmComputer.GetType();
                object hwColl = tComp.GetProperty("Hardware").GetValue(_lhmComputer, null);
                System.Collections.IEnumerable hwList = hwColl as System.Collections.IEnumerable;
                if (hwList == null) return;
                foreach (object hw in hwList)
                {
                    // 先触发硬件更新以填充传感器数据
                    try { hw.GetType().GetMethod("Update").Invoke(hw, null); } catch { }
                    ReadHardware(hw, s, ref bestCore, ref havePkg, ref pkg, ref cpuPow);
                    object sub = hw.GetType().GetProperty("SubHardware").GetValue(hw, null);
                    if (sub != null)
                        foreach (object sh in (System.Collections.IEnumerable)sub)
                        {
                            try { sh.GetType().GetMethod("Update").Invoke(sh, null); } catch { }
                            ReadHardware(sh, s, ref bestCore, ref havePkg, ref pkg, ref cpuPow);
                        }
                }
            }
            catch { }
            if (havePkg) s.LhmCpuTempBest = pkg;
            else if (bestCore > float.MinValue) s.LhmCpuTempBest = bestCore;
            if (cpuPow > 0) s.LhmCpuPowerW = cpuPow;
        }

        private void ReadHardware(object hw, Snapshot s, ref float bestCore, ref bool havePkg, ref float pkg, ref float cpuPow)
        {
            try
            {
                object sensObj = hw.GetType().GetProperty("Sensors").GetValue(hw, null);
                System.Collections.IEnumerable sensors = sensObj as System.Collections.IEnumerable;
                if (sensors == null) return;
                foreach (object sen in sensors)
                {
                    Type st = sen.GetType();
                    object vobj = st.GetProperty("Value").GetValue(sen, null);
                    if (vobj == null) continue;
                    float val;
                    try { val = (float)vobj; } catch { continue; }
                    string type = st.GetProperty("SensorType").GetValue(sen, null).ToString();
                    string name = st.GetProperty("Name").GetValue(sen, null) as string;
                    // v5: 全传感器面板 (HWiNFO 风格, 上限 60 条防爆炸)
                    if (s.LhmAllSensors.Count < 60)
                    {
                        string unit = type == "Temperature" ? "°C" : type == "Power" ? "W"
                            : type == "Fan" ? "RPM" : type == "Voltage" ? "V"
                            : type == "Clock" ? "MHz" : type == "SmallData" || type == "Data" ? "GB" : "";
                        s.LhmAllSensors.Add(type + "/" + name + " = " + val.ToString("F1") + (unit.Length > 0 ? " " + unit : ""));
                    }
                    if (type == "Temperature")
                    {
                        s.LhmTemps.Add(name + ": " + val.ToString("F0") + "°C");
                        if (name != null && name.IndexOf("Package", StringComparison.OrdinalIgnoreCase) >= 0)
                        { havePkg = true; pkg = val; }
                        else if (val > bestCore) bestCore = val;
                    }
                    else if (type == "Fan")
                    {
                        s.LhmFans.Add(name + ": " + val.ToString("F0") + " RPM");
                    }
                    else if (type == "Power" && name != null && name.IndexOf("Package", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        cpuPow = val;
                    }
                }
            }
            catch { }
        }

        private void CloseLhm()
        {
            try
            {
                if (_lhmComputer != null)
                    _lhmComputer.GetType().GetMethod("Close").Invoke(_lhmComputer, null);
            }
            catch { }
            _lhmComputer = null; _lhmActive = false;
        }

        // ---- nvidia-smi ----
        private void ResolveNvidia()
        {
            try
            {
                // v4.2: x86 进程的 System32 会被重定向到 SysWOW64,
                // 需经 Sysnative 访问真正的 64 位 System32\nvidia-smi.exe
                string windir = Environment.GetEnvironmentVariable("windir") ?? @"C:\Windows";
                string[] candidates = new string[] {
                    Path.Combine(windir, "Sysnative", "nvidia-smi.exe"),          // x86 进程专用通道
                    Path.Combine(Environment.SystemDirectory, "nvidia-smi.exe"),  // 64 位编译时直接命中
                    @"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",  // 旧驱动位置
                    @"C:\Program Files\NVIDIA Corporation\Display.Driver\nvidia-smi.exe" // 新驱动位置
                };
                foreach (string c in candidates)
                    if (File.Exists(c)) { _nvidiaSmi = c; return; }
            }
            catch { }
            _nvidiaSmi = null;
        }

        private void QueryNvidia()
        {
            if (string.IsNullOrEmpty(_nvidiaSmi)) return;
            try
            {
                string outp = RunCapture(_nvidiaSmi,
                    "--query-gpu=name,utilization.gpu,memory.used,temperature.gpu,power.draw --format=csv,noheader,nounits", 3000);
                if (string.IsNullOrEmpty(outp)) return;
                string first = outp.Split('\n')[0].Trim();
                string[] parts = first.Split(',');
                if (parts.Length >= 5)
                {
                    float f; long m;
                    _nvCacheName = parts[0].Trim();
                    if (float.TryParse(parts[1].Trim(), out f)) _nvU = f;
                    if (long.TryParse(parts[2].Trim(), out m)) _nvM = m;
                    if (float.TryParse(parts[3].Trim(), out f)) _nvT = f;
                    if (float.TryParse(parts[4].Trim(), out f)) _nvP = f;
                }
            }
            catch { }
        }

        private int _nvBg;
        private void QueryNvidiaAsync()   // 结果写 _nv 缓存, 下一帧生效
        {
            if (System.Threading.Interlocked.CompareExchange(ref _nvBg, 1, 0) != 0) return;
            System.Threading.ThreadPool.QueueUserWorkItem(delegate
            {
                try { QueryNvidia(); }
                finally { _nvBg = 0; }
            });
        }

        // ---- v6.8: CPU 频率真值化 ----
        // WMI CurrentClockSpeed 恒等于标称基频 (本机钉死 1600, 睿频 3400 测不到) → 不可作当前频率.
        // 真值 = 基频 × %ProcessorPerformance/100 (微软官方换算, 可超基频, 且免每秒 WMI 查询)
        private void CollectCpuFreq(Snapshot s)
        {
            try
            {
                if (_cpuBaseMHz <= 0)
                {
                    using (System.Management.ManagementObjectSearcher searcher =
                        new System.Management.ManagementObjectSearcher("SELECT CurrentClockSpeed, MaxClockSpeed FROM Win32_Processor"))
                    {
                        foreach (System.Management.ManagementObject o in searcher.Get())
                        {
                            try { object v = o["CurrentClockSpeed"]; if (v != null) _cpuBaseMHz = Convert.ToInt32(v); } catch { }
                            try { object v = o["MaxClockSpeed"]; if (v != null) _cpuMaxMHz = Convert.ToInt32(v); } catch { }
                            break; // 只取第一个 CPU
                        }
                    }
                    if (_cpuBaseMHz <= 0) _cpuBaseMHz = 1600; // ponytail: WMI 彻底失败时兜底基频
                    try { _cpuPerf = new PerformanceCounter("Processor Information", "% Processor Performance", "_Total", true); }
                    catch { _cpuPerf = null; }
                }
                s.CpuFreqMaxMHz = _cpuMaxMHz > 0 ? _cpuMaxMHz : default(int?);
                if (_cpuPerf != null)
                {
                    float pct = _cpuPerf.NextValue();
                    if (pct > 0f) s.CpuFreqMHz = (int)Math.Round(_cpuBaseMHz * (double)pct / 100.0);
                }
                if (!s.CpuFreqMHz.HasValue) s.CpuFreqMHz = _cpuBaseMHz; // 首拍/失败兜底: 基频
            }
            catch { }
        }

        private void CollectBatteryDeep(Snapshot s)
        {
            try
            {
                using (System.Management.ManagementObjectSearcher searcher =
                    new System.Management.ManagementObjectSearcher("root\\WMI",
                        "SELECT * FROM BatteryStatus"))
                {
                    foreach (System.Management.ManagementObject o in searcher.Get())
                    {
                        try
                        {
                            // 温度 (单位: 十分之一开尔文)
                            object v = o["Temperature"];
                            if (v != null)
                            {
                                double tk = Convert.ToDouble(v);
                                if (tk > 0) s.BatteryTempC = (float)(tk / 10.0 - 273.15);
                            }
                            // 充电/放电速率 (mW)
                            v = o["ChargeRate"];
                            if (v != null)
                            {
                                long rate = Convert.ToInt64(v);
                                if (rate > 0) s.BatteryChargeRateMW = rate;
                            }
                            v = o["DischargeRate"];
                            if (v != null)
                            {
                                long rate = Convert.ToInt64(v);
                                if (rate > 0) s.BatteryDischargeRateMW = rate;
                            }
                            // 设计容量 / 实际满充容量
                            v = o["DesignCapacity"];
                            if (v != null) s.BatteryDesignCapMWh = Convert.ToInt64(v);
                            v = o["FullChargeCapacity"];
                            if (v != null) s.BatteryFullCapMWh = Convert.ToInt64(v);
                            // 电压 (mV → V)
                            v = o["Voltage"];
                            if (v != null) s.BatteryVoltageV = Convert.ToInt64(v) / 1000f;
                            // 健康度
                            if (s.BatteryDesignCapMWh.HasValue && s.BatteryFullCapMWh.HasValue && s.BatteryDesignCapMWh.Value > 0)
                                s.BatteryHealthPct = (float)(s.BatteryFullCapMWh.Value * 100.0 / s.BatteryDesignCapMWh.Value);
                        }
                        catch { }
                        break; // 只取第一个电池
                    }
                }
            }
            catch { }
        }

        // ---- 主采样 ----
        public Snapshot Sample()
        {
            Snapshot s = new Snapshot();

            // CPU
            try
            {
                s.CpuTotal = _cpuTotal.NextValue();
                s.CpuPerCore = new float[_cpuCores.Length];
                for (int i = 0; i < _cpuCores.Length; i++) s.CpuPerCore[i] = _cpuCores[i].NextValue();
            }
            catch { }

            // 内存
            try
            {
                MEMORYSTATUSEX m = new MEMORYSTATUSEX();
                if (GlobalMemoryStatusEx(m))
                {
                    s.MemTotalMB = (long)(m.ullTotalPhys / (1024 * 1024));
                    s.MemUsedMB = (long)((m.ullTotalPhys - m.ullAvailPhys) / (1024 * 1024));
                    s.MemUsedPct = m.dwMemoryLoad;
                }
            }
            catch { }

            // GPU (实例随进程动态变化, 每 60 次采样重建一次)
            try
            {
                _tickSinceGpuInit++;
                if (_gpuBroken || _tickSinceGpuInit > 60) InitGpuAsync();
                if (!_gpuBroken && _gpu3D.Count > 0)
                {
                    float sum = 0f;
                    foreach (PerformanceCounter c in _gpu3D) sum += c.NextValue();
                    s.Gpu3D = sum > 100f ? 100f : sum;
                }
                if (_gpuMem != null) s.GpuDedicatedMB = (long)(_gpuMem.NextValue() / (1024 * 1024));
            }
            catch { }

            // 磁盘
            try { s.DiskBusy = Math.Max(0f, Math.Min(100f, 100f - _diskBusy.NextValue())); } catch { }
            try { s.DiskBytesPerSec = _diskBytes.NextValue(); } catch { }

            // 网络
            foreach (KeyValuePair<string, PerformanceCounter> kv in _netRx)
            {
                try
                {
                    float rx = kv.Value.NextValue();
                    float tx = _netTx[kv.Key].NextValue();
                    s.NetPerNic[kv.Key] = new float[] { rx, tx };
                }
                catch { }
            }

            // 电池 / 供电
            try
            {
                System.Windows.Forms.PowerStatus ps = System.Windows.Forms.SystemInformation.PowerStatus;
                float bp = ps.BatteryLifePercent;
                s.BatteryPct = (bp < 0f || bp > 1f) ? -1 : (int)Math.Round(bp * 100);
                switch (ps.PowerLineStatus)
                {
                    case System.Windows.Forms.PowerLineStatus.Online: s.PowerLine = "已接通电源"; break;
                    case System.Windows.Forms.PowerLineStatus.Offline: s.PowerLine = "使用电池"; break;
                    default: s.PowerLine = "未知"; break;
                }
                s.BatteryLifeSec = ps.BatteryLifeRemaining;
            }
            catch { }

            // 温度区 (ACPI) — 首次探测权限
            try
            {
                if (_tempAdminBlocked != true)
                {
                    List<string> zones = new List<string>();
                    using (System.Management.ManagementObjectSearcher searcher =
                        new System.Management.ManagementObjectSearcher("root\\WMI",
                            "SELECT InstanceName, CurrentTemperature FROM MSAcpi_ThermalZoneTemperature"))
                    {
                        foreach (System.Management.ManagementObject o in searcher.Get())
                        {
                            try
                            {
                                double t = Convert.ToDouble(o["CurrentTemperature"]) / 10.0 - 273.15;
                                zones.Add(string.Format("{0}: {1:F1}°C", o["InstanceName"], t));
                            }
                            catch { }
                        }
                    }
                    if (_tempAdminBlocked == null && zones.Count == 0)
                        _tempAdminBlocked = false; // 能查但无数据
                    else if (zones.Count > 0) _tempAdminBlocked = false;
                    s.TempZones = zones;
                    if (zones.Count == 0 && _tempAdminBlocked == null) { /* 保持待定, 下次再探 */ }
                }
                else s.TempNeedsAdmin = true;

                // 真正的"拒绝访问"在查询抛异常时捕获:
            }
            catch (Exception ex)
            {
                UnauthorizedAccessException ua = ex as UnauthorizedAccessException;
                if (ua == null && ex.InnerException != null)
                    ua = ex.InnerException as UnauthorizedAccessException;
                if (ua != null || (ex.Message != null && ex.Message.IndexOf("拒绝") >= 0))
                    _tempAdminBlocked = true;
                s.TempNeedsAdmin = (_tempAdminBlocked == true);
            }

            // 开机时长
            try
            {
                TimeSpan up = TimeSpan.FromMilliseconds(GetTickCount64());
                s.UptimeText = string.Format("{0}天 {1:D2}:{2:D2}:{3:D2}", (int)up.TotalDays, up.Hours, up.Minutes, up.Seconds);
            }
            catch { }

            // 当前电源计划名
            try
            {
                List<PowerPlan> plans = ListPowerPlans();
                foreach (PowerPlan p in plans) if (p.IsActive) { s.ActivePlanName = p.Name; break; }
            }
            catch { }

            // v2: 权限 / LHM 传感器 / 独显
            s.Elevated = IsElevated();
            s.LhmActive = _lhmActive;
            s.LhmError = _lhmError;
            if (_lhmActive) { CollectLhm(s); s.LhmHardwareCount = _lhmHardwareCount; }
            _tickSinceNv++;
            if (_tickSinceNv >= 5 || string.IsNullOrEmpty(_nvCacheName))
            {
                _tickSinceNv = 0;
                if (string.IsNullOrEmpty(_nvCacheName)) QueryNvidia();   // 首次同步(保持原首帧行为/selftest 输出)
                else QueryNvidiaAsync();                                  // M: 周期刷新后台化, nvidia-smi 最坏 3s 不再卡 UI
            }
            s.NvidiaName = _nvCacheName;
            s.NvidiaUtil = _nvU; s.NvidiaTemp = _nvT; s.NvidiaPowerW = _nvP; s.NvidiaMemMB = _nvM;

            // v3: CPU 频率 + 电池深度数据
            CollectCpuFreq(s);
            CollectBatteryDeep(s);

            // v3.2: 充电阶段 + 健康趋势 + 进程排行 + 系统维护
            DetectChargePhase(s);
            UpdateHealthTrend(s);
            CollectTopProcesses(s);
            CollectMaintenanceInfo(s);

            // v6.7 C1修复: 恢复断电后台化重构时断链的六个采集方法 (PerProc* 自带后台化, 只取上次结果)
            CollectPerProcGpu(s);
            CollectPerProcDisk(s);
            _tick5++;
            if (_tick5 >= 5) { _tick5 = 0; RefreshDetailAsync(); }   // 慢数据 5s 刷新
            Snapshot det = _detailSnap;
            if (det != null)
            {
                s.SysProcCount = det.SysProcCount; s.SysThreadCount = det.SysThreadCount; s.SysHandleCount = det.SysHandleCount;
                s.NicInfos = det.NicInfos; s.DiskHealth = det.DiskHealth; s.RecentEvents = det.RecentEvents;
            }

            // v5: 对标工具启发加载 (TrafficMonitor/Process Explorer/Mission Center/HWiNFO)
            CollectDailyTraffic(s);

            return s;
        }

        // ---- v5: 每进程 GPU% (GPU Engine 计数器实例名含 pid_NNNN) ----
        private int _tick5 = 99;   // 死代码清理: _tick30/_tick60 只增不读, 已删除
        private Dictionary<string, PerformanceCounter> _gpuProcCounters = new Dictionary<string, PerformanceCounter>();
        // v6.6 修复: PerProcGpu/Disk 后台化 — 断电后 PerformanceCounter 构造可挂死 (非慢),
        // UI 线程同步跑会拖死首帧/selftest; 改为 Sample 只返回上次结果, 重量级枚举丢线程池
        // ponytail: _nvU/_nvT/_nvP/_nvM 非 volatile — float/long 在 x86 上写原子且显示数据脏一帧无害, 需要精确再加 Interlocked
        private volatile Dictionary<int, float> _lastGpuPerProc = new Dictionary<int, float>();
        private volatile Dictionary<int, float> _lastDiskPerProc = new Dictionary<int, float>();
        private int _gpuProcBg = 0, _diskProcBg = 0;

        private void CollectPerProcGpu(Snapshot s)
        {
            s.GpuPerProc = _lastGpuPerProc;
            if (System.Threading.Interlocked.CompareExchange(ref _gpuProcBg, 1, 0) != 0) return;
            System.Threading.ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    if (_gpuBroken) return;
                    Dictionary<int, float> acc = new Dictionary<int, float>();
                    Regex pidRe = new Regex(@"pid_(\d+)");
                    PerformanceCounterCategory cat = new PerformanceCounterCategory("GPU Engine");
                    foreach (string inst in cat.GetInstanceNames())
                    {
                        Match m = pidRe.Match(inst);
                        if (!m.Success) continue;
                        int pid;
                        if (!int.TryParse(m.Groups[1].Value, out pid)) continue;
                        PerformanceCounter c;
                        if (!_gpuProcCounters.TryGetValue(inst, out c))
                        {
                            try { c = new PerformanceCounter("GPU Engine", "Utilization Percentage", inst, true); c.NextValue(); }
                            catch { continue; }
                            _gpuProcCounters[inst] = c;
                        }
                        float v = c.NextValue();
                        if (v > 0.05f)
                        {
                            float old;
                            acc.TryGetValue(pid, out old);
                            acc[pid] = old + v;
                        }
                    }
                    if (_gpuProcCounters.Count > 400) _gpuProcCounters.Clear(); // 防实例泄漏膨胀
                    _lastGpuPerProc = acc;
                }
                catch { }
                finally { _gpuProcBg = 0; }
            });
        }

        // ---- v5: 每进程磁盘 IO (Process/IO Data Bytes/sec, 实例名→pid 经 ID Process 映射) ----
        private Dictionary<string, PerformanceCounter> _diskProcIo = new Dictionary<string, PerformanceCounter>();
        private Dictionary<string, PerformanceCounter> _diskProcId = new Dictionary<string, PerformanceCounter>();
        private void CollectPerProcDisk(Snapshot s)
        {
            s.DiskPerProc = _lastDiskPerProc;
            if (System.Threading.Interlocked.CompareExchange(ref _diskProcBg, 1, 0) != 0) return;
            System.Threading.ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    Dictionary<int, float> acc = new Dictionary<int, float>();
                    PerformanceCounterCategory cat = new PerformanceCounterCategory("Process");
                    foreach (string inst in cat.GetInstanceNames())
                    {
                        if (inst == "_Total" || inst == "Idle") continue;
                        try
                        {
                            PerformanceCounter idC;
                            if (!_diskProcId.TryGetValue(inst, out idC))
                            {
                                idC = new PerformanceCounter("Process", "ID Process", inst, true);
                                _diskProcId[inst] = idC;
                            }
                            PerformanceCounter ioC;
                            if (!_diskProcIo.TryGetValue(inst, out ioC))
                            {
                                ioC = new PerformanceCounter("Process", "IO Data Bytes/sec", inst, true);
                                ioC.NextValue();
                                _diskProcIo[inst] = ioC;
                            }
                            int pid = (int)idC.NextValue();
                            float v = ioC.NextValue();
                            if (pid > 0 && v > 1f)
                            {
                                float old;
                                acc.TryGetValue(pid, out old);
                                acc[pid] = old + v;
                            }
                        }
                        catch { }
                    }
                    if (_diskProcIo.Count > 500) { _diskProcIo.Clear(); _diskProcId.Clear(); }
                    _lastDiskPerProc = acc;
                }
                catch { }
                finally { _diskProcBg = 0; }
            });
        }

        // ---- v5: 系统进程/线程/句柄总数 (任务管理器风格摘要) ----
        private void CollectSystemCounts(Snapshot s)
        {
            try
            {
                long p = 0, t = 0, h = 0;
                Process[] ps = Process.GetProcesses();
                p = ps.Length;
                foreach (Process pr in ps)
                {
                    try { t += pr.Threads.Count; } catch { }
                    try { h += pr.HandleCount; } catch { }
                    try { pr.Dispose(); } catch { }
                }
                s.SysProcCount = p; s.SysThreadCount = t; s.SysHandleCount = h;
            }
            catch { }
        }

        // ---- v5: 网卡详情 (Mission Center 风格) ----
        private void CollectNicInfos(Snapshot s)
        {
            s.NicInfos.Clear();
            try
            {
                foreach (System.Net.NetworkInformation.NetworkInterface ni in
                    System.Net.NetworkInformation.NetworkInterface.GetAllNetworkInterfaces())
                {
                    if (ni.OperationalStatus != System.Net.NetworkInformation.OperationalStatus.Up) continue;
                    if (ni.NetworkInterfaceType == System.Net.NetworkInformation.NetworkInterfaceType.Loopback) continue;
                    string ips = "";
                    try
                    {
                        foreach (System.Net.NetworkInformation.UnicastIPAddressInformation ua in ni.GetIPProperties().UnicastAddresses)
                            if (ua.Address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork)
                                ips = ua.Address.ToString();
                    }
                    catch { }
                    s.NicInfos.Add(ni.Name + " | " + ni.NetworkInterfaceType + " | " + (ni.Speed / 1000000.0).ToString("F0") + "Mbps | IP " + (ips.Length > 0 ? ips : "-"));
                }
            }
            catch { }
        }

        // ---- v5: 磁盘健康 + 剩余空间 ----
        private void CollectDiskHealth(Snapshot s)
        {
            s.DiskHealth.Clear();
            try
            {
                using (ManagementObjectSearcher sr = new ManagementObjectSearcher("SELECT Model,Status,Size FROM Win32_DiskDrive"))
                    foreach (ManagementObject o in sr.Get())
                        s.DiskHealth.Add((o["Model"] as string ?? "?") + " | " + (o["Status"] as string ?? "?") + " | " + (((ulong)o["Size"]) / 1073741824.0).ToString("F0") + "GB");
                using (ManagementObjectSearcher sr = new ManagementObjectSearcher("SELECT DeviceID,FreeSpace,Size FROM Win32_LogicalDisk WHERE DriveType=3"))
                    foreach (ManagementObject o in sr.Get())
                    {
                        ulong sz = o["Size"] as ulong? ?? 0, fr = o["FreeSpace"] as ulong? ?? 0;
                        if (sz > 0)
                            s.DiskHealth.Add("盘 " + (o["DeviceID"] as string ?? "?") + " 剩余 " + (fr / 1073741824.0).ToString("F0") + "/" + (sz / 1073741824.0).ToString("F0") + "GB (" + (100.0 * fr / sz).ToString("F0") + "%)");
                    }
            }
            catch { }
        }

        // ---- v5: 最近系统事件 (错误/警告, 24h 内) ----
        private DateTime _lastEventScan = DateTime.MinValue;
        private void CollectRecentEvents(Snapshot s)
        {
            if ((DateTime.Now - _lastEventScan).TotalMinutes < 5) return;
            _lastEventScan = DateTime.Now;
            s.RecentEvents.Clear();
            try
            {
                EventLog log = new EventLog("System");
                int n = 0;
                for (int i = log.Entries.Count - 1; i >= 0 && n < 40 && s.RecentEvents.Count < 15; i--)
                {
                    EventLogEntry e = log.Entries[i];
                    if (e.TimeGenerated < DateTime.Now.AddHours(-24)) break;
                    if (e.EntryType == EventLogEntryType.Error || e.EntryType == EventLogEntryType.Warning)
                    {
                        string src = e.Source ?? "?";
                        string msg = (e.Message ?? "").Replace("\r", " ").Replace("\n", " ");
                        if (msg.Length > 70) msg = msg.Substring(0, 70) + "..";
                        s.RecentEvents.Add(e.TimeGenerated.ToString("MM-dd HH:mm") + " [" + e.EntryType + "] " + src + ": " + msg);
                        n++;
                    }
                }
            }
            catch { }
        }

        // ---- v6.7 C1: 慢数据 (进程/线程/句柄计数+网卡+磁盘健康+系统事件) 后台影子快照, 5s 周期 ----
        private volatile Snapshot _detailSnap;
        private int _detailBg;
        private void RefreshDetailAsync()
        {
            if (System.Threading.Interlocked.CompareExchange(ref _detailBg, 1, 0) != 0) return;
            System.Threading.ThreadPool.QueueUserWorkItem(delegate
            {
                try
                {
                    Snapshot d = new Snapshot();
                    CollectSystemCounts(d);
                    CollectNicInfos(d);
                    CollectDiskHealth(d);
                    CollectRecentEvents(d);
                    _detailSnap = d;   // 整体替换, 读端无撕裂
                }
                catch { }
                finally { _detailBg = 0; }
            });
        }

        // ---- v5: 今日累计流量 (TrafficMonitor 风格, 持久化; M修复: 跨午夜换文件+收发分离) ----
        private Dictionary<string, long> _lastNicRx = new Dictionary<string, long>();
        private Dictionary<string, long> _lastNicTx = new Dictionary<string, long>();
        private string _trafficFile = "";
        private string _trafficDate = "";
        private void CollectDailyTraffic(Snapshot s)
        {
            try
            {
                string today = DateTime.Now.ToString("yyyyMMdd");
                if (_trafficDate != today)   // 跨午夜: 换新文件+清基线, 次日不再累加昨日
                {
                    _trafficDate = today;
                    string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "SysConsole");
                    if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
                    _trafficFile = Path.Combine(dir, "traffic_" + today + ".txt");
                    _lastNicRx.Clear(); _lastNicTx.Clear();
                }
                double rx = 0, tx = 0;
                foreach (System.Net.NetworkInformation.NetworkInterface ni in
                    System.Net.NetworkInformation.NetworkInterface.GetAllNetworkInterfaces())
                {
                    try
                    {
                        if (ni.NetworkInterfaceType == System.Net.NetworkInformation.NetworkInterfaceType.Loopback) continue;
                        System.Net.NetworkInformation.IPInterfaceStatistics st = ni.GetIPStatistics();
                        long lastRx = 0, lastTx = 0;
                        bool hadBase = _lastNicRx.TryGetValue(ni.Id, out lastRx);
                        _lastNicTx.TryGetValue(ni.Id, out lastTx);
                        if (hadBase)   // 首拍只建基线 — 否则把开机以来总计数当成当日增量
                        {
                            if (st.BytesReceived >= lastRx) rx += st.BytesReceived - lastRx;
                            if (st.BytesSent >= lastTx) tx += st.BytesSent - lastTx;   // M: 上行不再恒 0
                        }
                        _lastNicRx[ni.Id] = st.BytesReceived;
                        _lastNicTx[ni.Id] = st.BytesSent;
                    }
                    catch { }
                }
                double curRx = 0, curTx = 0;
                if (File.Exists(_trafficFile))
                {
                    string[] tok = File.ReadAllText(_trafficFile).Trim().Split(' ');
                    double.TryParse(tok[0], out curRx);
                    if (tok.Length > 1) double.TryParse(tok[1], out curTx);
                }
                s.TodayRxMB = curRx + rx / 1048576.0;
                s.TodayTxMB = curTx + tx / 1048576.0;
                if (rx > 0 || tx > 0) File.WriteAllText(_trafficFile, s.TodayRxMB.ToString("F2") + " " + s.TodayTxMB.ToString("F2"));
            }
            catch { }
        }

        // ================= v6: 本机调优 (全部经本机探测验证可用) =================

        // ---- 屏幕亮度 (root\WMI WmiMonitorBrightnessMethods, 本机验证 OK) ----
        public int? GetBrightness()
        {
            try
            {
                using (ManagementObjectSearcher sr = new ManagementObjectSearcher(@"root\WMI", "SELECT CurrentBrightness FROM WmiMonitorBrightness"))
                    foreach (ManagementObject o in sr.Get())
                        return Convert.ToInt32(o["CurrentBrightness"]);
            }
            catch { }
            return null;
        }

        public bool SetBrightness(int pct)
        {
            try
            {
                using (ManagementObject c = new ManagementClass(@"root\WMI", "WmiMonitorBrightnessMethods", null).CreateInstance())
                // WmiSetBrightness(Timeout, Brightness)
                c.InvokeMethod("WmiSetBrightness", new object[] { (uint)1, (byte)pct });
                return true;
            }
            catch { return false; }
        }

        // ---- v6.6: 显示刷新率 (user32, 零依赖; 本机 1080p144Hz 实测) ----
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
        private struct DEVMODE
        {
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmDeviceName;
            public ushort dmSpecVersion; public ushort dmDriverVersion; public ushort dmSize; public ushort dmDriverExtra;
            public uint dmFields; public int dmPositionX; public int dmPositionY; public uint dmDisplayOrientation; public uint dmDisplayFixedOutput;
            public short dmColor; public short dmDuplex; public short dmYResolution; public short dmTTOption; public short dmCollate;
            [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmFormName;
            public ushort dmLogPixels; public uint dmBitsPerPel; public uint dmPelsWidth; public uint dmPelsHeight;
            public uint dmDisplayFlags; public uint dmDisplayFrequency;
            public uint dmICMMethod; public uint dmICMIntent; public uint dmMediaType; public uint dmDitherType;
            public uint dmReserved1; public uint dmReserved2; public uint dmPanningWidth; public uint dmPanningHeight;
        }
        [DllImport("user32.dll", CharSet = CharSet.Ansi)]
        private static extern bool EnumDisplaySettings(string deviceName, int mode, ref DEVMODE dm);
        [DllImport("user32.dll", CharSet = CharSet.Ansi)]
        private static extern int ChangeDisplaySettingsEx(string deviceName, ref DEVMODE dm, IntPtr hwnd, uint flags, IntPtr lParam);

        /// 主屏设备名 (本机 EnumDisplaySettings 对 null 设备名返回失败, 必须显式指定 — 0826 实测)
        private static string PrimaryDevice()
        {
            try { return System.Windows.Forms.Screen.PrimaryScreen.DeviceName; }
            catch { return null; }
        }

        /// 当前刷新率 (枚举当前模式); 失败返回 null
        public static int? GetRefreshRate()
        {
            try
            {
                DEVMODE dm = new DEVMODE();
                dm.dmSize = (ushort)Marshal.SizeOf(typeof(DEVMODE));
                if (EnumDisplaySettings(PrimaryDevice(), -1 /*ENUM_CURRENT_SETTINGS*/, ref dm)) return (int)dm.dmDisplayFrequency;
            }
            catch { }
            return null;
        }

        /// 切换刷新率 (只改频率, 分辨率/位深保持当前值); 返回 null=成功
        public static string SetRefreshRate(int hz)
        {
            try
            {
                DEVMODE dm = new DEVMODE();
                dm.dmSize = (ushort)Marshal.SizeOf(typeof(DEVMODE));
                if (!EnumDisplaySettings(PrimaryDevice(), -1, ref dm)) return "枚举当前显示模式失败";
                // v6.6 修复: DM_DISPLAYFREQUENCY=0x00400000 (此前误写 0x00800000=DM_ICMMETHOD 导致驱动静默忽略);
                // 带上 BITSPERPEL/PELSWIDTH/PELSHEIGHT 提高驱动兼容性
                dm.dmFields = 0x00400000u | 0x00040000u | 0x00080000u | 0x00100000u;
                dm.dmDisplayFrequency = (uint)hz;
                // M修复: CDS_TEST 预校验, 驱动不支持时返回明确错误而不是直接尝试切换
                int t = ChangeDisplaySettingsEx(PrimaryDevice(), ref dm, IntPtr.Zero, 0x00000010 /*CDS_TEST*/, IntPtr.Zero);
                if (t != 0 && t != 1 /*DISP_CHANGE_SUCCESSFUL / RESTART*/) return "模式预检失败 (CDS_TEST=" + t + ")";
                int r = ChangeDisplaySettingsEx(PrimaryDevice(), ref dm, IntPtr.Zero, 0, IntPtr.Zero);
                return r == 0 /*DISP_CHANGE_SUCCESSFUL*/ ? null : "ChangeDisplaySettingsEx 返回 " + r;
            }
            catch (Exception ex) { return ex.Message; }
        }

        /// 枚举主屏全部可用刷新率 (去重升序)
        public static List<int> EnumRefreshRates()
        {
            List<int> list = new List<int>();
            try
            {
                DEVMODE dm = new DEVMODE();
                dm.dmSize = (ushort)Marshal.SizeOf(typeof(DEVMODE));
                string dev = PrimaryDevice();
                for (int i = 0; EnumDisplaySettings(dev, i, ref dm); i++)
                {
                    int hz = (int)dm.dmDisplayFrequency;
                    if (hz >= 30 && !list.Contains(hz)) list.Add(hz);
                }
                list.Sort();
            }
            catch { }
            return list;
        }

        // ---- 电源设置读写 (powercfg, 本机验证无需管理员) ----
        /// 读取当前方案的 AC/DC 值 (返回 null=读取失败)
        public static int?[] ReadPowerSetting(string subGuid, string settingGuid)
        {
            try
            {
                string outp = RunCapture("powercfg", "/q SCHEME_CURRENT " + subGuid + " " + settingGuid, 5000);
                int? ac = null, dc = null;
                foreach (string line in outp.Split('\n'))
                {
                    string l = line.Trim();
                    if (ac == null && l.IndexOf("交流", StringComparison.Ordinal) >= 0)
                    {
                        Match m = Regex.Match(l, @"0x[0-9a-fA-F]+");
                        if (m.Success) ac = Convert.ToInt32(m.Value, 16);
                    }
                    else if (dc == null && l.IndexOf("直流", StringComparison.Ordinal) >= 0)
                    {
                        Match m = Regex.Match(l, @"0x[0-9a-fA-F]+");
                        if (m.Success) dc = Convert.ToInt32(m.Value, 16);
                    }
                }
                return new int?[] { ac, dc };
            }
            catch { return new int?[] { null, null }; }
        }

        /// 写入 AC/DC 值并立即应用 (返回 null=成功, 否则错误信息)
        public static string ApplyPowerSetting(string subGuid, string settingGuid, int acVal, int dcVal)
        {
            try
            {
                // M修复: 原来 err1 = RunCapture(...out err1...) 让 stdout 覆盖了 stderr, 报错信息错位
                string o1, o2, err1, err2;
                int c1, c2;
                o1 = RunCapture("powercfg", "/setacvalueindex SCHEME_CURRENT " + subGuid + " " + settingGuid + " " + acVal, 5000, out err1, out c1);
                o2 = RunCapture("powercfg", "/setdcvalueindex SCHEME_CURRENT " + subGuid + " " + settingGuid + " " + dcVal, 5000, out err2, out c2);
                RunCapture("powercfg", "/setactive SCHEME_CURRENT", 5000);
                if (c1 != 0) return "AC 写入失败: " + (err1.Trim().Length > 0 ? err1.Trim() : o1.Trim());
                if (c2 != 0) return "DC 写入失败: " + (err2.Trim().Length > 0 ? err2.Trim() : o2.Trim());
                return null;
            }
            catch (Exception ex) { return ex.Message; }
        }

        // (死代码清理: QueryGpuDetail 无调用点, 已删除 — 详情展示走 QueryNvidiaUtilDetail/GetDisplayInfo)

        // ---- 显示信息 (只读) ----
        public List<string> GetDisplayInfo()
        {
            List<string> list = new List<string>();
            try
            {
                using (ManagementObjectSearcher sr = new ManagementObjectSearcher("SELECT Name,CurrentHorizontalResolution,CurrentVerticalResolution,CurrentRefreshRate,VideoModeDescription FROM Win32_VideoController"))
                    foreach (ManagementObject o in sr.Get())
                    {
                        string name = o["Name"] as string ?? "?";
                        int? w = o["CurrentHorizontalResolution"] as int?;
                        int? h = o["CurrentVerticalResolution"] as int?;
                        int? rr = o["CurrentRefreshRate"] as int?;
                        if (w.HasValue && w.Value > 0)
                            list.Add(name + " | " + w + "x" + h + " @ " + rr + "Hz");
                        else
                            list.Add(name + " | (空闲/无输出)");
                    }
            }
            catch { }
            return list;
        }

        // ---- v6.2: 电池数据块增强 (root\WMI ACPI 电池) ----
        /// 循环次数 + 满充容量 (非管理员可读); 设计容量/温度 需管理员
        public int?[] GetBatteryBlocks()
        {
            int? cycles = null, fullCap = null, designCap = null;
            try
            {
                using (ManagementObjectSearcher sr = new ManagementObjectSearcher(@"root\WMI", "SELECT CycleCount FROM BatteryCycleCount"))
                    foreach (ManagementObject o in sr.Get()) { cycles = Convert.ToInt32(o["CycleCount"]); break; }
            }
            catch { }
            try
            {
                using (ManagementObjectSearcher sr = new ManagementObjectSearcher(@"root\WMI", "SELECT FullChargedCapacity FROM BatteryFullChargedCapacity"))
                    foreach (ManagementObject o in sr.Get()) { fullCap = Convert.ToInt32(o["FullChargedCapacity"]); break; }
            }
            catch { }
            try
            {
                using (ManagementObjectSearcher sr = new ManagementObjectSearcher(@"root\WMI", "SELECT DesignedCapacity FROM BatteryStaticData"))
                    foreach (ManagementObject o in sr.Get()) { designCap = Convert.ToInt32(o["DesignedCapacity"]); break; }
            }
            catch { }
            return new int?[] { cycles, fullCap, designCap };
        }

        // ---- v6.2: 自适应亮度 (ADAPTBRIGHT, 本机 SUB_VIDEO 已确认存在) ----
        public const string ADAPTBRIGHT_GUID = "fbd9aa66-9553-4097-ba44-ed6e9d65eab8";

        // ---- v6.2: GPU 编解码利用率 (nvidia-smi -q Utilization 段) ----
        public string QueryNvidiaUtilDetail()
        {
            try
            {
                if (string.IsNullOrEmpty(_nvidiaSmi)) return "";
                string outp = RunCapture(_nvidiaSmi, "-q -d UTILIZATION", 4000);
                string enc = "", dec = "", graf = "";
                foreach (string line in outp.Split('\n'))
                {
                    string l = line.Trim();
                    if (l.StartsWith("Graphics") && graf.Length == 0) graf = l;
                    if (l.StartsWith("Encoder")) enc = l;
                    if (l.StartsWith("Decoder")) dec = l;
                }
                return "3D " + graf + " | " + enc + " | " + dec;
            }
            catch { return ""; }
        }

        // ---- v6.3: NVIDIA 深度状态 (单次 -q 全解析: P状态/时钟/功耗墙/降频原因/PCIe) ----
        public class NvidiaDeep
        {
            public string PState = "?";
            public string TempC = "?";
            public string ClockGfx = "?", ClockGfxMax = "?", ClockMem = "?", ClockMemMax = "?";
            public string PowerLimit = "?";
            public string MemUsed = "?", MemTotal = "?";
            public string PcieGen = "?", PcieWidth = "?";
            public string DisplayActive = "?";
            public bool ThrottleSwPowerCap;
            public bool ThrottleSwThermal;
            public bool ThrottleHwThermal;
            public bool ThrottleHwSlowdown;
            public List<string> Lines = new List<string>();
        }

        public NvidiaDeep QueryNvidiaDeep()
        {
            NvidiaDeep d = new NvidiaDeep();
            if (string.IsNullOrEmpty(_nvidiaSmi)) return d;
            try
            {
                string outp = RunCapture(_nvidiaSmi, "-q", 5000);
                string section = "";
                bool fbT = false, fbU = false;   // v6.6: FB 段只取第一对 Total/Used (BAR1 等后续段不再混入)
                foreach (string rawLine in outp.Split('\n'))
                {
                    string l = rawLine.Trim();
                    if (l.Length == 0) continue;
                    // 段落跟踪
                    if (l == "Clocks" || l == "Max Clocks" || l.StartsWith("Clocks Event Reasons") ||
                        l.StartsWith("Power Readings") || l.StartsWith("PCIe") || l == "Display" ||
                        l.StartsWith("Performance") || l.StartsWith("Temperature") || l.StartsWith("FB Memory Usage") ||
                        l.StartsWith("BAR1 Memory Usage"))
                        section = l;
                    string key = l.Contains(":") ? l.Substring(0, l.IndexOf(':')).Trim() : "";
                    string val = l.Contains(":") ? l.Substring(l.IndexOf(':') + 1).Trim() : "";
                    if (l.StartsWith("Performance State")) { d.PState = val; d.Lines.Add("P状态: " + val); }
                    else if (l.StartsWith("GPU Current Temp")) { d.TempC = val; d.Lines.Add("温度: " + val); }
                    else if (key == "Graphics" && section == "Clocks") { d.ClockGfx = val; d.Lines.Add("核心时钟: " + val); }
                    else if (key == "SM" && section == "Clocks") { d.Lines.Add("SM 时钟: " + val); }
                    else if (key == "Memory" && section == "Clocks") { d.ClockMem = val; d.Lines.Add("显存时钟: " + val); }
                    else if (key == "Graphics" && section == "Max Clocks") { d.ClockGfxMax = val; d.Lines.Add("核心最大时钟: " + val); }
                    else if (key == "Memory" && section == "Max Clocks") { d.ClockMemMax = val; d.Lines.Add("显存最大时钟: " + val); }
                    else if (l.StartsWith("Current Power Limit") && !val.StartsWith("N/A")) { d.PowerLimit = val; d.Lines.Add("当前功耗墙: " + val); }
                    else if (l.StartsWith("SW Power Cap") && !l.Contains("Counters") && !l.Contains("us")) d.ThrottleSwPowerCap = val == "Active";
                    else if (l.StartsWith("SW Thermal Slowdown") && !l.Contains("us")) d.ThrottleSwThermal = val == "Active";
                    else if (l.StartsWith("HW Thermal Slowdown") && !l.Contains("us")) d.ThrottleHwThermal = val == "Active";
                    else if (l.StartsWith("HW Slowdown") && !l.Contains("Thermal") && !l.Contains("us")) d.ThrottleHwSlowdown = val == "Active";
                    else if (l.StartsWith("Current") && section.StartsWith("PCIe") && l.Contains("Gen")) d.PcieGen = val;
                    else if (l.StartsWith("Current") && section.StartsWith("PCIe") && l.Contains("Width")) d.PcieWidth = val;
                    else if (l.StartsWith("Display Active")) { d.DisplayActive = val; d.Lines.Add("显示输出: " + val); }
                    else if (l.StartsWith("Used") && section.StartsWith("FB Memory") && !fbU) { d.MemUsed = val; d.Lines.Add("显存占用: " + val); fbU = true; }
                    else if (l.StartsWith("Total") && section.StartsWith("FB Memory") && !fbT) { d.MemTotal = val; d.Lines.Add("显存总量: " + val); fbT = true; }
                }
                // 降频原因行
                List<string> th = new List<string>();
                if (d.ThrottleSwPowerCap) th.Add("SW功耗墙");
                if (d.ThrottleSwThermal) th.Add("SW热降频");
                if (d.ThrottleHwThermal) th.Add("HW热降频");
                if (d.ThrottleHwSlowdown) th.Add("HW减速");
                d.Lines.Add("降频原因: " + (th.Count > 0 ? string.Join(", ", th.ToArray()) + " ⚠" : "无"));
                d.Lines.Add("PCIe: Gen" + d.PcieGen + " x" + d.PcieWidth);
            }
            catch { }
            return d;
        }

        // ---- v6.3: PowerMizer 注册表 (实验性, 需管理员+重启生效) ----
        private const string NVIDIA_CLASS_KEY = @"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}";

        /// 找到 NVIDIA 显卡驱动注册表键 (0001 等)
        private Microsoft.Win32.RegistryKey FindNvidiaDriverKey()
        {
            try
            {
                // C2修复: 命中键不再包 using (原实现返回已 Dispose 的键, PowerMizer 读写永远静默失败)
                // 所有权移交调用方 (ReadPowerMizer/SetPowerMizer 的 using 负责释放)
                using (Microsoft.Win32.RegistryKey cls = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(NVIDIA_CLASS_KEY, true))
                {
                    if (cls == null) return null;
                    foreach (string sub in cls.GetSubKeyNames())
                    {
                        Microsoft.Win32.RegistryKey k = cls.OpenSubKey(sub, true);
                        if (k == null) continue;
                        string desc = (k.GetValue("DriverDesc") as string) ?? "";
                        if (desc.IndexOf("NVIDIA", StringComparison.OrdinalIgnoreCase) >= 0)
                            return k;
                        k.Close();
                    }
                }
            }
            catch { }
            return null;
        }

        /// 读 PowerMizer 当前值 (返回 null=不可读/需管理员)
        public string[] ReadPowerMizer()
        {
            try
            {
                using (Microsoft.Win32.RegistryKey k = FindNvidiaDriverKey())
                {
                    if (k == null) return null;
                    object en = k.GetValue("PowerMizerEnable");
                    object lv = k.GetValue("PowerMizerLevel");
                    object lvac = k.GetValue("PowerMizerLevelAC");
                    object src = k.GetValue("PerfLevelSrc");
                    return new string[] {
                        en == null ? "(默认)" : en.ToString(),
                        lv == null ? "(默认)" : lv.ToString(),
                        lvac == null ? "(默认)" : lvac.ToString(),
                        src == null ? "(默认)" : src.ToString()
                    };
                }
            }
            catch { return null; }
        }

        /// 写 PowerMizer 预设. mode: 1=偏高性能, 0=恢复默认. 返回 null=成功
        public string SetPowerMizer(int mode)
        {
            try
            {
                using (Microsoft.Win32.RegistryKey k = FindNvidiaDriverKey())
                {
                    if (k == null) return "未找到 NVIDIA 驱动键 (需管理员)";
                    if (mode == 0)
                    {
                        foreach (string v in new string[] { "PowerMizerEnable", "PowerMizerLevel", "PowerMizerLevelAC", "PerfLevelSrc" })
                        {
                            try { k.DeleteValue(v, false); } catch { }
                        }
                        return null;
                    }
                    // 偏最高性能 (经典笔记本调优: 锁定高性能档)
                    k.SetValue("PowerMizerEnable", 1, Microsoft.Win32.RegistryValueKind.DWord);
                    k.SetValue("PowerMizerLevel", 1, Microsoft.Win32.RegistryValueKind.DWord);
                    k.SetValue("PowerMizerLevelAC", 1, Microsoft.Win32.RegistryValueKind.DWord);
                    k.SetValue("PerfLevelSrc", 0x2222, Microsoft.Win32.RegistryValueKind.DWord);
                    return null;
                }
            }
            catch (Exception ex) { return ex.Message + " (需管理员权限)"; }
        }

        // ================= v6.4: 隐藏电源设置 + Boost 模式 + 电源滑块 Overlay =================
        // 借鉴 PowerSettingsExplorer (Scott, 2017): 直读定义库枚举全部设置(含隐藏), powercfg 可写隐藏项

        public class PowerSettingInfo
        {
            public string SubgroupGuid, SubgroupName, SettingGuid, FriendlyName, Description;
            public bool Hidden;
            public string CurrentAC = "(默认)", CurrentDC = "(默认)";
        }

        private const string POWER_SETTINGS_DEF = @"SYSTEM\CurrentControlSet\Control\Power\PowerSettings";
        private const string POWER_USER_SCHEMES = @"SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes";

        /// 枚举全部电源设置 (含隐藏), 附当前覆盖值
        public List<PowerSettingInfo> EnumeratePowerSettings()
        {
            List<PowerSettingInfo> list = new List<PowerSettingInfo>();
            try
            {
                using (Microsoft.Win32.RegistryKey baseK = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(POWER_SETTINGS_DEF))
                {
                    if (baseK == null) return list;
                    string activeScheme = GetActiveSchemeGuid();
                    foreach (string sub in baseK.GetSubKeyNames())
                    {
                        using (Microsoft.Win32.RegistryKey subK = baseK.OpenSubKey(sub))
                        {
                            if (subK == null) continue;
                            string subName = (subK.GetValue("FriendlyName") as string) ?? sub;
                            foreach (string st in subK.GetSubKeyNames())
                            {
                                using (Microsoft.Win32.RegistryKey stK = subK.OpenSubKey(st))
                                {
                                    if (stK == null) continue;
                                    PowerSettingInfo info = new PowerSettingInfo();
                                    info.SubgroupGuid = sub;
                                    info.SubgroupName = subName;
                                    info.SettingGuid = st;
                                    info.FriendlyName = (stK.GetValue("FriendlyName") as string) ?? st;
                                    info.Description = (stK.GetValue("Description") as string) ?? "";
                                    int attr = stK.GetValue("Attributes") is int ? (int)stK.GetValue("Attributes") : 0;
                                    info.Hidden = (attr & 1) != 0;
                                    // 当前覆盖值
                                    using (Microsoft.Win32.RegistryKey ov = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(
                                        POWER_USER_SCHEMES + "\\" + activeScheme + "\\" + sub + "\\" + st))
                                    {
                                        if (ov != null)
                                        {
                                            object ac = ov.GetValue("ACSettingIndex"), dc = ov.GetValue("DCSettingIndex");
                                            if (ac is int) info.CurrentAC = "0x" + ((int)ac).ToString("X");
                                            if (dc is int) info.CurrentDC = "0x" + ((int)dc).ToString("X");
                                        }
                                    }
                                    list.Add(info);
                                }
                            }
                        }
                    }
                }
            }
            catch { }
            return list;
        }

        private string GetActiveSchemeGuid()
        {
            try
            {
                string outp = RunCapture("powercfg", "/getactivescheme", 4000);
                Match m = Regex.Match(outp, @"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})");
                return m.Success ? m.Groups[1].Value : "";
            }
            catch { return ""; }
        }

        /// 写任意电源设置 (含隐藏项). 返回 null=成功
        public static string SetPowerSettingRaw(string subGuid, string settingGuid, int acVal, int dcVal)
        {
            return ApplyPowerSetting(subGuid, settingGuid, acVal, dcVal);
        }

        // ---- Boost 模式 (PERFBOOSTMODE, 隐藏但可写, 本机已实测) ----
        public const string PERFBOOSTMODE_GUID = "be337238-0d82-4146-a960-4f3749d470c7";
        public static readonly string[] BOOST_NAMES = new string[] {
            "0 禁用", "1 启用", "2 Aggressive (默认)", "3 Efficient Enabled", "4 Efficient Aggressive", "5 Aggressive At Guaranteed" };

        /// 读 Boost AC/DC (隐藏设置 powercfg /q 不输出 → 注册表直读; null=未覆盖走系统默认)
        public int?[] ReadBoostModeACDC()
        {
            int? ac = null, dc = null;
            try
            {
                string scheme = GetActiveSchemeGuid();
                using (Microsoft.Win32.RegistryKey k = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(
                    POWER_USER_SCHEMES + "\\" + scheme + "\\" + SUB_PROCESSOR_GUID + "\\" + PERFBOOSTMODE_GUID))
                {
                    if (k != null)
                    {
                        object a = k.GetValue("ACSettingIndex"); if (a is int) ac = (int)a;
                        object d = k.GetValue("DCSettingIndex"); if (d is int) dc = (int)d;
                    }
                }
            }
            catch { }
            return new int?[] { ac, dc };
        }
        public int? ReadBoostMode()
        {
            int?[] v = ReadBoostModeACDC();
            return v[0].HasValue ? v[0] : 2; // 兜底: Windows 默认 Aggressive (旧行为)
        }

        public string SetBoostMode(int mode)
        {
            return ApplyPowerSetting(SUB_PROCESSOR_GUID, PERFBOOSTMODE_GUID, mode, mode);
        }

        // ---- v6.5: EPP 能量性能偏好 (PERFEPP, 隐藏但可写; 本机 A/B 实测: 空载时钟 -75%, 负载 -14% @0->70) ----
        // 注意: 本机真实 GUID 尾号为 e3a5-4dbf-b1dc-15eb381c6863 (经注册表直读验证)
        public const string PERFEPP_GUID = "36687f9e-e3a5-4dbf-b1dc-15eb381c6863";

        /// 读 EPP AC/DC 覆盖值 (隐藏设置 powercfg /q 不输出 → 注册表直读; null=未覆盖/失败)
        public int?[] ReadEpp()
        {
            try
            {
                string scheme = GetActiveSchemeGuid();
                using (Microsoft.Win32.RegistryKey k = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(
                    POWER_USER_SCHEMES + "\\" + scheme + "\\" + SUB_PROCESSOR_GUID + "\\" + PERFEPP_GUID))
                {
                    if (k != null)
                    {
                        object ac = k.GetValue("ACSettingIndex");
                        object dc = k.GetValue("DCSettingIndex");
                        return new int?[] { ac is int ? (int)ac : (int?)null, dc is int ? (int)dc : (int?)null };
                    }
                }
            }
            catch { }
            return new int?[] { null, null };
        }

        /// 写 EPP (0=最高性能 .. 100=最大省电). 返回 null=成功
        public string SetEpp(int acVal, int dcVal)
        {
            return ApplyPowerSetting(SUB_PROCESSOR_GUID, PERFEPP_GUID, acVal, dcVal);
        }

        public static string SUB_PROCESSOR_GUID = "54533251-82be-4824-96c1-47b60b740d00";

        // ---- 电源滑块 Overlay (Win11, 注册表+setactive, 写需管理员; 本机已验证读=ded574b5) ----
        public const string OVERLAY_BEST_EFFICIENCY = "961cc777-2547-4f9d-8174-7d86181b8a7a";
        public const string OVERLAY_BALANCED = "00000000-0000-0000-0000-000000000000";
        public const string OVERLAY_BEST_PERFORMANCE = "ded574b5-45a0-4f42-8737-46345c09c238";

        public string GetActiveOverlay()
        {
            try
            {
                using (Microsoft.Win32.RegistryKey k = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(POWER_USER_SCHEMES))
                {
                    if (k == null) return "?";
                    object v = k.GetValue("ActiveOverlayAcPowerScheme");
                    return v as string ?? "?";
                }
            }
            catch { return "?"; }
        }

        public string OverlayName(string guid)
        {
            if (guid == OVERLAY_BEST_EFFICIENCY) return "最佳能效";
            if (guid == OVERLAY_BALANCED) return "平衡";
            if (guid == OVERLAY_BEST_PERFORMANCE) return "最佳性能";
            return guid;
        }

        /// 切换电源滑块. 返回 null=成功 (需管理员)
        public string SetActiveOverlay(string overlayGuid)
        {
            try
            {
                using (Microsoft.Win32.RegistryKey k = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(POWER_USER_SCHEMES, true))
                {
                    if (k == null) return "注册表打开失败 (需管理员)";
                    k.SetValue("ActiveOverlayAcPowerScheme", overlayGuid);
                    k.SetValue("ActiveOverlayDcPowerScheme", overlayGuid);
                }
                RunCapture("powercfg", "/setactive SCHEME_CURRENT", 4000);
                return null;
            }
            catch (Exception ex) { return ex.Message + " (需管理员权限)"; }
        }

        /// v6.6: 仅写 DC 侧电源滑块 Overlay (A4 修正: 离电不再跟随 AC 挂最佳性能). 返回 null=成功 (需管理员)
        public string SetActiveOverlayDc(string overlayGuid)
        {
            try
            {
                using (Microsoft.Win32.RegistryKey k = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(POWER_USER_SCHEMES, true))
                {
                    if (k == null) return "注册表打开失败 (需管理员)";
                    k.SetValue("ActiveOverlayDcPowerScheme", overlayGuid);
                }
                RunCapture("powercfg", "/setactive SCHEME_CURRENT", 4000);
                return null;
            }
            catch (Exception ex) { return ex.Message + " (需管理员权限)"; }
        }

        // ---- v6.6: 无线适配器功耗模式 (SUB_WIFI, 隐藏组; 0=最高性能..3=最大省电) ----
        public const string SUB_WIFI_GUID = "19cbb8fa-5279-450e-9fac-8a3d5fedd0c1";
        public const string WIRELESS_POWER_GUID = "12bbebe6-58d6-4636-95bb-3217ef867c1a";
        public static readonly string[] WIRELESS_POWER_NAMES = new string[] {
            "0 最高性能", "1 低省电", "2 中省电", "3 最大省电" };

        // v6.6: CLI 用公开常量 (PCIe ASPM)
        public const string SUB_PCIEXPRESS_GUID = "501a4d13-42af-4429-9fd1-a8218c268e20";
        public const string PCIE_ASPM_GUID = "ee12f906-d277-404b-b6da-e5fa1a576df5";

        /// 读无线功耗 AC/DC 覆盖值 (隐藏设置 → 注册表直读; null=未覆盖/失败)
        public int?[] ReadWirelessPower()
        {
            try
            {
                string scheme = GetActiveSchemeGuid();
                using (Microsoft.Win32.RegistryKey k = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(
                    POWER_USER_SCHEMES + "\\" + scheme + "\\" + SUB_WIFI_GUID + "\\" + WIRELESS_POWER_GUID))
                {
                    if (k != null)
                    {
                        object ac = k.GetValue("ACSettingIndex");
                        object dc = k.GetValue("DCSettingIndex");
                        return new int?[] { ac is int ? (int)ac : (int?)null, dc is int ? (int)dc : (int?)null };
                    }
                }
            }
            catch { }
            return new int?[] { null, null };
        }

        /// 写无线功耗档位. 返回 null=成功
        public string SetWirelessPower(int acVal, int dcVal)
        {
            return ApplyPowerSetting(SUB_WIFI_GUID, WIRELESS_POWER_GUID, acVal, dcVal);
        }

        // ---- v6.6: EcoQoS 进程效率模式 (Win11 原生 API, 零依赖) ----
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool SetProcessInformation(IntPtr hProcess, int cls, ref ProcThrottleState s, int size);
        [DllImport("kernel32.dll")]
        private static extern bool CloseHandle(IntPtr h);
        [StructLayout(LayoutKind.Sequential)]
        private struct ProcThrottleState { public uint Version; public uint ControlMask; public uint StateMask; }

        /// <summary>ecoOn=true 加入 EcoQoS(效率模式); false=清除(恢复常规调度). 返回 null=成功</summary>
        public static string SetProcessEcoQoS(int pid, bool ecoOn)
        {
            IntPtr h = OpenProcess(0x0200, false, pid);   // PROCESS_SET_INFORMATION
            if (h == IntPtr.Zero) return "OpenProcess 失败 (权限不足或进程已退出)";
            try
            {
                ProcThrottleState st = new ProcThrottleState();
                st.Version = 1;
                st.ControlMask = 0x1;                       // PROCESS_POWER_THROTTLING_EXECUTION_SPEED
                st.StateMask = ecoOn ? 0x1u : 0x0u;
                if (!SetProcessInformation(h, 4, ref st, Marshal.SizeOf(typeof(ProcThrottleState))))
                    return "SetProcessInformation 失败 (Win32 错误 " + Marshal.GetLastWin32Error() + ")";
                return null;
            }
            finally { CloseHandle(h); }
        }

        // ================= v6.1: Acer 硬件联动 (EC-WMI, 本机已实测: Profile 写入被接受) =================
        // 接口: root\WMI AcerGamingFunction (实例 ACPI\PNP0C14\APGe_0, Active=True)
        // 已验证: GetGamingProfile/FanBehavior/FanSpeed 只读 OK; SetGamingProfile(2) 返回0=接受
        // 未验证: SetGamingFanSpeed 手动速度编码 (读回不匹配, 不实现)
        // 需管理员权限 (实例枚举/写入)

        private ManagementObject _acerMo;
        private bool _acerTried;

        private ManagementObject GetAcerInstance()
        {
            if (_acerTried) return _acerMo;
            _acerTried = true;
            try
            {
                using (ManagementClass gc = new ManagementClass("root\\WMI", "AcerGamingFunction", null))
                    foreach (ManagementObject i in gc.GetInstances())
                    {
                        _acerMo = i;
                        break;
                    }
            }
            catch { _acerMo = null; }
            return _acerMo;
        }

        public bool AcerAvailable()
        {
            return GetAcerInstance() != null;
        }

        /// 读 Acer 性能配置 (1=安静 2=平衡 3=性能), 失败返回 null
        public int? AcerGetProfile()
        {
            try
            {
                ManagementObject mo = GetAcerInstance();
                if (mo == null) return null;
                using (ManagementBaseObject inP = mo.GetMethodParameters("GetGamingProfile"))
                {
                    inP["gmInput"] = (uint)1;
                    using (ManagementBaseObject o = mo.InvokeMethod("GetGamingProfile", inP, null))
                        return Convert.ToInt32((UInt64)o["gmOutput"]);
                }
            }
            catch { return null; }
        }

        /// 写 Acer 性能配置. 返回 null=成功(返回码0), 否则错误描述
        public string AcerSetProfile(int profile)
        {
            try
            {
                ManagementObject mo = GetAcerInstance();
                if (mo == null) return "Acer WMI 实例不可用 (需管理员)";
                using (ManagementBaseObject inP = mo.GetMethodParameters("SetGamingProfile"))
                {
                    inP["gmInput"] = (UInt64)profile;
                    using (ManagementBaseObject o = mo.InvokeMethod("SetGamingProfile", inP, null))
                    {
                        uint rc = Convert.ToUInt32(o["gmOutput"]);
                        return rc == 0 ? null : ("固件返回码 " + rc);
                    }
                }
            }
            catch (Exception ex) { return ex.Message; }
        }

        /// 读风扇状态 (行为/速度), 失败返回 null
        public int?[] AcerGetFanStatus()
        {
            try
            {
                ManagementObject mo = GetAcerInstance();
                if (mo == null) return null;
                int? beh = null, spd = null;
                using (ManagementBaseObject inP = mo.GetMethodParameters("GetGamingFanBehavior"))
                {
                    inP["gmInput"] = (uint)0;
                    using (ManagementBaseObject o = mo.InvokeMethod("GetGamingFanBehavior", inP, null))
                        beh = Convert.ToInt32((UInt64)o["gmOutput"]);
                }
                using (ManagementBaseObject inP = mo.GetMethodParameters("GetGamingFanSpeed"))
                {
                    inP["gmInput"] = (uint)0;
                    using (ManagementBaseObject o = mo.InvokeMethod("GetGamingFanSpeed", inP, null))
                        spd = Convert.ToInt32((UInt64)o["gmOutput"]);
                }
                return new int?[] { beh, spd };
            }
            catch { return null; }
        }

        // ---- 电源计划 ----
        public List<PowerPlan> ListPowerPlans()
        {
            List<PowerPlan> list = new List<PowerPlan>();
            string output = RunPowerCfg("/list");
            Regex guidRe = new Regex(@"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\s*\((.+?)\)");
            foreach (string line in output.Split('\n'))
            {
                Match m = guidRe.Match(line);
                if (m.Success)
                {
                    PowerPlan p = new PowerPlan();
                    p.Guid = m.Groups[1].Value;
                    p.Name = m.Groups[2].Value.Trim();
                    p.IsActive = line.Contains("*");
                    list.Add(p);
                }
            }
            return list;
        }

        /// 安全运行外部命令: 异步读取双管道+有界超时+超时强杀, 永不死锁.
        /// 返回 stdout; 超时/异常返回 "". stderr 与退出码经输出参数带回.
        public static string RunCapture(string exe, string args, int timeoutMs, out string stderr, out int exitCode)
        {
            stderr = ""; exitCode = -1;
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = exe;
                psi.Arguments = args;
                psi.UseShellExecute = false;
                psi.RedirectStandardOutput = true;
                psi.RedirectStandardError = true;
                psi.CreateNoWindow = true;
                psi.StandardOutputEncoding = System.Text.Encoding.Default;
                using (Process p = Process.Start(psi))
                {
                    string so = "", se = "";
                    p.OutputDataReceived += delegate(object s, DataReceivedEventArgs e) { if (e.Data != null) so += e.Data + "\n"; };
                    p.ErrorDataReceived += delegate(object s, DataReceivedEventArgs e) { if (e.Data != null) se += e.Data + "\n"; };
                    p.BeginOutputReadLine();
                    p.BeginErrorReadLine();
                    bool ok = p.WaitForExit(timeoutMs);
                    if (!ok)
                    {
                        try { p.Kill(); } catch { }
                        try { p.WaitForExit(1000); } catch { }
                        stderr = "超时(" + timeoutMs + "ms)已强制终止";
                        return "";
                    }
                    try { p.WaitForExit(); } catch { }   // 确保异步读取冲刷完成
                    stderr = se ?? "";
                    exitCode = p.ExitCode;
                    return so ?? "";
                }
            }
            catch (Exception ex) { stderr = ex.Message; return ""; }
        }

        public static string RunCapture(string exe, string args, int timeoutMs)
        {
            string err; int code;
            return RunCapture(exe, args, timeoutMs, out err, out code);
        }

        public static string RunPowerCfg(string args)
        {
            return RunCapture("powercfg", args, 5000);
        }

        /// 返回 null=成功, 否则为错误信息
        public static string SwitchPowerPlan(string guid)
        {
            try
            {
                string err; int code;
                RunCapture("powercfg", "/setactive " + guid, 5000, out err, out code);
                if (code != 0)
                    return string.IsNullOrEmpty(err) ? ("powercfg 退出码 " + code + "（可能需要管理员权限）") : err.Trim();
                return null;
            }
            catch (Exception ex) { return ex.Message; }
        }

        public void Dispose()
        {
            CloseLhm();
            try { if (_cpuTotal != null) _cpuTotal.Dispose(); } catch { }
            if (_cpuCores != null) foreach (PerformanceCounter c in _cpuCores) { try { c.Dispose(); } catch { } }
            foreach (PerformanceCounter c in _gpu3D) { try { c.Dispose(); } catch { } }
            // M修复: 补齐原 Dispose 漏掉的计数器
            try { if (_gpuMem != null) _gpuMem.Dispose(); } catch { }
            try { if (_diskBusy != null) _diskBusy.Dispose(); } catch { }
            try { if (_diskBytes != null) _diskBytes.Dispose(); } catch { }
            foreach (PerformanceCounter c in _gpuProcCounters.Values) { try { c.Dispose(); } catch { } }
            foreach (PerformanceCounter c in _diskProcIo.Values) { try { c.Dispose(); } catch { } }
            foreach (PerformanceCounter c in _diskProcId.Values) { try { c.Dispose(); } catch { } }
            foreach (PerformanceCounter c in _netRx.Values) { try { c.Dispose(); } catch { } }
            foreach (PerformanceCounter c in _netTx.Values) { try { c.Dispose(); } catch { } }
        }

        // ---- v3: 性能日志 (CSV, 每30秒一条) ----
        public void LogSample(Snapshot s)
        {
            if (string.IsNullOrEmpty(_logDir) || s == null) return;
            try
            {
                DateTime now = DateTime.Now;
                if ((now - _lastLogTime).TotalSeconds < _logIntervalSec) return;
                _lastLogTime = now;

                string fileName = "perf_" + now.ToString("yyyyMMdd") + ".csv";
                string filePath = Path.Combine(_logDir, fileName);
                bool newFile = !File.Exists(filePath);

                using (StreamWriter sw = new StreamWriter(filePath, true, System.Text.Encoding.UTF8))
                {
                    if (newFile)
                    {
                        sw.WriteLine("时间,CPU%,内存%,内存已用MB,内存总量MB,GPU3D%,磁盘繁忙%,磁盘KB/s,电池%,电源计划,CPU频率MHz,CPU温度°C,CPU功耗W,电池温度°C,电池健康度%,充电mW,放电mW");
                    }
                    sw.Write(now.ToString("HH:mm:ss"));
                    sw.Write("," + s.CpuTotal.ToString("F1"));
                    sw.Write("," + s.MemUsedPct.ToString("F1"));
                    sw.Write("," + s.MemUsedMB);
                    sw.Write("," + s.MemTotalMB);
                    sw.Write("," + (s.Gpu3D.HasValue ? s.Gpu3D.Value.ToString("F1") : ""));
                    sw.Write("," + s.DiskBusy.ToString("F1"));
                    sw.Write("," + (s.DiskBytesPerSec / 1024).ToString("F0"));
                    sw.Write("," + (s.BatteryPct >= 0 ? s.BatteryPct.ToString() : ""));
                    sw.Write("," + (string.IsNullOrEmpty(s.ActivePlanName) ? "" : s.ActivePlanName));
                    sw.Write("," + (s.CpuFreqMHz.HasValue ? s.CpuFreqMHz.Value.ToString() : ""));
                    sw.Write("," + (s.LhmCpuTempBest.HasValue ? s.LhmCpuTempBest.Value.ToString("F1") : ""));
                    sw.Write("," + (s.LhmCpuPowerW.HasValue ? s.LhmCpuPowerW.Value.ToString("F2") : ""));
                    sw.Write("," + (s.BatteryTempC.HasValue ? s.BatteryTempC.Value.ToString("F1") : ""));
                    sw.Write("," + (s.BatteryHealthPct.HasValue ? s.BatteryHealthPct.Value.ToString("F0") : ""));
                    sw.Write("," + (s.BatteryChargeRateMW.HasValue ? s.BatteryChargeRateMW.Value.ToString() : ""));
                    sw.WriteLine("," + (s.BatteryDischargeRateMW.HasValue ? s.BatteryDischargeRateMW.Value.ToString() : ""));
                }
            }
            catch { }
        }

        // ---- v3.2: 充电阶段检测 (CC/CV) ----
        private void DetectChargePhase(Snapshot s)
        {
            if (!s.BatteryVoltageV.HasValue || !s.BatteryChargeRateMW.HasValue)
            { s.BatteryChargePhase = "--"; return; }

            // 记录历史
            _voltageHistory.Add(s.BatteryVoltageV.Value);
            if (_voltageHistory.Count > 5) _voltageHistory.RemoveAt(0);

            float curMA = s.BatteryVoltageV.Value > 0 ? s.BatteryChargeRateMW.Value / s.BatteryVoltageV.Value : 0;
            _currentHistory.Add(curMA);
            if (_currentHistory.Count > 5) _currentHistory.RemoveAt(0);

            if (_voltageHistory.Count < 3 || _currentHistory.Count < 3)
            { s.BatteryChargePhase = "CC"; return; } // 默认假设恒流

            // 电压趋势: 上升 → CC, 稳定/微降 → CV
            float vFirst = _voltageHistory[0];
            float vLast = _voltageHistory[_voltageHistory.Count - 1];
            float vDelta = vLast - vFirst;

            // 电流趋势: 下降 → CV, 稳定 → CC
            float cFirst = _currentHistory[0];
            float cLast = _currentHistory[_currentHistory.Count - 1];
            float cDelta = cLast - cFirst;

            if (vDelta > 0.02f && Math.Abs(cDelta) < cFirst * 0.1f)
                s.BatteryChargePhase = "CC";  // 电压上升 + 电流稳定 = 恒流
            else if (vDelta < 0.01f && cDelta < -cFirst * 0.15f)
                s.BatteryChargePhase = "CV";  // 电压稳定 + 电流下降 = 恒压
            else
                s.BatteryChargePhase = "CC"; // 默认
        }

        // ---- v3.2: 健康度趋势 (简单线性回归) ----
        private void UpdateHealthTrend(Snapshot s)
        {
            if (!s.BatteryHealthPct.HasValue) return;
            float hp = s.BatteryHealthPct.Value;
            // H4修复: 仅在健康度变化或距上次>30min时记录, 使历史跨度达到天级 (原每秒采样只回归出噪声)
            if (_healthHistory.Count > 0)
            {
                float last = _healthHistory[_healthHistory.Count - 1];
                if (Math.Abs(last - hp) < 0.05f && (DateTime.Now - _healthTimes[_healthTimes.Count - 1]).TotalMinutes <= 30)
                { s.BatteryHealthSlope = _lastSlope; return; }
            }
            _healthHistory.Add(hp);
            _healthTimes.Add(DateTime.Now);
            if (_healthHistory.Count > 20) { _healthHistory.RemoveAt(0); _healthTimes.RemoveAt(0); }

            if (_healthHistory.Count < 3) { s.BatteryHealthSlope = 0; _lastSlope = 0; return; }

            // 最小二乘线性回归: y = a + bx, x = 距首个采样的天数 (H4: 原为采样序号, 单位失真)
            int n = _healthHistory.Count;
            float sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
            DateTime t0 = _healthTimes[0];
            for (int i = 0; i < n; i++)
            {
                float x = (float)(ulong)_healthTimes[i].Subtract(t0).TotalDays; float y = _healthHistory[i];
                sumX += x; sumY += y; sumXY += x * y; sumX2 += x * x;
            }
            float denom = n * sumX2 - sumX * sumX;
            if (Math.Abs(denom) < 0.001f) { s.BatteryHealthSlope = 0; _lastSlope = 0; return; }
            _lastSlope = (n * sumXY - sumX * sumY) / denom;   // %/天
            s.BatteryHealthSlope = _lastSlope;
        }
        private float _lastSlope;

        // ---- v3.1: 应用功耗排行 (Top-N by CPU) ----
        private void CollectTopProcesses(Snapshot s)
        {
            try
            {
                Process[] procs = Process.GetProcesses();
                List<ProcessPowerInfo> list = new List<ProcessPowerInfo>();
                foreach (Process p in procs)
                {
                    try
                    {
                        string name = p.ProcessName;
                        int pid = p.Id;
                        float cpu = 0;
                        try { cpu = (float)(p.TotalProcessorTime.TotalMilliseconds / 1000.0); } catch { }
                        long mem = 0;
                        try { mem = p.WorkingSet64 / (1024 * 1024); } catch { }
                        if (cpu > 0 || mem > 10)
                            list.Add(new ProcessPowerInfo { Name = name, Pid = pid, CpuPct = cpu, MemMB = mem });
                    }
                    catch { }
                }
                foreach (Process p in procs) { try { p.Dispose(); } catch { } }   // M: 每 tick 数百个 Process 句柄不再悬空
                list.Sort(delegate(ProcessPowerInfo a, ProcessPowerInfo b) { return b.CpuPct.CompareTo(a.CpuPct); });
                if (list.Count > 15) list.RemoveRange(15, list.Count - 15);
                s.TopProcesses = list;
            }
            catch { }
        }

        // ---- v3.3: 系统维护信息 ----
        private void CollectMaintenanceInfo(Snapshot s)
        {
            // 内核版本
            try
            {
                using (ManagementObjectSearcher searcher = new ManagementObjectSearcher("SELECT Caption FROM Win32_OperatingSystem"))
                {
                    foreach (ManagementObject o in searcher.Get())
                    {
                        s.KernelVersion = (o["Caption"] as string) ?? "";
                        break;
                    }
                }
            }
            catch { }

            // 关键服务状态
            string[] svcNames = new string[] { "Spooler", "WSearch", "Themes", "WinDefend", "wuauserv", "Schedule", "Dhcp" };
            string[] svcDisplay = new string[] { "打印队列", "Windows Search", "主题", "Windows Defender", "Windows Update", "任务计划", "DHCP Client" };
            for (int i = 0; i < svcNames.Length; i++)
            {
                ServiceInfo svc = new ServiceInfo();
                svc.Name = svcNames[i];
                svc.DisplayName = svcDisplay[i];
                svc.Status = "NotFound";
                try
                {
                    using (ManagementObjectSearcher searcher = new ManagementObjectSearcher(
                        "SELECT State FROM Win32_Service WHERE Name='" + svcNames[i] + "'"))
                    {
                        foreach (ManagementObject o in searcher.Get())
                        {
                            svc.Status = (o["State"] as string) ?? "Unknown";
                            break;
                        }
                    }
                }
                catch { }
                s.Services.Add(svc);
            }

            // 启动项 (HKCU Run + HKLM Run)
            try
            {
                List<string> items = new List<string>();
                using (Microsoft.Win32.RegistryKey key = Microsoft.Win32.Registry.CurrentUser.OpenSubKey("Software\\Microsoft\\Windows\\CurrentVersion\\Run"))
                {
                    if (key != null)
                        foreach (string name in key.GetValueNames())
                            if (!string.IsNullOrEmpty(name)) items.Add("[用户] " + name);
                }
                using (Microsoft.Win32.RegistryKey key = Microsoft.Win32.Registry.LocalMachine.OpenSubKey("Software\\Microsoft\\Windows\\CurrentVersion\\Run"))
                {
                    if (key != null)
                        foreach (string name in key.GetValueNames())
                            if (!string.IsNullOrEmpty(name)) items.Add("[系统] " + name);
                }
                s.StartupItems = items.ToArray();
            }
            catch { }
        }
    }

    internal static class WinAPI
    {
        [DllImport("user32.dll")]
        internal static extern bool SetProcessDPIAware();
    }
}
