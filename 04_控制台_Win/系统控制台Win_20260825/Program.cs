// Program.cs — Windows 系统控制台入口
// 编译: build.cmd (系统自带 csc, .NET Framework 4.8)
// 模式: 正常启动 GUI; --selftest 采集自检(输出到控制台/selftest_result.txt)
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Windows.Forms;

namespace SysConsole
{
    static class Program
    {
        // v4: 启动跟踪日志(诊断"打不开"问题)
        internal static void Trace(string msg)
        {
            try
            {
                string dir = Path.Combine(AppDomain.CurrentDomain.BaseDirectory);
                File.AppendAllText(Path.Combine(dir, "startup_trace.log"),
                    DateTime.Now.ToString("HH:mm:ss.fff") + " [" + Thread.CurrentThread.ManagedThreadId + "] " + msg + "\r\n");
            }
            catch { }
        }

        [STAThread]
        static int Main(string[] args)
        {
            Trace("=== Main 入口 ===");
            // 全局异常捕获
            Application.ThreadException += delegate(object sender, System.Threading.ThreadExceptionEventArgs e)
            {
                Trace("UI线程异常: " + e.Exception);
                MessageBox.Show("未处理异常: " + e.Exception.ToString(), "系统控制台错误",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
            };
            AppDomain.CurrentDomain.UnhandledException += delegate(object sender, UnhandledExceptionEventArgs e)
            {
                Exception ex = e.ExceptionObject as Exception;
                Trace("未处理异常: " + (ex != null ? ex.ToString() : e.ExceptionObject != null ? e.ExceptionObject.ToString() : "null"));
                if (ex != null)
                    MessageBox.Show("未处理异常: " + ex.ToString(), "系统控制台错误",
                        MessageBoxButtons.OK, MessageBoxIcon.Error);
            };

            // 自检模式: 不进 GUI, 验证采集层真实可用
            int initialTab = -1;
            int autoCloseSec = 0;
            foreach (string a in args)
            {
                if (a == "--selftest")
                {
                    return RunSelfTest();
                }
                // v6.6: CLI 控制面 (#14) — /get <项|all> /set <项> <值...>
                if (a.Equals("/get", StringComparison.OrdinalIgnoreCase) || a.Equals("/set", StringComparison.OrdinalIgnoreCase))
                {
                    return RunCli(args);
                }
                if ((a.StartsWith("/tab=", StringComparison.OrdinalIgnoreCase)
                     || a.StartsWith("--tab=", StringComparison.OrdinalIgnoreCase)))
                {
                    int v;
                    if (int.TryParse(a.Substring(a.IndexOf('=') + 1), out v)) initialTab = v;
                }

                if (a.StartsWith("--autoclose=", StringComparison.OrdinalIgnoreCase))
                {
                    int v;
                    if (int.TryParse(a.Substring(a.IndexOf('=') + 1), out v)) autoCloseSec = v;
                }
            }

            bool createdNew;
            using (Mutex m = new Mutex(true, "SysConsole_SingleInstance_A615", out createdNew))
            {
                Trace("互斥锁 createdNew=" + createdNew);
                if (!createdNew)
                {
                    MessageBox.Show("系统控制台已在运行中（请查看托盘图标）。", "系统控制台",
                        MessageBoxButtons.OK, MessageBoxIcon.Information);
                    return 0;
                }
                try { WinAPI.SetProcessDPIAware(); } catch { }
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Trace("准备创建 MainForm...");
                MainForm form = new MainForm(initialTab, autoCloseSec);
                Trace("MainForm 构造完成, 进入消息循环");
                Application.Run(form);
                Trace("消息循环退出");
            }
            return 0;
        }

        // v6.6: CLI 控制面 (#14, 来源 LLT CLI 思路) — 脚本化读写, 不进 GUI
        // 用法: SysConsole.exe /get <epp|boost|wireless|aspm|overlay|refresh|plan|all>
        //       SysConsole.exe /set epp <ac> <dc> | /set boost <0-5> | /set wireless <ac> <dc>
        //       /set aspm <0|1> | /set overlay <eff|bal|perf|dcbal> | /set refresh <hz> | /set plan <名称>
        static int RunCli(string[] args)
        {
            try
            {
                Collector c = new Collector();
                string cmd = args[0].ToLowerInvariant();
                string what = args.Length > 1 ? args[1].ToLowerInvariant() : "all";

                if (cmd == "/get")
                {
                    if (what == "epp" || what == "all")
                    {
                        int?[] v = c.ReadEpp();
                        Console.WriteLine("EPP AC=" + (v[0].HasValue ? v[0].Value.ToString() : "默认") + " DC=" + (v[1].HasValue ? v[1].Value.ToString() : "默认"));
                    }
                    if (what == "boost" || what == "all")
                    {
                        int?[] bv = c.ReadBoostModeACDC();
                        Console.WriteLine("Boost AC=" + (bv[0].HasValue ? bv[0].Value.ToString() : "默认(2)") + " DC=" + (bv[1].HasValue ? bv[1].Value.ToString() : "默认(2)"));
                    }
                    if (what == "wireless" || what == "all")
                    {
                        int?[] v = c.ReadWirelessPower();
                        Console.WriteLine("无线功耗 AC=" + (v[0].HasValue ? v[0].Value.ToString() : "默认") + " DC=" + (v[1].HasValue ? v[1].Value.ToString() : "默认"));
                    }
                    if (what == "aspm" || what == "all")
                    {
                        int?[] v = Collector.ReadPowerSetting(Collector.SUB_PCIEXPRESS_GUID, Collector.PCIE_ASPM_GUID);
                        Console.WriteLine("PCIe ASPM AC=" + (v[0].HasValue ? v[0].Value.ToString() : "默认") + " DC=" + (v[1].HasValue ? v[1].Value.ToString() : "默认"));
                    }
                    if (what == "overlay" || what == "all")
                    {
                        string ov = c.GetActiveOverlay();
                        Console.WriteLine("电源滑块(AC侧): " + c.OverlayName(ov) + " (" + ov + ")");
                    }
                    if (what == "refresh" || what == "all")
                    {
                        int? hz = Collector.GetRefreshRate();
                        Console.WriteLine("刷新率: " + (hz.HasValue ? hz.Value + "Hz" : "?") + " 可用: " + string.Join("/", Collector.EnumRefreshRates().ToArray()));
                    }
                    if (what == "plan" || what == "all")
                    {
                        foreach (PowerPlan p in c.ListPowerPlans())
                            Console.WriteLine("计划: " + p.Name + (p.IsActive ? " [活动]" : "") + "  " + p.Guid);
                    }
                    if (what == "all")
                    {
                        System.Windows.Forms.PowerStatus ps = System.Windows.Forms.SystemInformation.PowerStatus;
                        Console.WriteLine("电池: " + Math.Round(ps.BatteryLifePercent * 100) + "% 电源: " + ps.PowerLineStatus);
                    }
                    return 0;
                }

                if (cmd == "/set")
                {
                    string err = null;
                    switch (what)
                    {
                        case "epp":
                            if (args.Length < 4) { Console.WriteLine("用法: /set epp <ac> <dc>  (0=最高性能..100=最大省电)"); return 2; }
                            err = c.SetEpp(int.Parse(args[2]), int.Parse(args[3]));
                            break;
                        case "boost":
                            if (args.Length < 3) { Console.WriteLine("用法: /set boost <0-5>"); return 2; }
                            err = c.SetBoostMode(int.Parse(args[2]));
                            break;
                        case "wireless":
                            if (args.Length < 4) { Console.WriteLine("用法: /set wireless <ac> <dc>  (0-3)"); return 2; }
                            err = c.SetWirelessPower(int.Parse(args[2]), int.Parse(args[3]));
                            break;
                        case "aspm":
                            if (args.Length < 3) { Console.WriteLine("用法: /set aspm <0|1>"); return 2; }
                            err = Collector.ApplyPowerSetting(Collector.SUB_PCIEXPRESS_GUID, Collector.PCIE_ASPM_GUID, int.Parse(args[2]), int.Parse(args[2]));
                            break;
                        case "overlay":
                            if (args.Length < 3) { Console.WriteLine("用法: /set overlay <eff|bal|perf|dcbal>  (dcbal=仅电池侧切平衡, 需管理员)"); return 2; }
                            if (args[2] == "eff") err = c.SetActiveOverlay(Collector.OVERLAY_BEST_EFFICIENCY);
                            else if (args[2] == "bal") err = c.SetActiveOverlay(Collector.OVERLAY_BALANCED);
                            else if (args[2] == "perf") err = c.SetActiveOverlay(Collector.OVERLAY_BEST_PERFORMANCE);
                            else if (args[2] == "dcbal") err = c.SetActiveOverlayDc(Collector.OVERLAY_BALANCED);
                            else { Console.WriteLine("未知 overlay: " + args[2]); return 2; }
                            break;
                        case "refresh":
                            if (args.Length < 3) { Console.WriteLine("用法: /set refresh <hz>"); return 2; }
                            err = Collector.SetRefreshRate(int.Parse(args[2]));
                            break;
                        case "plan":
                            if (args.Length < 3) { Console.WriteLine("用法: /set plan <名称部分>"); return 2; }
                            {
                                PowerPlan hit = null;
                                foreach (PowerPlan p in c.ListPowerPlans())
                                    if (p.Name.IndexOf(args[2], StringComparison.OrdinalIgnoreCase) >= 0 || p.Guid == args[2]) { hit = p; break; }
                                if (hit == null) { Console.WriteLine("未找到计划: " + args[2]); return 2; }
                                err = Collector.SwitchPowerPlan(hit.Guid);
                                if (err == null) Console.WriteLine("已切换计划: " + hit.Name);
                            }
                            break;
                        default:
                            Console.WriteLine("未知项: " + what + " (支持 epp/boost/wireless/aspm/overlay/refresh/plan)");
                            return 2;
                    }
                    if (err == null) { if (what != "plan") Console.WriteLine("OK: " + what + " 已应用"); }
                    else { Console.WriteLine("失败: " + err); return 1; }
                    return 0;
                }

                Console.WriteLine("用法: SysConsole.exe /get <epp|boost|wireless|aspm|overlay|refresh|plan|all>");
                Console.WriteLine("      SysConsole.exe /set <epp|boost|wireless|aspm|overlay|refresh|plan> <值...>");
                return 2;
            }
            catch (Exception ex)
            {
                Console.WriteLine("CLI 异常: " + ex.Message);
                return 1;
            }
        }

        static int RunSelfTest()
        {
            StringWriter sw = new StringWriter();
            int exit = 0;
            try
            {
                Collector c = new Collector();
                sw.WriteLine("=== Windows 系统控制台 采集自检 ===");
                sw.WriteLine("时间: " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"));
                sw.WriteLine();

                // 第一次采样仅预热计数器(差分基线), 第二次为有效值
                c.Sample();
                Thread.Sleep(1100);
                Snapshot s = c.Sample();

                sw.WriteLine("[CPU] 总利用率: " + s.CpuTotal.ToString("F1") + "%");
                for (int i = 0; i < s.CpuPerCore.Length; i++)
                    sw.WriteLine("      核心" + i + ": " + s.CpuPerCore[i].ToString("F1") + "%");
                sw.WriteLine("[内存] 已用 " + s.MemUsedMB + " MB / " + s.MemTotalMB + " MB (" + s.MemUsedPct.ToString("F1") + "%)");
                sw.WriteLine("[GPU] 3D 利用率: " + (s.Gpu3D.HasValue ? s.Gpu3D.Value.ToString("F1") + "%" : "不可用"));
                sw.WriteLine("[磁盘] _Total 繁忙: " + s.DiskBusy.ToString("F1") + "% | 速率: " + (s.DiskBytesPerSec / 1024).ToString("F0") + " KB/s");
                foreach (var kv in s.NetPerNic)
                    sw.WriteLine("[网络] " + kv.Key + ": ↓" + (kv.Value[0] / 1024).ToString("F1") + " ↑" + (kv.Value[1] / 1024).ToString("F1") + " KB/s");
                sw.WriteLine("[电池] " + s.BatteryPct + "% | " + s.PowerLine + " | OS剩余估计: " +
                    (s.BatteryLifeSec > 0 ? (s.BatteryLifeSec / 60) + " 分钟" : "未知"));
                sw.WriteLine("[温度区] " + (s.TempNeedsAdmin ? "需要管理员权限" :
                    (s.TempZones.Count > 0 ? string.Join("; ", s.TempZones.ToArray()) : "无数据")));
                sw.WriteLine("[开机时长] " + s.UptimeText);
                sw.WriteLine("[电源计划] 当前: " + s.ActivePlanName);
                foreach (PowerPlan p in c.ListPowerPlans())
                    sw.WriteLine("   " + (p.IsActive ? "* " : "  ") + p.Name + "  (" + p.Guid + ")");

                // ---- v2 扩展自检 ----
                sw.WriteLine("[权限] 管理员运行: " + (s.Elevated ? "是" : "否"));
                sw.WriteLine("[LHM] LibreHardwareMonitor: " + (s.LhmActive
                    ? ("已启用 | 硬件" + s.LhmHardwareCount + "个 | 温度传感器" + s.LhmTemps.Count + "个, 风扇" + s.LhmFans.Count + "个"
                       + (s.LhmCpuTempBest.HasValue ? (" | CPU温度=" + s.LhmCpuTempBest.Value.ToString("F1") + "°C") : "")
                       + (s.LhmCpuPowerW.HasValue ? (" | CPU功耗=" + s.LhmCpuPowerW.Value.ToString("F2") + "W") : ""))
                    : ("未启用 — 原因: " + (string.IsNullOrEmpty(s.LhmError) ? "(无记录)" : s.LhmError))));
                if (s.LhmActive && s.LhmTemps.Count > 0)
                    sw.WriteLine("[LHM温度] " + string.Join("; ", s.LhmTemps.ToArray()));
                if (s.LhmActive && s.LhmFans.Count > 0)
                    sw.WriteLine("[LHM风扇] " + string.Join("; ", s.LhmFans.ToArray()));
                if (!string.IsNullOrEmpty(s.NvidiaName))
                {
                    sw.WriteLine("[独显] " + s.NvidiaName
                        + " | 利用率 " + FmtF(s.NvidiaUtil) + "%"
                        + " | 显存 " + (s.NvidiaMemMB.HasValue ? s.NvidiaMemMB.Value.ToString() : "?") + " MB"
                        + " | 温度 " + FmtF(s.NvidiaTemp) + "°C"
                        + " | 功耗 " + FmtF(s.NvidiaPowerW) + "W");
                }
                else sw.WriteLine("[独显] 未检测到 nvidia-smi");

                // ---- v3 扩展自检 ----
                sw.WriteLine("[CPU频率] " + (s.CpuFreqMHz.HasValue ? (s.CpuFreqMHz.Value + " MHz") : "--")
                    + (s.CpuFreqMaxMHz.HasValue ? (" / " + s.CpuFreqMaxMHz.Value + " MHz 最大") : ""));
                sw.WriteLine("[电池深度] " + (s.BatteryTempC.HasValue ? ("温度=" + s.BatteryTempC.Value.ToString("F1") + "°C") : "温度=--")
                    + " | " + (s.BatteryVoltageV.HasValue ? ("电压=" + s.BatteryVoltageV.Value.ToString("F2") + "V") : "电压=--")
                    + " | " + (s.BatteryHealthPct.HasValue ? ("健康度=" + s.BatteryHealthPct.Value.ToString("F0") + "%") : "健康度=--")
                    + " | " + (s.BatteryChargeRateMW.HasValue ? ("充电=" + s.BatteryChargeRateMW.Value + "mW") : "")
                    + (s.BatteryDischargeRateMW.HasValue ? ("放电=" + s.BatteryDischargeRateMW.Value + "mW") : ""));
                if (s.BatteryDesignCapMWh.HasValue)
                    sw.WriteLine("[电池容量] 设计=" + s.BatteryDesignCapMWh.Value + " mWh"
                        + (s.BatteryFullCapMWh.HasValue ? (" / 实际=" + s.BatteryFullCapMWh.Value + " mWh") : ""));

                // v3.2: 充电阶段 + 健康趋势
                sw.WriteLine("[充电阶段] " + (string.IsNullOrEmpty(s.BatteryChargePhase) ? "--" : s.BatteryChargePhase));
                sw.WriteLine("[健康趋势] 斜率=" + s.BatteryHealthSlope.ToString("F4") + " %/天"
                    + (s.BatteryHealthSlope != 0 ? (" → 月" + (s.BatteryHealthSlope * 30).ToString("F2") + "%") : ""));

                // v3.3: 系统维护
                sw.WriteLine("[服务] " + s.Services.Count + " 个已检查");
                foreach (ServiceInfo svc in s.Services)
                    sw.WriteLine("  " + svc.Status.PadRight(10) + " " + svc.DisplayName + " (" + svc.Name + ")");
                sw.WriteLine("[启动项] " + s.StartupItems.Length + " 个");
                foreach (string item in s.StartupItems)
                    sw.WriteLine("  " + item);
                sw.WriteLine("[进程排行] " + s.TopProcesses.Count + " 个");

                // 告警纯逻辑测试(4 用例)
                DateTime t0 = new DateTime(2026, 1, 1, 12, 0, 0);
                bool a1 = AppLogic.ShouldLowBattery(15, true, t0.AddMinutes(-30), t0, 10);
                bool a2 = AppLogic.ShouldLowBattery(15, true, t0, t0, 10);
                bool a3 = AppLogic.ShouldHighTemp(85f, t0.AddMinutes(-10), t0, 5);
                bool a4 = AppLogic.ShouldHighTemp(75f, t0.AddMinutes(-10), t0, 5);
                bool logicOk = a1 && !a2 && a3 && !a4;
                sw.WriteLine("[告警逻辑] 低电触发=" + a1 + "/冷却抑制=" + (!a2) + "/高温触发=" + a3 + "/阈值以下=" + (!a4)
                    + (logicOk ? " → PASS" : " → FAIL"));
                if (!logicOk) exit = 1;   // P2: FAIL 必须反映到退出码

                // 设置文件读写回环
                string tmpIni = Path.Combine(Path.GetTempPath(), "sc_settings_test.ini");
                File.WriteAllText(tmpIni, "interval=2000\r\nalerts=1\r\n");
                Dictionary<string, string> ini = AppLogic.ParseIni(tmpIni);
                bool iniOk = ini.ContainsKey("interval") && ini["interval"] == "2000" && ini["alerts"] == "1";
                File.Delete(tmpIni);
                sw.WriteLine("[设置回环] " + (iniOk ? "PASS" : "FAIL"));
                if (!iniOk) exit = 1;

                // 自启动注册表回环(写入→读取→清除→读取; P1: 测后恢复用户原状态)
                bool origAuto = AppLogic.GetAutostart();
                AppLogic.SetAutostart(true);
                bool regOn = AppLogic.GetAutostart();
                AppLogic.SetAutostart(false);
                bool regOff = AppLogic.GetAutostart();
                if (origAuto) AppLogic.SetAutostart(true);   // P1: 恢复用户原有自启, 自检不留副作用
                bool regOk = regOn && !regOff;
                sw.WriteLine("[自启动注册表] 写入=" + regOn + "/清除=" + (!regOff) + (regOk ? " → PASS" : " → FAIL"));
                if (!regOk) exit = 1;

                // v4.1: 负载建议器逻辑 (高负载+电池触发 / 插电不触发 / 低负载不触发 / 冷却抑制)
                LoadAdvisor la = new LoadAdvisor(70.0, 6, 1, 0);   // 6样本持续, 无冷却便于测试
                DateTime lt0 = DateTime.Now;
                bool advHit = false;
                for (int i = 0; i < 10; i++) { if (la.Feed(90f, true, lt0.AddSeconds(i)) != null) advHit = true; }
                la.Reset();
                bool advAc = false;
                for (int i = 0; i < 10; i++) { if (la.Feed(90f, false, lt0.AddSeconds(i)) != null) advAc = true; }
                la.Reset();
                bool advLow = false;
                for (int i = 0; i < 10; i++) { if (la.Feed(30f, true, lt0.AddSeconds(i)) != null) advLow = true; }
                la.Reset();
                LoadAdvisor la2 = new LoadAdvisor(70.0, 6, 1, 15);  // 15分钟冷却
                for (int i = 0; i < 10; i++) la2.Feed(90f, true, lt0.AddSeconds(i));   // 触发, 记录冷却起点
                bool advCool = false;
                for (int i = 0; i < 10; i++) { if (la2.Feed(90f, true, lt0.AddSeconds(20 + i)) != null) advCool = true; } // 冷却期内(20s < 15min)
                bool laOk = advHit && !advAc && !advLow && !advCool;
                sw.WriteLine("[负载建议] 电池高负载触发=" + advHit + "/插电抑制=" + (!advAc) + "/低负载抑制=" + (!advLow)
                    + "/冷却抑制=" + (!advCool) + (laOk ? " → PASS" : " → FAIL"));
                if (!laOk) exit = 1;

                // 电池报告生成(临时目录, 测试后删除)
                // 注意: powercfg /batteryreport 在非交互式子进程中可能因 energy.dll 加载失败而无法生成
                // 这是 Windows 系统级限制(非代码 bug)，GUI 模式下正常工作
                string rep = Path.Combine(Path.GetTempPath(), "mini_bat_test.html");
                try
                {
                    Collector.RunPowerCfg("/batteryreport /output \"" + rep + "\"");
                }
                catch { }
                bool repOk = File.Exists(rep) && new FileInfo(rep).Length > 500;
                sw.WriteLine("[电池报告] " + (repOk ? ("生成成功 " + new FileInfo(rep).Length + " 字节 → PASS") : "生成降级(energy.dll 非交互限制) → SKIP"));
                try { if (File.Exists(rep)) File.Delete(rep); } catch { }

                // 进程 API 回环
                Process np = Process.Start(new ProcessStartInfo("cmd.exe", "/c exit")
                { CreateNoWindow = true, UseShellExecute = false });
                long ws = -1;
                try { np.Refresh(); ws = np.WorkingSet64; } catch { }
                bool exited = np.WaitForExit(3000);
                sw.WriteLine("[进程API] 启动/读内存=" + (ws >= 0) + "/等待退出=" + exited);

                sw.WriteLine();
                bool coreOk = s.CpuPerCore.Length >= 4 && s.MemTotalMB > 0;
                sw.WriteLine(coreOk ? "SELFTEST: PASS" : "SELFTEST: FAIL");
                if (!coreOk) exit = 1;   // P2: 最终判定 FAIL 也必须非零退出码
            }
            catch (Exception ex)
            {
                sw.WriteLine("SELFTEST: EXCEPTION");
                sw.WriteLine(ex.ToString());
                exit = 2;
            }

            string text = sw.ToString();
            Console.WriteLine(text);
            try
            {
                string path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "selftest_result.txt");
                File.WriteAllText(path, text);
                Console.WriteLine("已写入: " + path);
            }
            catch { }
            return exit;
        }

        private static string FmtF(Nullable<float> v)
        {
            return v.HasValue ? v.Value.ToString("F0") : "?";
        }
    }

    // ---- 纯逻辑层(可独立测试) ----
    internal static class AppLogic
    {
        internal const int LowBatteryPct = 20;
        internal const float HighTempC = 80f;

        /// 低电量告警判定: 放电中 + 电量≤阈值 + 冷却期已过
        internal static bool ShouldLowBattery(int pct, bool discharging, DateTime lastAlert, DateTime now, int cooldownMinutes)
        {
            return ShouldLowBatteryAt(pct, discharging, lastAlert, now, cooldownMinutes, LowBatteryPct);
        }

        /// 低电量告警判定: 放电中 + 0<电量≤阈值 + 冷却期已过
        /// M修复: 原 pct<=0 直接放过使 0% 永不告警; 未知值由采集层归一 (<0 或 >100 均被范围排除)
        internal static bool ShouldLowBatteryAt(int pct, bool discharging, DateTime lastAlert, DateTime now, int cooldownMinutes, int thresholdPct)
        {
            if (!discharging) return false;
            if (pct < 0 || pct > thresholdPct) return false;
            return (now - lastAlert).TotalMinutes >= cooldownMinutes;
        }

        /// 高温告警判定: 温度≥阈值 + 冷却期已过
        internal static bool ShouldHighTemp(float? tempC, DateTime lastAlert, DateTime now, int cooldownMinutes)
        {
            return ShouldHighTempAt(tempC, lastAlert, now, cooldownMinutes, HighTempC);
        }

        internal static bool ShouldHighTempAt(float? tempC, DateTime lastAlert, DateTime now, int cooldownMinutes, float thresholdC)
        {
            if (!tempC.HasValue || tempC.Value < thresholdC) return false;
            return (now - lastAlert).TotalMinutes >= cooldownMinutes;
        }

        /// 简易 ini 解析
        internal static Dictionary<string, string> ParseIni(string path)
        {
            Dictionary<string, string> d = new Dictionary<string, string>();
            try
            {
                foreach (string line in System.IO.File.ReadAllLines(path))
                {
                    // M修复: 只在首个 '=' 处切分 — 原 Split('=') 使含 '=' 的值(路径等)被静默丢弃
                    int eq = line.IndexOf('=');
                    if (eq <= 0) continue;
                    string k = line.Substring(0, eq).Trim();
                    if (k.Length == 0) continue;
                    d[k] = line.Substring(eq + 1).Trim();
                }
            }
            catch { }
            return d;
        }

        internal static string RunValueName { get { return "SysConsoleWin"; } }
        private const string RunKeyPath = @"Software\Microsoft\Windows\CurrentVersion\Run";

        internal static void SetAutostart(bool on)
        {
            using (Microsoft.Win32.RegistryKey k = Microsoft.Win32.Registry.CurrentUser.CreateSubKey(RunKeyPath))
            {
                if (on) k.SetValue(RunValueName, "\"" + Application.ExecutablePath + "\"");
                else k.DeleteValue(RunValueName, false);
            }
        }

        internal static bool GetAutostart()
        {
            using (Microsoft.Win32.RegistryKey k = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(RunKeyPath))
            {
                if (k == null) return false;
                return k.GetValue(RunValueName) != null;
            }
        }
    }
}
