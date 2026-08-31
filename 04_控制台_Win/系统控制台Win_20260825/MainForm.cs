// MainForm.cs — Windows 系统控制台 UI 层
// 四页: 总览 / 电源 / 进程 / 系统 + 托盘常驻 + 自适应采样(前台1s/失焦5s)
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

namespace SysConsole
{
    public class MainForm : Form
    {
        private readonly Collector _collector = new Collector();
        private System.Windows.Forms.Timer _timer;
        private Snapshot _last;
        private bool _reallyExit;
        private int _tickCount;

        // ---- 控件引用 ----
        private TabControl _tabs;
        private Label _lblCpuVal, _lblMemVal, _lblGpuVal, _lblBatVal;
        private ProgressBar[] _coreBars;
        private Label _lblDiskIo, _lblNet, _lblTemp, _lblUptime, _lblPlanNow;
        private CurvePanel _cpuCurve, _memCurve;
        private CurvePanel _netCurve, _gpuCurve;   // v5
        private ListBox _planList;
        private Button _btnSwitchPlan, _btnBatteryReport;
        private Label _lblBatteryDetail;
        private ListView _procList;
        private Button _btnKillProc;
        private TextBox _txtSysInfo;
        private ProcSorter _sorter = new ProcSorter();
        private Dictionary<int, object[]> _prevProcCpu = new Dictionary<int, object[]>(); // pid -> [TimeSpan, DateTime]
        private DateTime _lastProcRefresh = DateTime.MinValue;
        // ---- v2 ----
        private CheckBox _chkAutostart, _chkAlerts;
        private ComboBox _cboInterval;
        private bool _loadingUi = true;
        private bool _alertsEnabled = true;
        private int _baseIntervalMs = 1000;
        private Label _lblNvidia;
        private DateTime _lastLowBatAlert = DateTime.MinValue;
        private DateTime _lastHighTempAlert = DateTime.MinValue;
        // ---- v3: CPU 频率 + 电池深度 + 充电曲线 + 场景切换 ----
        private Label _lblCpuFreq, _lblBatDeep;
        private DualAxisCurvePanel _chargeCurve;
        private ToolStrip _toolStrip;
        private ToolStripComboBox _cboScenePlans;
        private ToolStripLabel _lblPowerBadge;
        // ---- v4: 可配置布局 + 电池分析 ----
        private Panel _overviewCpuBox, _overviewMemBox, _overviewCoreBox, _overviewMemBarBox, _overviewDetailBox;
        private bool[] _moduleVisible = new bool[] { true, true, true, true, true }; // CPU曲线/内存曲线/每核/内存条/明细
        private TextBox _txtBatteryAnalysis;
        // ---- v4.1: AC/DC 自动切换 + 负载建议 + 托盘增强 (移植自 Linux acdc-profile.sh / load_advisor.py / tray_menu.py) ----
        private CheckBox _chkAutoSwitch;
        private ComboBox _cboAcPlan, _cboDcPlan;
        private bool _autoSwitch = false;
        private string _acPlanGuid = "", _dcPlanGuid = "";
        private string _lastPowerLine = "";
        private bool _linkAcerProfile = false;   // v6.2: 插电→性能/离电→平衡 联动
        // v6.6: 刷新率跟随 + 低电量自动省电
        private CheckBox _chkBatt60hz, _chkBatAutoSave;
        private bool _batt60hz = false;
        private bool _batAutoSave = false;
        private bool _batAutoDone = false;       // 本次放电周期只触发一次, 接电重置
        private List<PowerPlan> _cachedPlans = new List<PowerPlan>();
        private CheckBox _chkTopMost;
        private CheckBox _chkLinkAcer;             // M: LoadSettings 后回填联动复选框
        private NumericUpDown _numBat, _numTemp;   // M: LoadSettings 后回填阈值
        private readonly LoadAdvisor _advisor = new LoadAdvisor(70.0, 30, 1, 15);
        private MenuItem _trayStatusItem, _traySceneItem;
        // ---- v5: 悬浮窗 + 托盘数字图标 + 置顶 (TrafficMonitor/任务管理器风格) ----
        private FloatWidget _widget;
        private bool _widgetOn = false;
        private Icon _trayIconLive;          // 动态绘制的 CPU% 图标 (死代码清理: _clickThrough 已删除)
        private DateTime _lastIconDraw = DateTime.MinValue;

        public MainForm(int initialTab, int autoCloseSec)
        {
            Program.Trace("MainForm ctor: 开始");
            Text = "系统控制台";
            Font = new Font("Microsoft YaHei UI", 9F);
            StartPosition = FormStartPosition.CenterScreen;
            MinimumSize = new Size(760, 560);
            Size = new Size(860, 640);
            Icon = SystemIcons.Application;

            BuildUi();
            Program.Trace("MainForm ctor: BuildUi 完成");
            LoadSettings();
            Program.Trace("MainForm ctor: LoadSettings 完成");
            if (initialTab >= 0 && initialTab < _tabs.TabPages.Count) _tabs.SelectedIndex = initialTab;
            BuildTray();
            Program.Trace("MainForm ctor: BuildTray 完成");

            _timer = new System.Windows.Forms.Timer();
            _timer.Interval = _baseIntervalMs;
            _timer.Tick += OnTick;
            _timer.Start();
            OnTick(null, null); // 首帧立即填充
            Program.Trace("MainForm ctor: 首帧 OnTick 完成");

            // 自动退出(测试用): --autoclose=N 秒后干净退出(走正常保存/Dispose 路径)
            if (autoCloseSec > 0)
            {
                System.Windows.Forms.Timer ac = new System.Windows.Forms.Timer();
                ac.Interval = autoCloseSec * 1000;
                ac.Tick += delegate { ac.Stop(); _reallyExit = true; Close(); };
                ac.Start();
            }

            FormClosing += delegate(object s, FormClosingEventArgs e)
            {
                Program.Trace("FormClosing: reason=" + e.CloseReason + " reallyExit=" + _reallyExit);
                if (!_reallyExit && e.CloseReason == CloseReason.UserClosing)
                {
                    e.Cancel = true;
                    Hide();
                    SaveSettings();
                }
                else
                {
                    SaveSettings();
                    if (_tray != null) { _tray.Visible = false; _tray.Dispose(); }
                    _timer.Stop();
                    _collector.Dispose();
                }
            };
            Deactivate += delegate { _timer.Interval = Math.Max(_baseIntervalMs, 5000); };   // 省电: 失焦降频采样
            Activated += delegate { _timer.Interval = _baseIntervalMs; };
            Resize += delegate { if (WindowState == FormWindowState.Minimized) _timer.Interval = Math.Max(_baseIntervalMs, 5000); };

            // v2: 初始化设置区 UI 状态(在守卫解除前赋值不触发事件)
            _chkAutostart.Checked = AppLogic.GetAutostart();
            _chkAlerts.Checked = _alertsEnabled;
            int idx = 0;
            if (_baseIntervalMs == 2000) idx = 1; else if (_baseIntervalMs == 5000) idx = 2;
            _cboInterval.SelectedIndex = idx;
            // v4.1: AC/DC 自动切换 UI 状态(下拉框已在 FillPlanCombos 中按 guid 选中)
            _chkAutoSwitch.Checked = _autoSwitch;
            // v6.6: 刷新率跟随 + 低电量自动省电 UI 状态
            _chkBatt60hz.Checked = _batt60hz;
            _chkBatAutoSave.Checked = _batAutoSave;
            // M修复: BuildUi 先于 LoadSettings 执行, 按已加载值回填控件 (计划下拉/阈值/联动/置顶)
            FillPlanCombos();
            _chkTopMost.Checked = TopMost;
            _chkLinkAcer.Checked = _linkAcerProfile;
            _numBat.Value = _alertBatPct;
            _numTemp.Value = (decimal)_alertTempC;
            _loadingUi = false;
            Program.Trace("MainForm ctor: 设置区初始化完成");

            // v4: 加载布局设置
            LoadLayoutSettings();
            Program.Trace("MainForm ctor: 全部完成");
        }

        // ================= UI 构建 =================
        private void BuildUi()
        {
            // v3: 顶部工具栏 (场景快捷切换)
            _toolStrip = new ToolStrip();
            _toolStrip.GripStyle = ToolStripGripStyle.Hidden;
            _toolStrip.Padding = new Padding(8, 2, 8, 2);
            _lblPowerBadge = new ToolStripLabel("AC");
            _lblPowerBadge.Font = new Font("Microsoft YaHei UI", 9F, FontStyle.Bold);
            _lblPowerBadge.ForeColor = Color.DarkGreen;
            _toolStrip.Items.Add(_lblPowerBadge);
            _toolStrip.Items.Add(new ToolStripSeparator());
            _toolStrip.Items.Add(new ToolStripLabel("场景:"));
            _cboScenePlans = new ToolStripComboBox();
            _cboScenePlans.DropDownStyle = ComboBoxStyle.DropDownList;
            _cboScenePlans.Width = 160;
            _cboScenePlans.SelectedIndexChanged += delegate { OnScenePlanChanged(); };
            _toolStrip.Items.Add(_cboScenePlans);
            Button btnSceneSwitch = new Button();
            btnSceneSwitch.Text = "切换";
            btnSceneSwitch.Width = 60;
            btnSceneSwitch.Click += delegate { OnScenePlanChanged(); };
            ToolStripControlHost host = new ToolStripControlHost(btnSceneSwitch);
            _toolStrip.Items.Add(host);

            _tabs = new TabControl();
            _tabs.Dock = DockStyle.Fill;
            Program.Trace("BuildUi: 开始构建各页");
            _tabs.TabPages.Add(BuildOverviewPage());
            Program.Trace("BuildUi: 总览页完成");
            _tabs.TabPages.Add(BuildPowerPage());
            Program.Trace("BuildUi: 电源页完成");
            _tabs.TabPages.Add(BuildTuningPage());   // v6: 本机调优页 (亮度/CPU状态/超时/USB/PCIe/GPU)
            Program.Trace("BuildUi: 调优页完成");
            _tabs.TabPages.Add(BuildProcessPage());
            Program.Trace("BuildUi: 进程页完成");
            _tabs.TabPages.Add(BuildSystemPage());
            Program.Trace("BuildUi: 系统页完成");
            _tabs.TabPages.Add(BuildMaintenancePage());  // v3.3: 系统维护页
            Program.Trace("BuildUi: 维护页完成");
            // v4.2: 停靠顺序修正 — Fill 控件必须先加入(后布局拿剩余空间),
            // Top 工具栏后加入(先布局占顶部条)。原顺序导致 ToolStrip 盖住 TabControl 页签头。
            Controls.Add(_tabs);
            Controls.Add(_toolStrip);
            Program.Trace("BuildUi: Controls.Add 完成");

            // 加载电源计划到场景下拉框
            LoadScenePlans();
            Program.Trace("BuildUi: LoadScenePlans 完成");
        }

        // v3: 场景快捷切换
        private bool _suppressSceneEvent = false;   // v4.1: 程序化设置 SelectedIndex 时抑制事件(防无限切换循环)
        private void LoadScenePlans()
        {
            _cboScenePlans.Items.Clear();
            try
            {
                List<PowerPlan> plans = _collector.ListPowerPlans();
                _suppressSceneEvent = true;
                foreach (PowerPlan p in plans)
                {
                    _cboScenePlans.Items.Add(p.Name + (p.IsActive ? " (当前)" : ""));
                    if (p.IsActive) _cboScenePlans.SelectedIndex = _cboScenePlans.Items.Count - 1;
                }
                _suppressSceneEvent = false;
            }
            catch { _suppressSceneEvent = false; }
        }

        // v4.1: AC/DC 自动切换辅助
        private void FillPlanCombos()
        {
            try
            {
                _cachedPlans = _collector.ListPowerPlans();
                _suppressSceneEvent = true;
                _cboAcPlan.Items.Clear();
                _cboDcPlan.Items.Clear();
                foreach (PowerPlan p in _cachedPlans)
                {
                    _cboAcPlan.Items.Add(p.Name);
                    _cboDcPlan.Items.Add(p.Name);
                }
                int ai = IndexOfGuid(_acPlanGuid);
                int di = IndexOfGuid(_dcPlanGuid);
                if (ai >= 0) _cboAcPlan.SelectedIndex = ai;
                else if (_cboAcPlan.Items.Count > 0) _cboAcPlan.SelectedIndex = 0;
                if (di >= 0) _cboDcPlan.SelectedIndex = di;
                else if (_cboDcPlan.Items.Count > 1) _cboDcPlan.SelectedIndex = Math.Min(3, _cboDcPlan.Items.Count - 1); // 默认省电(第4项)
                _suppressSceneEvent = false;
            }
            catch { _suppressSceneEvent = false; }
        }

        private string GuidOfComboIndex(int idx)
        {
            if (idx < 0 || idx >= _cachedPlans.Count) return "";
            return _cachedPlans[idx].Guid;
        }

        private int IndexOfGuid(string guid)
        {
            if (string.IsNullOrEmpty(guid)) return -1;
            for (int i = 0; i < _cachedPlans.Count; i++)
                if (_cachedPlans[i].Guid == guid) return i;
            return -1;
        }

        private string PlanNameOf(string guid)
        {
            int i = IndexOfGuid(guid);
            return i >= 0 ? _cachedPlans[i].Name : guid;
        }

        // v4.1: 供电变化 → 应用默认计划 (冷启动归位 + 插拔电响应, 仿 acdc-profile.sh v4/v9)
        private void ApplyAutoSwitch(string powerLine)
        {
            try
            {
                if (!_autoSwitch) return;
                bool ac = (powerLine == "已接通电源");
                bool dc = (powerLine == "使用电池");
                if (!ac && !dc) return;
                string guid = ac ? _acPlanGuid : _dcPlanGuid;
                if (string.IsNullOrEmpty(guid)) return;
                string err = Collector.SwitchPowerPlan(guid);
                if (err == null)
                {
                    if (_tray != null && _alertsEnabled)
                    {
                        try { _tray.ShowBalloonTip(4000, "自动切换",
                            (ac ? "已接通电源" : "已切换为电池") + " → " + PlanNameOf(guid), ToolTipIcon.Info); }
                        catch { }
                    }
                    LoadScenePlans();
                    ReloadPlans();
                }
                // v6.2: 软硬件联动 — 插电→Acer 性能配置, 离电→平衡 (需管理员, 失败静默)
                if (_linkAcerProfile)
                {
                    string perr = _collector.AcerSetProfile(ac ? 3 : 2);
                    if (perr == null && _lblAcerNow != null)
                    {
                        _lblAcerNow.Text = ac ? "当前: 性能 (联动)" : "当前: 平衡 (联动)";
                        if (_cboAcerProfile != null) _cboAcerProfile.SelectedIndex = ac ? 2 : 1;
                    }
                }
                // v6.6: 刷新率跟随 — 离电降至 60Hz, 插电恢复该屏最高可用档
                if (_batt60hz)
                {
                    int? cur = Collector.GetRefreshRate();
                    if (cur.HasValue)
                    {
                        if (dc && cur.Value > 60)
                        {
                            string er = Collector.SetRefreshRate(60);
                            if (er == null && _tray != null && _alertsEnabled)
                            { try { _tray.ShowBalloonTip(3000, "省电", "已切换 60Hz (电池)", ToolTipIcon.Info); } catch { } }
                        }
                        else if (ac && cur.Value < 60)
                        {
                            List<int> rates = Collector.EnumRefreshRates();
                            int best = rates.Count > 0 ? rates[rates.Count - 1] : 0;
                            if (best > 60) Collector.SetRefreshRate(best);
                        }
                    }
                }
                // v6.6: 接电时重置低电量自动省电的一次性标志
                if (ac) _batAutoDone = false;
            }
            catch (Exception ex) { Program.Trace("ApplyAutoSwitch 失败: " + ex.Message); }   // M: 空 catch 掩盖写失败, 至少留痕
        }

        // v4: 可配置布局
        private void ShowLayoutDialog()
        {
            Form dlg = new Form();
            dlg.Text = "仪表板布局设置";
            dlg.Size = new Size(320, 280);
            dlg.StartPosition = FormStartPosition.CenterParent;
            dlg.FormBorderStyle = FormBorderStyle.FixedDialog;
            dlg.MaximizeBox = false;
            dlg.MinimizeBox = false;

            string[] moduleNames = new string[] { "CPU 历史曲线", "内存历史曲线", "每核柱条", "内存进度条", "明细区" };
            CheckBox[] checks = new CheckBox[5];

            TableLayoutPanel panel = new TableLayoutPanel();
            panel.Dock = DockStyle.Fill;
            panel.ColumnCount = 1;
            panel.RowCount = 6;
            panel.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            for (int i = 0; i < 5; i++)
            {
                checks[i] = new CheckBox();
                checks[i].Text = moduleNames[i];
                checks[i].Checked = _moduleVisible[i];
                checks[i].AutoSize = true;
                checks[i].Margin = new Padding(20, 8, 0, 0);
                panel.Controls.Add(checks[i], 0, i);
            }

            Button btnOk = new Button();
            btnOk.Text = "应用";
            btnOk.Width = 80;
            btnOk.Height = 30;
            btnOk.Click += delegate
            {
                for (int i = 0; i < 5; i++) _moduleVisible[i] = checks[i].Checked;
                ApplyLayout();
                SaveLayoutSettings();
                dlg.DialogResult = DialogResult.OK;
                dlg.Close();
            };
            panel.Controls.Add(btnOk, 0, 5);

            dlg.Controls.Add(panel);
            dlg.ShowDialog(this);
        }

        private void ApplyLayout()
        {
            if (_overviewCpuBox != null) _overviewCpuBox.Visible = _moduleVisible[0];
            if (_overviewMemBox != null) _overviewMemBox.Visible = _moduleVisible[1];
            if (_overviewCoreBox != null) _overviewCoreBox.Visible = _moduleVisible[2];
            if (_overviewMemBarBox != null) _overviewMemBarBox.Visible = _moduleVisible[3];
            if (_overviewDetailBox != null) _overviewDetailBox.Visible = _moduleVisible[4];
        }

        // 死代码清理: GetSettingsPath 与 IniPath 重复, 统一用 IniPath
        private void SaveLayoutSettings()
        {
            try
            {
                string path = IniPath();
                if (path == null) return;
                Dictionary<string, string> ini = File.Exists(path) ? AppLogic.ParseIni(path) : new Dictionary<string, string>();
                for (int i = 0; i < 5; i++)
                    ini["mod" + i] = _moduleVisible[i] ? "1" : "0";
                using (StreamWriter sw = new StreamWriter(path, false, System.Text.Encoding.UTF8))
                    foreach (KeyValuePair<string, string> kv in ini)
                        sw.WriteLine(kv.Key + "=" + kv.Value);
            }
            catch { }
        }

        private void LoadLayoutSettings()
        {
            try
            {
                string path = IniPath();
                if (path == null || !File.Exists(path)) return;
                Dictionary<string, string> ini = AppLogic.ParseIni(path);
                for (int i = 0; i < 5; i++)
                {
                    string val;
                    if (ini.TryGetValue("mod" + i, out val))
                        _moduleVisible[i] = (val == "1");
                }
                ApplyLayout();
            }
            catch { }
        }

        // v4: 电池科学分析报告
        private void ShowBatteryAnalysis()
        {
            if (_last == null) { MessageBox.Show("请等待数据采集完成", "电池分析"); return; }
            Snapshot s = _last;

            StringBuilder sb = new StringBuilder();
            sb.AppendLine("╔══════════════════════════════════════════════════════════════╗");
            sb.AppendLine("║            电池科学分析报告 (7维评估)                       ║");
            sb.AppendLine("╚══════════════════════════════════════════════════════════════╝");
            sb.AppendLine();

            // 1. 容量评估
            sb.AppendLine("【1. 容量评估】");
            if (s.BatteryPct >= 0)
                sb.AppendLine("  当前容量: " + s.BatteryPct + "%");
            if (s.BatteryDesignCapMWh.HasValue && s.BatteryFullCapMWh.HasValue)
            {
                sb.AppendLine("  设计容量: " + s.BatteryDesignCapMWh.Value + " mWh");
                sb.AppendLine("  实际容量: " + s.BatteryFullCapMWh.Value + " mWh");
                double ratio = (double)s.BatteryFullCapMWh.Value / s.BatteryDesignCapMWh.Value;
                string grade = ratio > 0.85 ? "良好" : (ratio > 0.7 ? "一般" : "衰退");
                sb.AppendLine("  容量比: " + ratio.ToString("P1") + " → " + grade);
            }
            // v6.2: ACPI 电池数据块 (循环次数/满充容量交叉验证)
            try
            {
                int?[] blk = _collector.GetBatteryBlocks();
                if (blk[0].HasValue) sb.AppendLine("  循环次数: " + blk[0].Value + " 次" + (blk[0].Value == 0 ? " (固件未计数或新电池)" : ""));
                if (blk[2].HasValue && !s.BatteryDesignCapMWh.HasValue) sb.AppendLine("  设计容量(ACPI): " + blk[2].Value + " mWh");
                if (blk[1].HasValue && s.BatteryFullCapMWh.HasValue && blk[1].Value != s.BatteryFullCapMWh.Value)
                    sb.AppendLine("  满充容量(ACPI): " + blk[1].Value + " mWh (与 WMI 报告值有差异)");
            }
            catch { }
            sb.AppendLine();

            // 2. 健康度分析
            sb.AppendLine("【2. 健康度分析】");
            if (s.BatteryHealthPct.HasValue)
                sb.AppendLine("  当前健康度: " + s.BatteryHealthPct.Value.ToString("F1") + "%");
            if (s.BatteryHealthSlope != 0)
            {
                double monthly = s.BatteryHealthSlope * 30;
                string trend = monthly < 0 ? "衰退" : "回升";
                sb.AppendLine("  月变化率: " + monthly.ToString("F2") + "% (" + trend + ")");
                if (monthly < -2)
                    sb.AppendLine("  ⚠ 衰退较快，建议检查充电习惯");
                else if (monthly < -0.5)
                    sb.AppendLine("  △ 正常老化范围");
                else
                    sb.AppendLine("  ✓ 健康度稳定");
            }
            sb.AppendLine();

            // 3. 温度评估
            sb.AppendLine("【3. 温度评估】");
            if (s.BatteryTempC.HasValue)
            {
                double t = s.BatteryTempC.Value;
                string grade = t < 35 ? "理想" : (t < 45 ? "正常" : (t < 55 ? "偏高" : "危险"));
                sb.AppendLine("  电池温度: " + t.ToString("F1") + "°C → " + grade);
                if (t > 45)
                    sb.AppendLine("  ⚠ 高温会加速电池老化，建议改善散热");
            }
            else
                sb.AppendLine("  温度数据不可用");
            sb.AppendLine();

            // 4. 充电行为分析
            sb.AppendLine("【4. 充电行为分析】");
            if (!string.IsNullOrEmpty(s.BatteryChargePhase) && s.BatteryChargePhase != "--")
            {
                sb.AppendLine("  当前阶段: " + s.BatteryChargePhase + (s.BatteryChargePhase == "CC" ? " (恒流充电)" : " (恒压充电)"));
                if (s.BatteryChargePhase == "CV")
                    sb.AppendLine("  △ 恒压阶段充电速度减慢，属正常现象");
            }
            if (s.BatteryChargeRateMW.HasValue)
                sb.AppendLine("  充电功率: " + s.BatteryChargeRateMW.Value + " mW");
            if (s.BatteryDischargeRateMW.HasValue)
                sb.AppendLine("  放电功率: " + s.BatteryDischargeRateMW.Value + " mW");
            sb.AppendLine();

            // 5. 电压分析
            sb.AppendLine("【5. 电压分析】");
            if (s.BatteryVoltageV.HasValue)
            {
                double v = s.BatteryVoltageV.Value;
                string status = v > 12.0 ? "满电" : (v > 11.0 ? "正常" : (v > 10.0 ? "偏低" : "严重不足"));
                sb.AppendLine("  当前电压: " + v.ToString("F2") + "V → " + status);
            }
            sb.AppendLine();

            // 6. 续航预估
            sb.AppendLine("【6. 续航预估】");
            if (s.BatteryLifeSec > 0)
            {
                int h = (int)(s.BatteryLifeSec / 3600);
                int m = (int)((s.BatteryLifeSec % 3600) / 60);
                sb.AppendLine("  系统预估: " + h + " 小时 " + m + " 分钟");
            }
            else if (s.BatteryDischargeRateMW.HasValue && s.BatteryVoltageV.HasValue && s.BatteryVoltageV.Value > 0
                     && s.BatteryPct > 0 && s.BatteryDesignCapMWh.HasValue && s.BatteryDischargeRateMW.Value > 0)
            {
                // M修复: 补 BatteryDesignCapMWh.HasValue (原 .Value 直接 NRE); 去掉 *1000 (mWh/mW 已是小时)
                double curW = s.BatteryDischargeRateMW.Value / 1000.0;
                double remainWh = (s.BatteryPct / 100.0) * s.BatteryDesignCapMWh.Value / 1000.0;
                sb.AppendLine("  计算预估: 约 " + (remainWh / curW).ToString("F1") + " 小时");
            }
            else
                sb.AppendLine("  数据不足，无法预估");
            sb.AppendLine();

            // 7. 维护建议
            sb.AppendLine("【7. 维护建议】");
            sb.AppendLine("  • 避免长期满充 (100%)，建议设置充电上限 80%");
            sb.AppendLine("  • 避免深度放电 (<20%)，及时充电");
            sb.AppendLine("  • 高温环境 (>40°C) 避免充电");
            sb.AppendLine("  • 定期使用电池至 20% 再充满，校准电量计");
            sb.AppendLine("  • 长期不用时保持 50% 电量存放");
            sb.AppendLine();
            sb.AppendLine("═══════════════════════════════════════════════════════════════");

            // 显示对话框
            Form dlg = new Form();
            dlg.Text = "电池科学分析报告";
            dlg.Size = new Size(520, 640);
            dlg.StartPosition = FormStartPosition.CenterParent;
            TextBox txt = new TextBox();
            txt.Dock = DockStyle.Fill;
            txt.Multiline = true;
            txt.ReadOnly = true;
            txt.ScrollBars = ScrollBars.Both;
            txt.Font = new Font("Consolas", 10F);
            txt.Text = sb.ToString();
            // v4.1: 导出按钮 (仿 Linux export_session.py)
            Panel btnPanel = new Panel();
            btnPanel.Dock = DockStyle.Bottom;
            btnPanel.Height = 40;
            Button btnExport = new Button();
            btnExport.Text = "导出到文件";
            btnExport.Width = 110;
            btnExport.Location = new Point(10, 6);
            btnExport.Click += delegate
            {
                try
                {
                    using (SaveFileDialog sfd = new SaveFileDialog())
                    {
                        sfd.Filter = "文本文件|*.txt";
                        sfd.FileName = "电池分析_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".txt";
                        sfd.InitialDirectory = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments);
                        if (sfd.ShowDialog(dlg) == DialogResult.OK)
                        {
                            File.WriteAllText(sfd.FileName, sb.ToString(), System.Text.Encoding.UTF8);
                            MessageBox.Show("已导出: " + sfd.FileName, "导出成功", MessageBoxButtons.OK, MessageBoxIcon.Information);
                        }
                    }
                }
                catch (Exception ex) { MessageBox.Show("导出失败: " + ex.Message, "导出", MessageBoxButtons.OK, MessageBoxIcon.Error); }
            };
            btnPanel.Controls.Add(btnExport);
            dlg.Controls.Add(txt);
            dlg.Controls.Add(btnPanel);
            dlg.ShowDialog(this);
        }

        private void OnScenePlanChanged()
        {
            if (_loadingUi || _suppressSceneEvent) return;   // v4.1: 重入守卫(初始化期间/程序化刷新时不触发切换)
            if (_cboScenePlans.SelectedIndex < 0) return;
            try
            {
                List<PowerPlan> plans = _collector.ListPowerPlans();
                string selected = _cboScenePlans.SelectedItem.ToString().Replace(" (当前)", "");
                foreach (PowerPlan p in plans)
                {
                    if (p.Name == selected)
                    {
                        string err = Collector.SwitchPowerPlan(p.Guid);
                        if (err != null)
                        {
                            MessageBox.Show("切换失败: " + err, "场景切换", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                        }
                        else
                        {
                            LoadScenePlans(); // 刷新列表
                            ReloadPlans();    // 刷新电源页
                        }
                        break;
                    }
                }
            }
            catch (Exception ex) { MessageBox.Show("切换异常: " + ex.Message, "场景切换", MessageBoxButtons.OK, MessageBoxIcon.Error); }
        }

        private TabPage BuildOverviewPage()
        {
            TabPage page = new TabPage("总览");
            TableLayoutPanel root = new TableLayoutPanel();
            root.Dock = DockStyle.Fill;
            root.ColumnCount = 4;
            root.RowCount = 6;
            root.Padding = new Padding(10);
            for (int i = 0; i < 4; i++) root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 25f));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 78));   // 卡片区
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 150));  // CPU 曲线
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 130));  // 每核柱条
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 44));   // 内存曲线行
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 120));  // v5: 网络+GPU 曲线
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));   // 明细区

            // ---- 状态卡 ----
            _lblCpuVal = MakeCard(root, 0, 0, "CPU");
            _lblMemVal = MakeCard(root, 1, 0, "内存");
            _lblGpuVal = MakeCard(root, 2, 0, "GPU");
            _lblBatVal = MakeCard(root, 3, 0, "电池");

            // ---- CPU 曲线 ----
            _overviewCpuBox = GroupOf("CPU 历史利用率 (%)", 0, 1, 2);
            _cpuCurve = new CurvePanel(Color.FromArgb(48, 140, 198));
            _cpuCurve.Dock = DockStyle.Fill;
            _overviewCpuBox.Controls.Add(_cpuCurve);
            root.Controls.Add(_overviewCpuBox, 0, 1);
            root.SetColumnSpan(_overviewCpuBox, 2);

            // ---- 内存曲线 ----
            _overviewMemBox = GroupOf("内存使用率 (%)", 2, 1, 2);
            _memCurve = new CurvePanel(Color.FromArgb(120, 170, 80));
            _memCurve.Dock = DockStyle.Fill;
            _overviewMemBox.Controls.Add(_memCurve);
            root.Controls.Add(_overviewMemBox, 2, 1);
            root.SetColumnSpan(_overviewMemBox, 2);

            // ---- 每核柱条 ----
            _overviewCoreBox = GroupOf("每核占用", 0, 2, 4);
            FlowLayoutPanel coreFlow = new FlowLayoutPanel();
            coreFlow.Dock = DockStyle.Fill;
            coreFlow.WrapContents = true;
            int cores = Math.Max(Environment.ProcessorCount, 1);
            _coreBars = new ProgressBar[cores];
            for (int i = 0; i < cores; i++)
            {
                Panel one = new Panel();
                one.Size = new Size(86, 56);
                one.Margin = new Padding(4);
                Label cap = new Label();
                cap.Text = "核 " + i;
                cap.AutoSize = true;
                cap.Location = new Point(2, 0);
                ProgressBar bar = new ProgressBar();
                bar.Location = new Point(2, 20);
                bar.Size = new Size(80, 18);
                bar.Minimum = 0; bar.Maximum = 100;
                one.Controls.Add(cap);
                one.Controls.Add(bar);
                _coreBars[i] = bar;
                coreFlow.Controls.Add(one);
            }
            _overviewCoreBox.Controls.Add(coreFlow);
            root.Controls.Add(_overviewCoreBox, 0, 2);
            root.SetColumnSpan(_overviewCoreBox, 4);

            // ---- 内存条 ----
            _overviewMemBarBox = GroupOf("", 0, 3, 4);
            _overviewMemBarBox.Height = 40;
            ProgressBar memBar = new ProgressBar();
            memBar.Name = "memBar";
            memBar.Dock = DockStyle.Fill;
            memBar.Minimum = 0; memBar.Maximum = 100;
            _overviewMemBarBox.Controls.Add(memBar);
            root.Controls.Add(_overviewMemBarBox, 0, 3);
            root.SetColumnSpan(_overviewMemBarBox, 4);
            _memBar = memBar;

            // ---- v5: 网络 + GPU 历史曲线 (Mission Center 风格) ----
            Panel netBox = GroupOf("网络总速率 (MB/s 刻度)", 0, 4, 2);
            _netCurve = new CurvePanel(Color.FromArgb(70, 130, 200));
            _netCurve.Dock = DockStyle.Fill;
            netBox.Controls.Add(_netCurve);
            root.Controls.Add(netBox, 0, 4);
            root.SetColumnSpan(netBox, 2);

            Panel gpuBox = GroupOf("GPU 利用率 (%)", 2, 4, 2);
            _gpuCurve = new CurvePanel(Color.FromArgb(160, 90, 200));
            _gpuCurve.Dock = DockStyle.Fill;
            gpuBox.Controls.Add(_gpuCurve);
            root.Controls.Add(gpuBox, 2, 4);
            root.SetColumnSpan(gpuBox, 2);

            // ---- 明细区 ----
            _overviewDetailBox = GroupOf("明细", 0, 5, 4);
            TableLayoutPanel d = new TableLayoutPanel();
            d.Dock = DockStyle.Fill;
            d.ColumnCount = 2;
            d.AutoScroll = false;
            d.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50f));
            d.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50f));
            _lblUptime = new Label(); _lblUptime.Dock = DockStyle.Top; _lblUptime.TextAlign = ContentAlignment.MiddleLeft;
            _lblDiskIo = new Label(); _lblDiskIo.Dock = DockStyle.Top; _lblDiskIo.TextAlign = ContentAlignment.MiddleLeft;
            _lblNet = new Label(); _lblNet.Dock = DockStyle.Top; _lblNet.TextAlign = ContentAlignment.MiddleLeft;
            _lblTemp = new Label(); _lblTemp.Dock = DockStyle.Top; _lblTemp.ForeColor = Color.DimGray;
            _lblPlanNow = new Label(); _lblPlanNow.Dock = DockStyle.Top; _lblPlanNow.TextAlign = ContentAlignment.MiddleLeft;
            _lblNvidia = new Label(); _lblNvidia.Dock = DockStyle.Top; _lblNvidia.ForeColor = Color.DimGray;
            _lblCpuFreq = new Label(); _lblCpuFreq.Dock = DockStyle.Top; _lblCpuFreq.ForeColor = Color.DimGray;
            _lblBatDeep = new Label(); _lblBatDeep.Dock = DockStyle.Top; _lblBatDeep.ForeColor = Color.DimGray;
            d.Controls.Add(_lblUptime, 0, 0);
            d.Controls.Add(_lblDiskIo, 0, 1);
            d.Controls.Add(_lblNet, 0, 2);
            d.Controls.Add(_lblCpuFreq, 0, 3);
            d.Controls.Add(_lblPlanNow, 1, 0);
            d.Controls.Add(_lblTemp, 1, 1);
            d.Controls.Add(_lblNvidia, 1, 2);
            d.Controls.Add(_lblBatDeep, 1, 3);
            _overviewDetailBox.Controls.Add(d);
            root.Controls.Add(_overviewDetailBox, 0, 5);
            root.SetColumnSpan(_overviewDetailBox, 4);

            page.Controls.Add(root);

            // v4: 布局设置按钮
            Panel btnPanel = new Panel();
            btnPanel.Dock = DockStyle.Bottom;
            btnPanel.Height = 36;
            Button btnLayout = new Button();
            btnLayout.Text = "布局设置";
            btnLayout.AutoSize = true;
            btnLayout.Location = new Point(10, 6);
            btnLayout.Click += delegate { ShowLayoutDialog(); };
            btnPanel.Controls.Add(btnLayout);
            page.Controls.Add(btnPanel);

            return page;
        }

        private ProgressBar _memBar;

        private TabPage BuildPowerPage()
        {
            TabPage page = new TabPage("电源");
            TableLayoutPanel root = new TableLayoutPanel();
            root.Dock = DockStyle.Fill;
            root.ColumnCount = 1;
            root.RowCount = 4;
            root.Padding = new Padding(12);
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 110));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 160));  // v3: 充电曲线
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 90));

            Panel batBox = GroupOf("电池 / 供电", 0, 0, 1);
            _lblBatteryDetail = new Label();
            _lblBatteryDetail.Dock = DockStyle.Fill;
            _lblBatteryDetail.Font = new Font(Font, FontStyle.Bold);
            batBox.Controls.Add(_lblBatteryDetail);
            root.Controls.Add(batBox, 0, 0);

            // v3: 充电曲线 (双轴: 容量% + 电流mA)
            Panel chargeBox = GroupOf("充电曲线 (容量% + 电流mA)", 0, 1, 1);
            _chargeCurve = new DualAxisCurvePanel();
            _chargeCurve.Dock = DockStyle.Fill;
            chargeBox.Controls.Add(_chargeCurve);
            root.Controls.Add(chargeBox, 0, 1);

            Panel planBox = GroupOf("电源计划（对标 Linux 场景概念）", 0, 2, 1);
            TableLayoutPanel pl = new TableLayoutPanel();
            pl.Dock = DockStyle.Fill;
            pl.ColumnCount = 1;
            pl.RowCount = 2;
            pl.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            pl.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));
            _planList = new ListBox();
            _planList.Dock = DockStyle.Fill;
            FlowLayoutPanel btnRow = new FlowLayoutPanel();
            btnRow.Dock = DockStyle.Fill;
            btnRow.FlowDirection = FlowDirection.LeftToRight;
            _btnSwitchPlan = new Button();
            _btnSwitchPlan.Text = "切换到选中方案";
            _btnSwitchPlan.Width = 140;
            _btnSwitchPlan.Click += delegate { SwitchSelectedPlan(); };
            Button btnRefresh = new Button();
            btnRefresh.Text = "刷新";
            btnRefresh.Width = 70;
            btnRefresh.Click += delegate { ReloadPlans(); };
            _btnBatteryReport = new Button();
            _btnBatteryReport.Text = "生成电池报告 (HTML)";
            _btnBatteryReport.Width = 180;
            _btnBatteryReport.Click += delegate { GenerateBatteryReport(); };
            btnRow.Controls.Add(_btnSwitchPlan);
            btnRow.Controls.Add(btnRefresh);
            btnRow.Controls.Add(_btnBatteryReport);
            // v4: 电池分析按钮
            Button btnAnalysis = new Button();
            btnAnalysis.Text = "电池科学分析";
            btnAnalysis.Width = 130;
            btnAnalysis.Click += delegate { ShowBatteryAnalysis(); };
            btnRow.Controls.Add(btnAnalysis);
            // v6.4: 电源滑块 Overlay (Win11) — v6.6 实测: 注册表键仅 SYSTEM 可写 (Administrators 只读),
            // 直写路线不可行 → 建议用 Windows 设置→电源→电源模式滑块; 按钮保留 (SYSTEM 环境下可用)
            Label lblOv = new Label();
            lblOv.Text = "电源滑块:";
            lblOv.AutoSize = true;
            lblOv.Padding = new Padding(10, 8, 0, 0);
            _lblOverlayNow = new Label();
            _lblOverlayNow.Text = "滑块: --";
            _lblOverlayNow.AutoSize = true;
            _lblOverlayNow.ForeColor = Color.DimGray;
            _lblOverlayNow.Padding = new Padding(2, 8, 6, 0);
            Button btnOvEff = new Button();
            btnOvEff.Text = "最佳能效";
            btnOvEff.Width = 84;
            btnOvEff.Click += delegate { SwitchOverlay(Collector.OVERLAY_BEST_EFFICIENCY, "最佳能效"); };
            Button btnOvBal = new Button();
            btnOvBal.Text = "平衡";
            btnOvBal.Width = 60;
            btnOvBal.Click += delegate { SwitchOverlay(Collector.OVERLAY_BALANCED, "平衡"); };
            Button btnOvPerf = new Button();
            btnOvPerf.Text = "最佳性能";
            btnOvPerf.Width = 84;
            btnOvPerf.Click += delegate { SwitchOverlay(Collector.OVERLAY_BEST_PERFORMANCE, "最佳性能"); };
            // v6.6: 仅电池侧修正 (离电挂平衡, 插电保持不变)
            Button btnOvDcBal = new Button();
            btnOvDcBal.Text = "仅电池→平衡";
            btnOvDcBal.Width = 110;
            btnOvDcBal.Click += delegate { SwitchOverlayDc(Collector.OVERLAY_BALANCED, "平衡"); };
            btnRow.Controls.Add(lblOv);
            btnRow.Controls.Add(_lblOverlayNow);
            btnRow.Controls.Add(btnOvEff);
            btnRow.Controls.Add(btnOvBal);
            btnRow.Controls.Add(btnOvPerf);
            btnRow.Controls.Add(btnOvDcBal);
            pl.Controls.Add(_planList, 0, 0);
            pl.Controls.Add(btnRow, 0, 1);
            planBox.Controls.Add(pl);
            root.Controls.Add(planBox, 0, 2);

            Label hint = new Label();
            hint.Dock = DockStyle.Fill;
            hint.ForeColor = Color.DimGray;
            hint.Text = "提示：切换电源计划如失败（需要管理员），请到\"系统\"页点击【以管理员身份重启】后再操作。";
            hint.TextAlign = ContentAlignment.MiddleCenter;
            root.Controls.Add(hint, 0, 3);

            page.Controls.Add(root);
            ReloadPlans();
            return page;
        }

        private TextBox _procSearch;
        private Label _procSummary;
        private TabPage BuildProcessPage()
        {
            TabPage page = new TabPage("进程");
            TableLayoutPanel root = new TableLayoutPanel();
            root.Dock = DockStyle.Fill;
            root.ColumnCount = 1;
            root.RowCount = 3;
            root.Padding = new Padding(10);
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 36));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 40));

            // v5: 搜索框 + 摘要行 (System Informer/任务管理器 DeLuxe 风格)
            FlowLayoutPanel topRow = new FlowLayoutPanel();
            topRow.Dock = DockStyle.Fill;
            Label lblSearch = new Label();
            lblSearch.Text = "筛选:";
            lblSearch.AutoSize = true;
            lblSearch.Padding = new Padding(2, 8, 0, 0);
            _procSearch = new TextBox();
            _procSearch.Width = 180;
            _procSearch.TextChanged += delegate { RefreshProcesses(false); };
            _procSummary = new Label();
            _procSummary.AutoSize = true;
            _procSummary.ForeColor = Color.DimGray;
            _procSummary.Padding = new Padding(12, 8, 0, 0);
            topRow.Controls.Add(lblSearch);
            topRow.Controls.Add(_procSearch);
            topRow.Controls.Add(_procSummary);
            root.Controls.Add(topRow, 0, 0);

            _procList = new ListView();
            _procList.View = View.Details;
            _procList.FullRowSelect = true;
            _procList.HideSelection = true;
            _procList.Dock = DockStyle.Fill;
            _procList.Columns.Add("名称", 220);
            _procList.Columns.Add("PID", 60, HorizontalAlignment.Right);
            _procList.Columns.Add("CPU %", 70, HorizontalAlignment.Right);
            _procList.Columns.Add("内存 MB", 80, HorizontalAlignment.Right);
            _procList.Columns.Add("磁盘 KB/s", 80, HorizontalAlignment.Right);
            _procList.Columns.Add("GPU %", 60, HorizontalAlignment.Right);
            _procList.Columns.Add("公司/路径", 260);
            _procList.ColumnClick += delegate(object sender, ColumnClickEventArgs e)
            {
                _sorter.Col = e.Column;
                _sorter.NumMode = (e.Column >= 1 && e.Column <= 5);
                _procList.ListViewItemSorter = _sorter;
                _procList.Sort();
            };
            // v5: 右键菜单 (结束/挂起/恢复/优先级)
            ContextMenu pm = new ContextMenu();
            pm.MenuItems.Add("结束任务", delegate { KillSelected(); });
            pm.MenuItems.Add("挂起", delegate { SuspendSelected(true); });
            pm.MenuItems.Add("恢复", delegate { SuspendSelected(false); });
            MenuItem miPri = new MenuItem("优先级");
            miPri.MenuItems.Add("高", delegate { SetPriority(ProcessPriorityClass.High); });
            miPri.MenuItems.Add("普通", delegate { SetPriority(ProcessPriorityClass.Normal); });
            miPri.MenuItems.Add("低", delegate { SetPriority(ProcessPriorityClass.Idle); });
            pm.MenuItems.Add(miPri);
            // v6.6: EcoQoS 效率模式 (Win11 原生, 后台程序降频省电)
            MenuItem miEco = new MenuItem("效率模式(EcoQoS)");
            miEco.MenuItems.Add("开 (加入自动规则)", delegate { EcoSelected(true); });
            miEco.MenuItems.Add("关 (移除规则)", delegate { EcoSelected(false); });
            pm.MenuItems.Add(miEco);
            _procList.ContextMenu = pm;
            root.Controls.Add(_procList, 0, 1);

            FlowLayoutPanel row = new FlowLayoutPanel();
            row.Dock = DockStyle.Fill;
            Button btnRefresh = new Button();
            btnRefresh.Text = "立即刷新";
            btnRefresh.Width = 90;
            btnRefresh.Click += delegate { RefreshProcesses(true); };
            _btnKillProc = new Button();
            _btnKillProc.Text = "结束任务";
            _btnKillProc.Width = 100;
            _btnKillProc.Click += delegate { KillSelected(); };
            Label note = new Label();
            note.AutoSize = true;
            note.ForeColor = Color.DimGray;
            note.Text = "（红=CPU>50% 橙=内存>500MB；右键挂起/优先级/效率模式(EcoQoS)；仅可见时 2s 自动刷新）";
            note.Padding = new Padding(8, 8, 0, 0);
            row.Controls.Add(btnRefresh);
            row.Controls.Add(_btnKillProc);
            row.Controls.Add(note);
            root.Controls.Add(row, 0, 2);

            page.Controls.Add(root);
            return page;
        }

        // v5: 挂起/恢复进程 (ntdll)
        [System.Runtime.InteropServices.DllImport("ntdll.dll")]
        private static extern int NtSuspendProcess(IntPtr handle);
        [System.Runtime.InteropServices.DllImport("ntdll.dll")]
        private static extern int NtResumeProcess(IntPtr handle);

        private void SuspendSelected(bool suspend)
        {
            if (_procList.SelectedItems.Count == 0) return;
            int pid = (int)_procList.SelectedItems[0].Tag;
            try
            {
                using (Process p = Process.GetProcessById(pid))
                {
                    if (suspend && IsCriticalProc(p.ProcessName))   // M: 禁止挂起关键进程 (恢复不限制)
                    { MessageBox.Show("关键系统进程 (" + p.ProcessName + ") 禁止挂起", "保护", MessageBoxButtons.OK, MessageBoxIcon.Warning); return; }
                    IntPtr h = p.Handle;
                    int r = suspend ? NtSuspendProcess(h) : NtResumeProcess(h);
                    if (r != 0) MessageBox.Show("操作失败 (NTSTATUS 0x" + r.ToString("X") + ")，可能需要管理员权限。");
                }
            }
            catch (Exception ex) { MessageBox.Show("操作失败: " + ex.Message); }
        }

        private void SetPriority(ProcessPriorityClass pri)
        {
            if (_procList.SelectedItems.Count == 0) return;
            int pid = (int)_procList.SelectedItems[0].Tag;
            try
            {
                using (Process p = Process.GetProcessById(pid)) { p.PriorityClass = pri; }
            }
            catch (Exception ex) { MessageBox.Show("设置失败: " + ex.Message + "（可能需要管理员权限）"); }
        }

        // v6.6: EcoQoS 效率模式 (右键开/关 + settings.ini 按进程名持久化 + 刷新时自动补挂)
        private static string EcoBaseName(string listItemText)
        {
            string n = (listItemText ?? "").Trim().ToLower();
            if (n.EndsWith(".exe")) n = n.Substring(0, n.Length - 4);
            return n;
        }

        private void EcoSelected(bool on)
        {
            if (_procList.SelectedItems.Count == 0) return;
            ListViewItem li = _procList.SelectedItems[0];
            int pid = (int)li.Tag;
            string baseName = EcoBaseName(li.Text);
            if (on) _ecoqosNames.Add(baseName); else _ecoqosNames.Remove(baseName);
            SaveSettings();
            string err = Collector.SetProcessEcoQoS(pid, on);
            if (err == null)
            {
                if (on) _ecoqosApplied.Add(pid); else _ecoqosApplied.Remove(pid);
                if (_procSummary != null)
                    _procSummary.Text = "效率模式" + (on ? "已开启" : "已关闭") + ": " + li.Text
                        + " (规则数 " + _ecoqosNames.Count + ", 新进程自动套用)";
            }
            else if (_procSummary != null) _procSummary.Text = "效率模式失败: " + err;
        }

        /// 刷新后对命中规则的未处理 PID 自动套用 EcoQoS; 并清理已退出进程的记录
        private void EnsureEcoApplied()
        {
            if (_ecoqosNames.Count == 0) { if (_ecoqosApplied.Count > 0) _ecoqosApplied.Clear(); return; }
            if (_ecoqosApplied.Count > 64) _ecoqosApplied.RemoveWhere(delegate(int pid) { try { using (Process.GetProcessById(pid)) return false; } catch { return true; } });
            foreach (ListViewItem li in _procList.Items)
            {
                int pid;
                try { pid = (int)li.Tag; } catch { continue; }
                if (_ecoqosApplied.Contains(pid)) continue;
                if (!_ecoqosNames.Contains(EcoBaseName(li.Text))) continue;
                if (Collector.SetProcessEcoQoS(pid, true) == null) _ecoqosApplied.Add(pid);
            }
        }

        private TabPage BuildSystemPage()
        {
            TabPage page = new TabPage("系统");
            TableLayoutPanel root = new TableLayoutPanel();
            root.Dock = DockStyle.Fill;
            root.ColumnCount = 1;
            root.RowCount = 3;
            root.Padding = new Padding(12);
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 52));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 64));

            Panel infoBox = GroupOf("本机信息", 0, 0, 1);
            _txtSysInfo = new TextBox();
            _txtSysInfo.Multiline = true;
            _txtSysInfo.ReadOnly = true;
            _txtSysInfo.ScrollBars = ScrollBars.Vertical;
            _txtSysInfo.Dock = DockStyle.Fill;
            _txtSysInfo.BackColor = SystemColors.Window;
            _txtSysInfo.Font = new Font("Consolas", 9F);
            infoBox.Controls.Add(_txtSysInfo);
            root.Controls.Add(infoBox, 0, 0);

            FlowLayoutPanel actions = new FlowLayoutPanel();
            actions.Dock = DockStyle.Fill;
            AddAction(actions, "以管理员身份重启", delegate { RestartAsAdmin(); });
            AddAction(actions, "任务管理器", delegate { TryStart("taskmgr.exe"); });
            AddAction(actions, "事件查看器", delegate { TryStart("eventvwr.msc"); });
            AddAction(actions, "设备管理器", delegate { TryStart("devmgmt.msc"); });
            AddAction(actions, "电源选项(控制面板)", delegate { TryStart("control", "/name Microsoft.PowerOptions"); });
            root.Controls.Add(actions, 0, 1);

            // ---- v2 设置区 ----
            Panel setBox = GroupOf("设置", 0, 2, 1);
            FlowLayoutPanel settings = new FlowLayoutPanel();
            settings.Dock = DockStyle.Fill;
            settings.Padding = new Padding(0, 4, 0, 0);
            _chkAutostart = new CheckBox();
            _chkAutostart.Text = "开机自动启动";
            _chkAutostart.AutoSize = true;
            _chkAutostart.CheckedChanged += delegate
            {
                if (_loadingUi) return;
                try { AppLogic.SetAutostart(_chkAutostart.Checked); }
                catch (Exception ex) { MessageBox.Show("写入自启动失败: " + ex.Message); }
            };
            _chkAlerts = new CheckBox();
            _chkAlerts.Text = "气泡告警（电量≤20% / CPU≥80°C）";
            _chkAlerts.AutoSize = true;
            _chkAlerts.CheckedChanged += delegate
            {
                if (_loadingUi) return;
                _alertsEnabled = _chkAlerts.Checked;
                SaveSettings();
            };
            Label lblIv = new Label();
            lblIv.Text = "采样间隔:";
            lblIv.AutoSize = true;
            lblIv.Padding = new Padding(10, 6, 0, 0);
            _cboInterval = new ComboBox();
            _cboInterval.DropDownStyle = ComboBoxStyle.DropDownList;
            _cboInterval.Items.Add("1 秒");
            _cboInterval.Items.Add("2 秒");
            _cboInterval.Items.Add("5 秒");
            _cboInterval.Width = 70;
            _cboInterval.SelectedIndex = 0;
            _cboInterval.SelectedIndexChanged += delegate
            {
                if (_loadingUi) return;
                int ms = 1000;
                if (_cboInterval.SelectedIndex == 1) ms = 2000;
                else if (_cboInterval.SelectedIndex == 2) ms = 5000;
                _baseIntervalMs = ms;
                if (WindowState != FormWindowState.Minimized) _timer.Interval = ms;
                SaveSettings();
            };
            settings.Controls.Add(_chkAutostart);
            settings.Controls.Add(_chkAlerts);
            settings.Controls.Add(lblIv);
            settings.Controls.Add(_cboInterval);

            // ---- v4.1: AC/DC 自动切换 (仿 Linux acdc-profile.sh) ----
            _chkAutoSwitch = new CheckBox();
            _chkAutoSwitch.Text = "插拔电自动切换计划";
            _chkAutoSwitch.AutoSize = true;
            _chkAutoSwitch.CheckedChanged += delegate
            {
                if (_loadingUi) return;
                _autoSwitch = _chkAutoSwitch.Checked;
                SaveSettings();
            };
            // v6.6: 电池时降 60Hz (刷新率跟随; 注: 内屏 60Hz 无可降, 仅外接高刷屏场景生效)
            _chkBatt60hz = new CheckBox();
            _chkBatt60hz.Text = "电池时降 60Hz (外接高刷屏场景)";
            _chkBatt60hz.AutoSize = true;
            _chkBatt60hz.Padding = new Padding(14, 0, 0, 0);
            _chkBatt60hz.CheckedChanged += delegate
            {
                if (_loadingUi) return;
                _batt60hz = _chkBatt60hz.Checked;
                SaveSettings();
                if (_batt60hz && _lastPowerLine == "使用电池")
                {
                    int? cur = Collector.GetRefreshRate();
                    if (cur.HasValue && cur.Value > 60) Collector.SetRefreshRate(60);
                }
            };
            // v6.6: 低电量自动省电
            _chkBatAutoSave = new CheckBox();
            _chkBatAutoSave.Text = "低电量自动省电 (切电池计划+EPP拉满)";
            _chkBatAutoSave.AutoSize = true;
            _chkBatAutoSave.Padding = new Padding(14, 0, 0, 0);
            _chkBatAutoSave.CheckedChanged += delegate
            {
                if (_loadingUi) return;
                _batAutoSave = _chkBatAutoSave.Checked;
                SaveSettings();
            };
            Label lblAc = new Label();
            lblAc.Text = "插电默认:";
            lblAc.AutoSize = true;
            lblAc.Padding = new Padding(10, 6, 0, 0);
            _cboAcPlan = new ComboBox();
            _cboAcPlan.DropDownStyle = ComboBoxStyle.DropDownList;
            _cboAcPlan.Width = 110;
            _cboAcPlan.SelectedIndexChanged += delegate
            {
                if (_loadingUi) return;
                _acPlanGuid = GuidOfComboIndex(_cboAcPlan.SelectedIndex);
                SaveSettings();
            };
            Label lblDc = new Label();
            lblDc.Text = "离电默认:";
            lblDc.AutoSize = true;
            lblDc.Padding = new Padding(10, 6, 0, 0);
            _cboDcPlan = new ComboBox();
            _cboDcPlan.DropDownStyle = ComboBoxStyle.DropDownList;
            _cboDcPlan.Width = 110;
            _cboDcPlan.SelectedIndexChanged += delegate
            {
                if (_loadingUi) return;
                _dcPlanGuid = GuidOfComboIndex(_cboDcPlan.SelectedIndex);
                SaveSettings();
            };
            settings.Controls.Add(_chkAutoSwitch);
            settings.Controls.Add(lblAc);
            settings.Controls.Add(_cboAcPlan);
            settings.Controls.Add(lblDc);
            settings.Controls.Add(_cboDcPlan);
            settings.Controls.Add(_chkBatt60hz);      // v6.6
            settings.Controls.Add(_chkBatAutoSave);   // v6.6

            // ---- v5: 悬浮窗 + 窗口置顶 ----
            CheckBox chkWidget = new CheckBox();
            chkWidget.Text = "桌面悬浮窗";
            chkWidget.AutoSize = true;
            chkWidget.Checked = _widgetOn;
            chkWidget.CheckedChanged += delegate
            {
                if (_loadingUi) return;
                if (chkWidget.Checked != _widgetOn) ToggleWidget();
                chkWidget.Checked = _widgetOn;
            };
            CheckBox chkTopMost = new CheckBox();
            chkTopMost.Text = "窗口置顶";
            chkTopMost.AutoSize = true;
            chkTopMost.CheckedChanged += delegate
            {
                if (_loadingUi) return;
                TopMost = chkTopMost.Checked;
                SaveSettings();
            };
            settings.Controls.Add(chkWidget);
            settings.Controls.Add(chkTopMost);
            _chkTopMost = chkTopMost;

            // ---- v5: 告警阈值可配置 ----
            Label lblBat = new Label();
            lblBat.Text = "低电阈值%";
            lblBat.AutoSize = true;
            lblBat.Padding = new Padding(10, 6, 0, 0);
            NumericUpDown numBat = _numBat = new NumericUpDown();
            numBat.Minimum = 5; numBat.Maximum = 50;
            numBat.Value = _alertBatPct;
            numBat.Width = 50;
            numBat.ValueChanged += delegate
            {
                if (_loadingUi) return;
                _alertBatPct = (int)numBat.Value;
                SaveSettings();
            };
            Label lblTemp = new Label();
            lblTemp.Text = "高温阈值°C";
            lblTemp.AutoSize = true;
            lblTemp.Padding = new Padding(10, 6, 0, 0);
            NumericUpDown numTemp = _numTemp = new NumericUpDown();
            numTemp.Minimum = 60; numTemp.Maximum = 100;
            numTemp.Value = (decimal)_alertTempC;
            numTemp.Width = 50;
            numTemp.ValueChanged += delegate
            {
                if (_loadingUi) return;
                _alertTempC = (float)numTemp.Value;
                SaveSettings();
            };
            settings.Controls.Add(lblBat);
            settings.Controls.Add(numBat);
            settings.Controls.Add(lblTemp);
            settings.Controls.Add(numTemp);

            // ---- v6.2: AC/DC ↔ Acer 配置联动 ----
            CheckBox chkLink = _chkLinkAcer = new CheckBox();
            chkLink.Text = "插拔电联动Acer配置(插电→性能/离电→平衡, 需管理员)";
            chkLink.AutoSize = true;
            chkLink.Checked = _linkAcerProfile;
            chkLink.CheckedChanged += delegate
            {
                if (_loadingUi) return;
                _linkAcerProfile = chkLink.Checked;
                SaveSettings();
            };
            settings.Controls.Add(chkLink);
            FillPlanCombos();
            setBox.Controls.Add(settings);
            root.Controls.Add(setBox, 0, 2);

            page.Controls.Add(root);
            FillSystemInfo();
            return page;
        }

        // ================= v6: 调优页 (本机探测验证: 亮度/CPU状态/超时/USB/PCIe 全可用, 无需管理员) =================
        private TrackBar _trkBright, _trkAcMax, _trkDcMax;
        private TrackBar _trkAcEpp, _trkDcEpp;                // v6.5: EPP 能量性能偏好
        private Label _lblBrightNow, _lblTunStatus;
        private NumericUpDown _numScreenAc, _numScreenDc, _numSleepAc, _numSleepDc;
        private NumericUpDown _numMinAc, _numMinDc;          // v6.2: 最小处理器状态
        private CheckBox _chkUsbAc, _chkUsbDc, _chkAspmAc, _chkAspmDc;
        // v6.6: 无线功耗 + EcoQoS
        private ComboBox _cboWifiAc, _cboWifiDc;
        private readonly System.Collections.Generic.HashSet<string> _ecoqosNames = new System.Collections.Generic.HashSet<string>();
        private readonly System.Collections.Generic.HashSet<int> _ecoqosApplied = new System.Collections.Generic.HashSet<int>();
        private CheckBox _chkAdaptive;                        // v6.2: 自适应亮度
        private TextBox _txtTuningInfo;
        // v6.6: dGPU 断电辅助 (#12, 来源 LLT/G-Helper 思路, 零依赖实现)
        private Button _btnKillGpuProc;
        private List<int> _gpuBusyPids = new List<int>();
        private bool _tuningLoaded, _tuningBusy;
        // v6.1: Acer 硬件联动
        private ComboBox _cboAcerProfile;
        private Label _lblAcerNow, _lblFanStatus;
        // v6.3: NVIDIA PowerMizer
        private Label _lblPmNow;
        private DateTime _lastThrottleAlert = DateTime.MinValue;
        // v6.4: Boost 模式
        private ComboBox _cboBoost;
        private Label _lblOverlayNow;

        private void RefreshPmLabel()
        {
            try
            {
                string[] pm = _collector.ReadPowerMizer();
                if (pm == null) { _lblPmNow.Text = "当前: 不可读 (需管理员)"; return; }
                if (pm[0] == "(默认)") _lblPmNow.Text = "当前: 驱动默认";
                else _lblPmNow.Text = string.Format("当前: Enable={0} Level={1}/{2} Src={3}", pm[0], pm[1], pm[2], pm[3]);
            }
            catch { }
        }

        // 电源设置 GUID (本机已验证存在)
        private const string SUB_PROCESSOR = "54533251-82be-4824-96c1-47b60b740d00";
        private const string PROCTHROTTLEMAX = "bc5038f7-23e0-4960-96da-33abaf5935ec";
        private const string PROCTHROTTLEMIN = "893dee8e-2bef-41e0-89c6-b55d0929964c";   // v6.2
        private const string PERFEPP = "36687f9e-e3a5-4dbf-b1dc-15eb381c6863";           // v6.5: EPP (隐藏设置, 本机实测有效)
        private const string SUB_VIDEO = "7516b95f-f776-4464-8c53-06167f40cc99";
        private const string VIDEOIDLE = "3c0bc021-c8a8-4e07-a973-6b14cbcb2b7e";
        private const string SUB_SLEEP = "238c9fa8-0aad-41ed-83f4-97be242c8f20";
        private const string STANDBYIDLE = "29f6c1db-86da-48c5-9fdb-f2b67b1f44da";
        private const string SUB_USB = "2a737441-1930-4402-8d77-b2bebba308a3";
        private const string USBSELECTIVESUSPEND = "48e6b7a6-50f5-4782-a5d4-53bb8f07e226";
        private const string SUB_PCIEXPRESS = "501a4d13-42af-4429-9fd1-a8218c268e20";
        private const string PCIE_ASPM = "ee12f906-d277-404b-b6da-e5fa1a576df5";
        // v6.6: 无线适配器功耗模式 (SUB_WIFI 隐藏组)
        private const string SUB_WIFI = "19cbb8fa-5279-450e-9fac-8a3d5fedd0c1";
        private const string WIRELESS_POWER = "12bbebe6-58d6-4636-95bb-3217ef867c1a";

        private TabPage BuildTuningPage()
        {
            TabPage page = new TabPage("调优");
            TableLayoutPanel root = new TableLayoutPanel();
            root.Dock = DockStyle.Fill;
            root.ColumnCount = 1;
            root.RowCount = 8;
            root.Padding = new Padding(12);
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 84));   // 亮度
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 168));  // CPU 状态 (4行: 最大/最小/Boost/EPP)
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 92));   // 超时
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 84));   // USB/PCIe
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 84));   // v6.6: 无线适配器功耗
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 84));   // v6.1: Acer 硬件联动
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 84));   // v6.3: NVIDIA PowerMizer
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));   // 信息区

            // ---- 屏幕亮度 ----
            Panel brightBox = GroupOf("屏幕亮度 (WMI 即时生效)", 0, 0, 1);
            FlowLayoutPanel bf = new FlowLayoutPanel();
            bf.Dock = DockStyle.Fill;
            _trkBright = new TrackBar();
            _trkBright.Minimum = 0; _trkBright.Maximum = 100;
            _trkBright.TickFrequency = 10;
            _trkBright.Width = 320;
            _lblBrightNow = new Label();
            _lblBrightNow.Text = "--";
            _lblBrightNow.AutoSize = true;
            _lblBrightNow.Padding = new Padding(8, 14, 0, 0);
            _trkBright.ValueChanged += delegate
            {
                if (_tuningBusy) return;
                _lblBrightNow.Text = "亮度 " + _trkBright.Value + "%";
            };
            _trkBright.MouseUp += delegate
            {
                if (_tuningBusy) return;
                int target = _trkBright.Value;   // M: UI 线程捕获值, 后台不再跨线程读控件
                System.Threading.ThreadPool.QueueUserWorkItem(delegate
                {
                    bool ok = _collector.SetBrightness(target);
                    try { BeginInvoke((MethodInvoker)delegate { _lblBrightNow.Text = "亮度 " + target + "%" + (ok ? "" : " (失败)"); }); } catch { }
                });
            };
            // v6.2: 自适应亮度开关
            Label lblAdp = new Label();
            lblAdp.Text = "自适应亮度:";
            lblAdp.AutoSize = true;
            lblAdp.Padding = new Padding(14, 12, 0, 0);
            _chkAdaptive = new CheckBox();
            _chkAdaptive.Text = "启用";
            _chkAdaptive.AutoSize = true;
            _chkAdaptive.Padding = new Padding(2, 9, 0, 0);
            _chkAdaptive.CheckedChanged += delegate
            {
                if (_tuningBusy || _loadingUi) return;
                string err = Collector.ApplyPowerSetting(SUB_VIDEO, Collector.ADAPTBRIGHT_GUID, _chkAdaptive.Checked ? 1 : 0, _chkAdaptive.Checked ? 1 : 0);
                SetTunStatus(err == null ? "自适应亮度已" + (_chkAdaptive.Checked ? "开启" : "关闭") : "失败: " + err);
            };
            bf.Controls.Add(_trkBright);
            bf.Controls.Add(_lblBrightNow);
            bf.Controls.Add(lblAdp);
            bf.Controls.Add(_chkAdaptive);
            brightBox.Controls.Add(bf);
            root.Controls.Add(brightBox, 0, 0);

            // ---- CPU 性能状态 ----
            Panel cpuBox = GroupOf("CPU 性能状态 (频率占用%, 经电源计划生效)", 0, 1, 1);
            FlowLayoutPanel cf = new FlowLayoutPanel();
            cf.Dock = DockStyle.Fill;
            Label l1 = new Label(); l1.Text = "插电最大:"; l1.AutoSize = true; l1.Padding = new Padding(2, 4, 0, 0);
            _trkAcMax = new TrackBar(); _trkAcMax.Minimum = 50; _trkAcMax.Maximum = 100; _trkAcMax.TickFrequency = 10; _trkAcMax.Width = 180;
            Label l2 = new Label(); l2.Text = "电池最大:"; l2.AutoSize = true; l2.Padding = new Padding(10, 4, 0, 0);
            _trkDcMax = new TrackBar(); _trkDcMax.Minimum = 50; _trkDcMax.Maximum = 100; _trkDcMax.TickFrequency = 10; _trkDcMax.Width = 180;
            Label l3 = new Label(); l3.Text = "100%/90%"; l3.AutoSize = true; l3.ForeColor = Color.DimGray; l3.Padding = new Padding(10, 4, 0, 0);
            _trkAcMax.ValueChanged += delegate { l3.Text = _trkAcMax.Value + "%/" + _trkDcMax.Value + "%"; };
            _trkDcMax.ValueChanged += delegate { l3.Text = _trkAcMax.Value + "%/" + _trkDcMax.Value + "%"; };
            Button btnCpu = new Button(); btnCpu.Text = "应用"; btnCpu.Width = 70;
            btnCpu.Click += delegate
            {
                string err = Collector.ApplyPowerSetting(SUB_PROCESSOR, PROCTHROTTLEMAX, _trkAcMax.Value, _trkDcMax.Value);
                SetTunStatus(err == null ? "CPU 状态已应用: AC " + _trkAcMax.Value + "% / DC " + _trkDcMax.Value + "%" : "失败: " + err);
            };
            cf.Controls.Add(l1); cf.Controls.Add(_trkAcMax);
            cf.Controls.Add(l2); cf.Controls.Add(_trkDcMax);
            cf.Controls.Add(l3); cf.Controls.Add(btnCpu);
            // v6.2: 最小处理器状态 (影响待机频率下限)
            FlowLayoutPanel cf2 = new FlowLayoutPanel();
            cf2.Dock = DockStyle.Fill;
            Label l8 = new Label(); l8.Text = "最小状态 插电:"; l8.AutoSize = true; l8.Padding = new Padding(2, 2, 0, 0);
            _numMinAc = NewNum(0, 100);
            Label l9 = new Label(); l9.Text = "电池:"; l9.AutoSize = true; l9.Padding = new Padding(6, 2, 0, 0);
            _numMinDc = NewNum(0, 100);
            Label l10 = new Label(); l10.Text = "(默认 5%/5%, 调高可减少频闪卡顿但增耗电)"; l10.AutoSize = true; l10.ForeColor = Color.DimGray; l10.Padding = new Padding(10, 2, 0, 0);
            Button btnMin = new Button(); btnMin.Text = "应用"; btnMin.Width = 70;
            btnMin.Click += delegate
            {
                string err = Collector.ApplyPowerSetting(SUB_PROCESSOR, PROCTHROTTLEMIN, (int)_numMinAc.Value, (int)_numMinDc.Value);
                SetTunStatus(err == null ? "最小状态已应用: AC " + _numMinAc.Value + "% / DC " + _numMinDc.Value + "%" : "失败: " + err);
            };
            cf2.Controls.Add(l8); cf2.Controls.Add(_numMinAc);
            cf2.Controls.Add(l9); cf2.Controls.Add(_numMinDc);
            cf2.Controls.Add(l10); cf2.Controls.Add(btnMin);
            // v6.4: Boost 模式 (PERFBOOSTMODE, 隐藏设置但可写, 本机实测)
            FlowLayoutPanel cf3 = new FlowLayoutPanel();
            cf3.Dock = DockStyle.Fill;
            Label l11 = new Label(); l11.Text = "Boost 模式:"; l11.AutoSize = true; l11.Padding = new Padding(2, 6, 0, 0);
            _cboBoost = new ComboBox();
            _cboBoost.DropDownStyle = ComboBoxStyle.DropDownList;
            foreach (string bn in Collector.BOOST_NAMES) _cboBoost.Items.Add(bn);
            _cboBoost.Width = 190;
            Label l12 = new Label(); l12.Text = "(Turbo 频率策略, 隐藏设置)"; l12.AutoSize = true; l12.ForeColor = Color.DimGray; l12.Padding = new Padding(10, 6, 0, 0);
            Button btnBoost = new Button(); btnBoost.Text = "应用"; btnBoost.Width = 70;
            btnBoost.Click += delegate
            {
                if (_cboBoost.SelectedIndex < 0) return;
                string err = _collector.SetBoostMode(_cboBoost.SelectedIndex);
                SetTunStatus(err == null ? "Boost 模式已应用: " + Collector.BOOST_NAMES[_cboBoost.SelectedIndex] : "失败: " + err);
            };
            cf3.Controls.Add(l11); cf3.Controls.Add(_cboBoost);
            cf3.Controls.Add(l12); cf3.Controls.Add(btnBoost);
            // v6.5: EPP 能量性能偏好 (Speed Shift, 隐藏设置; 本机 A/B 实测: 空载时钟 -75%, 负载 -14%, GPU -4C @0->70)
            FlowLayoutPanel cf4 = new FlowLayoutPanel();
            cf4.Dock = DockStyle.Fill;
            Label l13 = new Label(); l13.Text = "能效偏好 插电:"; l13.AutoSize = true; l13.Padding = new Padding(2, 2, 0, 0);
            _trkAcEpp = new TrackBar(); _trkAcEpp.Minimum = 0; _trkAcEpp.Maximum = 100; _trkAcEpp.TickFrequency = 10; _trkAcEpp.Width = 180;
            Label l14 = new Label(); l14.Text = "电池:"; l14.AutoSize = true; l14.Padding = new Padding(6, 2, 0, 0);
            _trkDcEpp = new TrackBar(); _trkDcEpp.Minimum = 0; _trkDcEpp.Maximum = 100; _trkDcEpp.TickFrequency = 10; _trkDcEpp.Width = 180;
            Label l15 = new Label(); l15.Text = "0/84"; l15.AutoSize = true; l15.ForeColor = Color.DimGray; l15.Padding = new Padding(10, 2, 0, 0);
            Label l16 = new Label(); l16.Text = "(0=最高性能 100=最大省电; 调高可降温省电, 重载吞吐略降)"; l16.AutoSize = true; l16.ForeColor = Color.DimGray; l16.Padding = new Padding(10, 2, 0, 0);
            Button btnEpp = new Button(); btnEpp.Text = "应用"; btnEpp.Width = 70;
            _trkAcEpp.ValueChanged += delegate { l15.Text = _trkAcEpp.Value + "/" + _trkDcEpp.Value; };
            _trkDcEpp.ValueChanged += delegate { l15.Text = _trkAcEpp.Value + "/" + _trkDcEpp.Value; };
            btnEpp.Click += delegate
            {
                string err = Collector.ApplyPowerSetting(SUB_PROCESSOR, PERFEPP, _trkAcEpp.Value, _trkDcEpp.Value);
                SetTunStatus(err == null ? "能效偏好已应用: AC " + _trkAcEpp.Value + " / DC " + _trkDcEpp.Value : "失败: " + err);
            };
            cf4.Controls.Add(l13); cf4.Controls.Add(_trkAcEpp);
            cf4.Controls.Add(l14); cf4.Controls.Add(_trkDcEpp);
            cf4.Controls.Add(l15); cf4.Controls.Add(btnEpp); cf4.Controls.Add(l16);
            TableLayoutPanel cpuWrap = new TableLayoutPanel();
            cpuWrap.Dock = DockStyle.Fill;
            cpuWrap.ColumnCount = 1;
            cpuWrap.RowCount = 4;
            cpuWrap.RowStyles.Add(new RowStyle(SizeType.Percent, 25));
            cpuWrap.RowStyles.Add(new RowStyle(SizeType.Percent, 25));
            cpuWrap.RowStyles.Add(new RowStyle(SizeType.Percent, 25));
            cpuWrap.RowStyles.Add(new RowStyle(SizeType.Percent, 25));
            cpuWrap.Controls.Add(cf, 0, 0);
            cpuWrap.Controls.Add(cf2, 0, 1);
            cpuWrap.Controls.Add(cf3, 0, 2);
            cpuWrap.Controls.Add(cf4, 0, 3);
            cpuBox.Controls.Add(cpuWrap);
            root.Controls.Add(cpuBox, 0, 1);

            // ---- 超时 ----
            Panel toBox = GroupOf("超时 (分钟, 0=从不)", 0, 2, 1);
            FlowLayoutPanel tf = new FlowLayoutPanel();
            tf.Dock = DockStyle.Fill;
            Label l4 = new Label(); l4.Text = "屏幕关闭 插电:"; l4.AutoSize = true; l4.Padding = new Padding(2, 10, 0, 0);
            _numScreenAc = NewNum(0, 360);
            Label l5 = new Label(); l5.Text = "电池:"; l5.AutoSize = true; l5.Padding = new Padding(6, 10, 0, 0);
            _numScreenDc = NewNum(0, 360);
            Label l6 = new Label(); l6.Text = "睡眠 插电:"; l6.AutoSize = true; l6.Padding = new Padding(12, 10, 0, 0);
            _numSleepAc = NewNum(0, 360);
            Label l7 = new Label(); l7.Text = "电池:"; l7.AutoSize = true; l7.Padding = new Padding(6, 10, 0, 0);
            _numSleepDc = NewNum(0, 360);
            Button btnTo = new Button(); btnTo.Text = "应用"; btnTo.Width = 70;
            btnTo.Click += delegate
            {
                string e1 = Collector.ApplyPowerSetting(SUB_VIDEO, VIDEOIDLE, (int)_numScreenAc.Value * 60, (int)_numScreenDc.Value * 60);
                string e2 = Collector.ApplyPowerSetting(SUB_SLEEP, STANDBYIDLE, (int)_numSleepAc.Value * 60, (int)_numSleepDc.Value * 60);
                SetTunStatus(e1 == null && e2 == null ? "超时已应用" : "失败: " + (e1 ?? e2));
            };
            tf.Controls.Add(l4); tf.Controls.Add(_numScreenAc);
            tf.Controls.Add(l5); tf.Controls.Add(_numScreenDc);
            tf.Controls.Add(l6); tf.Controls.Add(_numSleepAc);
            tf.Controls.Add(l7); tf.Controls.Add(_numSleepDc);
            tf.Controls.Add(btnTo);
            toBox.Controls.Add(tf);
            root.Controls.Add(toBox, 0, 2);

            // ---- USB / PCIe 联动 ----
            Panel devBox = GroupOf("设备电源联动", 0, 3, 1);
            FlowLayoutPanel df = new FlowLayoutPanel();
            df.Dock = DockStyle.Fill;
            _chkUsbAc = MkChk("USB暂停·插电");
            _chkUsbDc = MkChk("USB暂停·电池");
            _chkAspmAc = MkChk("PCIe节能·插电");
            _chkAspmDc = MkChk("PCIe节能·电池");
            Button btnDev = new Button(); btnDev.Text = "应用"; btnDev.Width = 70;
            btnDev.Click += delegate
            {
                string e1 = Collector.ApplyPowerSetting(SUB_USB, USBSELECTIVESUSPEND, _chkUsbAc.Checked ? 1 : 0, _chkUsbDc.Checked ? 1 : 0);
                string e2 = Collector.ApplyPowerSetting(SUB_PCIEXPRESS, PCIE_ASPM, _chkAspmAc.Checked ? 1 : 0, _chkAspmDc.Checked ? 1 : 0);
                SetTunStatus(e1 == null && e2 == null ? "设备联动已应用" : "失败: " + (e1 ?? e2));
            };
            df.Controls.Add(_chkUsbAc); df.Controls.Add(_chkUsbDc);
            df.Controls.Add(_chkAspmAc); df.Controls.Add(_chkAspmDc);
            df.Controls.Add(btnDev);
            devBox.Controls.Add(df);
            root.Controls.Add(devBox, 0, 3);

            // ---- v6.6: 无线适配器功耗 (隐藏组, 免管理员) ----
            Panel wifiBox = GroupOf("无线适配器功耗 (Wi-Fi 档位)", 0, 4, 1);
            FlowLayoutPanel wf = new FlowLayoutPanel();
            wf.Dock = DockStyle.Fill;
            Label lw1 = new Label(); lw1.Text = "插电:"; lw1.AutoSize = true; lw1.Padding = new Padding(2, 10, 0, 0);
            _cboWifiAc = new ComboBox();
            _cboWifiAc.DropDownStyle = ComboBoxStyle.DropDownList;
            _cboWifiAc.Items.AddRange(Collector.WIRELESS_POWER_NAMES);
            _cboWifiAc.Width = 130;
            Label lw2 = new Label(); lw2.Text = "电池:"; lw2.AutoSize = true; lw2.Padding = new Padding(10, 10, 0, 0);
            _cboWifiDc = new ComboBox();
            _cboWifiDc.DropDownStyle = ComboBoxStyle.DropDownList;
            _cboWifiDc.Items.AddRange(Collector.WIRELESS_POWER_NAMES);
            _cboWifiDc.Width = 130;
            Button btnWifi = new Button(); btnWifi.Text = "应用"; btnWifi.Width = 70;
            btnWifi.Click += delegate
            {
                if (_cboWifiAc.SelectedIndex < 0 || _cboWifiDc.SelectedIndex < 0) return;
                string ew = Collector.ApplyPowerSetting(SUB_WIFI, WIRELESS_POWER, _cboWifiAc.SelectedIndex, _cboWifiDc.SelectedIndex);
                SetTunStatus(ew == null ? "无线功耗已应用: AC=" + _cboWifiAc.SelectedIndex + " DC=" + _cboWifiDc.SelectedIndex : "失败: " + ew);
            };
            wf.Controls.Add(lw1); wf.Controls.Add(_cboWifiAc);
            wf.Controls.Add(lw2); wf.Controls.Add(_cboWifiDc);
            wf.Controls.Add(btnWifi);
            wifiBox.Controls.Add(wf);
            root.Controls.Add(wifiBox, 0, 4);

            // ---- v6.1: Acer 硬件联动 (EC-WMI, 需管理员) ----
            Panel acerBox = GroupOf("Acer 硬件联动 (实验性, 需管理员)", 0, 5, 1);
            FlowLayoutPanel af = new FlowLayoutPanel();
            af.Dock = DockStyle.Fill;
            Label lblAcerNow = new Label();
            lblAcerNow.Text = "当前: --";
            lblAcerNow.AutoSize = true;
            lblAcerNow.Padding = new Padding(2, 10, 8, 0);
            _lblAcerNow = lblAcerNow;
            _cboAcerProfile = new ComboBox();
            _cboAcerProfile.DropDownStyle = ComboBoxStyle.DropDownList;
            _cboAcerProfile.Items.Add("安静 (低温低噪)");
            _cboAcerProfile.Items.Add("平衡 (默认)");
            _cboAcerProfile.Items.Add("性能 (全速)");
            _cboAcerProfile.Width = 140;
            Button btnAcer = new Button();
            btnAcer.Text = "应用配置";
            btnAcer.Width = 90;
            btnAcer.Click += delegate
            {
                if (_cboAcerProfile.SelectedIndex < 0) return;
                int prof = _cboAcerProfile.SelectedIndex + 1;
                string err = _collector.AcerSetProfile(prof);
                if (err == null)
                {
                    SetTunStatus("Acer 配置已切换: " + (prof == 1 ? "安静" : prof == 2 ? "平衡" : "性能"));
                    _lblAcerNow.Text = "当前: " + (prof == 1 ? "安静" : prof == 2 ? "平衡" : "性能");
                }
                else SetTunStatus("Acer 配置失败: " + err + " (需管理员权限运行)");
            };
            Label lblFan = new Label();
            lblFan.Text = "风扇: --";
            lblFan.AutoSize = true;
            lblFan.ForeColor = Color.DimGray;
            lblFan.Padding = new Padding(12, 10, 0, 0);
            _lblFanStatus = lblFan;
            af.Controls.Add(lblAcerNow);
            af.Controls.Add(_cboAcerProfile);
            af.Controls.Add(btnAcer);
            af.Controls.Add(lblFan);
            acerBox.Controls.Add(af);
            root.Controls.Add(acerBox, 0, 5);

            // ---- v6.3: NVIDIA PowerMizer (注册表, 实验性, 需管理员+重启生效) ----
            Panel pmBox = GroupOf("NVIDIA PowerMizer (实验性, 需管理员, 重启生效)", 0, 6, 1);
            FlowLayoutPanel pf = new FlowLayoutPanel();
            pf.Dock = DockStyle.Fill;
            Label lblPmNow = new Label();
            lblPmNow.Text = "当前: --";
            lblPmNow.AutoSize = true;
            lblPmNow.ForeColor = Color.DimGray;
            lblPmNow.Padding = new Padding(2, 10, 8, 0);
            _lblPmNow = lblPmNow;
            Button btnPmPerf = new Button();
            btnPmPerf.Text = "偏最高性能";
            btnPmPerf.Width = 110;
            btnPmPerf.Click += delegate
            {
                if (MessageBox.Show("将写入 PowerMizer 注册表值 (锁定高性能档)。\r\n需重启生效, 可随时\"恢复默认\"。\r\n\r\n继续?",
                    "PowerMizer", MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes) return;
                string err = _collector.SetPowerMizer(1);
                SetTunStatus(err == null ? "PowerMizer 已写入偏高性能 (重启后生效)" : "失败: " + err);
                RefreshPmLabel();
            };
            Button btnPmReset = new Button();
            btnPmReset.Text = "恢复驱动默认";
            btnPmReset.Width = 110;
            btnPmReset.Click += delegate
            {
                string err = _collector.SetPowerMizer(0);
                SetTunStatus(err == null ? "PowerMizer 已恢复驱动默认 (重启后生效)" : "失败: " + err);
                RefreshPmLabel();
            };
            // v6.4: 隐藏电源设置浏览器 (借鉴 PowerSettingsExplorer)
            Button btnHidden = new Button();
            btnHidden.Text = "隐藏设置浏览器";
            btnHidden.Width = 120;
            btnHidden.Click += delegate { ShowHiddenSettingsBrowser(); };
            pf.Controls.Add(lblPmNow);
            pf.Controls.Add(btnPmPerf);
            pf.Controls.Add(btnPmReset);
            pf.Controls.Add(btnHidden);
            pmBox.Controls.Add(pf);
            root.Controls.Add(pmBox, 0, 6);

            // ---- GPU/显示信息 (只读) ----
            Panel infoBox = GroupOf("GPU / 显示信息 (只读, ⚠=正在降频)", 0, 6, 1);
            _txtTuningInfo = new TextBox();
            _txtTuningInfo.Multiline = true;
            _txtTuningInfo.ReadOnly = true;
            _txtTuningInfo.ScrollBars = ScrollBars.Vertical;
            _txtTuningInfo.Dock = DockStyle.Fill;
            _txtTuningInfo.BackColor = SystemColors.Window;
            _txtTuningInfo.Font = new Font("Consolas", 9F);
            infoBox.Controls.Add(_txtTuningInfo);
            // v6.6: dGPU 断电辅助 — 检测无显示输出时的占用进程, 一键结束逼 Optimus 掉电
            // (Dock 逆序: 先加 Fill 再加 Top, Top 才能保留自己的带)
            FlowLayoutPanel gbf = new FlowLayoutPanel();
            gbf.Dock = DockStyle.Top;
            gbf.Height = 34;
            _btnKillGpuProc = new Button();
            _btnKillGpuProc.Text = "独显空闲";
            _btnKillGpuProc.Width = 170;
            _btnKillGpuProc.Enabled = false;
            _btnKillGpuProc.Click += delegate { KillGpuBusyProcs(); };
            Label lblGpuHint = new Label();
            lblGpuHint.Text = "无显示输出时被进程占用 → 独显无法掉电 (约 0.5-2W)";
            lblGpuHint.AutoSize = true;
            lblGpuHint.ForeColor = Color.DimGray;
            lblGpuHint.Padding = new Padding(8, 8, 0, 0);
            gbf.Controls.Add(_btnKillGpuProc);
            gbf.Controls.Add(lblGpuHint);
            infoBox.Controls.Add(gbf);
            root.Controls.Add(infoBox, 0, 7);

            _lblTunStatus = new Label();
            _lblTunStatus.Dock = DockStyle.Bottom;
            _lblTunStatus.Height = 24;
            _lblTunStatus.ForeColor = Color.DarkGreen;
            _lblTunStatus.Text = " ";
            page.Controls.Add(_lblTunStatus);
            page.Controls.Add(root);
            return page;
        }

        private NumericUpDown NewNum(int min, int max)
        {
            NumericUpDown n = new NumericUpDown();
            n.Minimum = min; n.Maximum = max;
            n.Width = 56;
            return n;
        }

        private CheckBox MkChk(string text)
        {
            CheckBox c = new CheckBox();
            c.Text = text;
            c.AutoSize = true;
            c.Padding = new Padding(4, 8, 8, 0);
            return c;
        }

        private void SetTunStatus(string msg)
        {
            try
            {
                _lblTunStatus.Text = DateTime.Now.ToString("HH:mm:ss") + "  " + msg;
                _lblTunStatus.ForeColor = msg.StartsWith("失败") ? Color.Firebrick : Color.DarkGreen;
            }
            catch { }
        }

        // v6.4: 隐藏电源设置浏览器 (借鉴 PowerSettingsExplorer: 定义库直读+隐藏可写)
        private void ShowHiddenSettingsBrowser()
        {
            List<Collector.PowerSettingInfo> all = _collector.EnumeratePowerSettings();
            if (all.Count == 0) { MessageBox.Show("枚举失败 (注册表不可读)"); return; }

            Form dlg = new Form();
            dlg.Text = "隐藏电源设置浏览器 (" + all.Count + " 项, 含隐藏; 修改经 powercfg 立即生效)";
            dlg.Size = new Size(880, 560);
            dlg.StartPosition = FormStartPosition.CenterParent;

            TableLayoutPanel root = new TableLayoutPanel();
            root.Dock = DockStyle.Fill;
            root.ColumnCount = 1;
            root.RowCount = 3;
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 36));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 80));

            FlowLayoutPanel top = new FlowLayoutPanel();
            top.Dock = DockStyle.Fill;
            Label lblF = new Label(); lblF.Text = "筛选:"; lblF.AutoSize = true; lblF.Padding = new Padding(2, 8, 0, 0);
            TextBox txtF = new TextBox(); txtF.Width = 200;
            CheckBox chkAll = new CheckBox(); chkAll.Text = "显示全部 (取消=仅隐藏项)"; chkAll.Checked = true; chkAll.AutoSize = true; chkAll.Padding = new Padding(10, 7, 0, 0);
            top.Controls.Add(lblF); top.Controls.Add(txtF); top.Controls.Add(chkAll);
            root.Controls.Add(top, 0, 0);

            ListView lv = new ListView();
            lv.View = View.Details; lv.FullRowSelect = true; lv.Dock = DockStyle.Fill;
            lv.Columns.Add("设置名", 300);
            lv.Columns.Add("子组", 130);
            lv.Columns.Add("隐藏", 50);
            lv.Columns.Add("AC 当前", 90, HorizontalAlignment.Right);
            lv.Columns.Add("DC 当前", 90, HorizontalAlignment.Right);
            lv.Columns.Add("GUID", 0);
            root.Controls.Add(lv, 0, 1);

            Action refill = delegate
            {
                string f = txtF.Text.Trim().ToLower();
                lv.BeginUpdate(); lv.Items.Clear();
                foreach (Collector.PowerSettingInfo info in all)
                {
                    if (!chkAll.Checked && !info.Hidden) continue;
                    if (f.Length > 0 && info.FriendlyName.ToLower().IndexOf(f) < 0
                        && info.SettingGuid.IndexOf(f, StringComparison.OrdinalIgnoreCase) < 0
                        && info.SubgroupName.ToLower().IndexOf(f) < 0) continue;
                    ListViewItem li = new ListViewItem(info.FriendlyName);
                    li.SubItems.Add(info.SubgroupName);
                    li.SubItems.Add(info.Hidden ? "是" : "");
                    li.SubItems.Add(info.CurrentAC);
                    li.SubItems.Add(info.CurrentDC);
                    li.Tag = info;
                    if (info.Hidden) li.ForeColor = Color.DimGray;
                    lv.Items.Add(li);
                }
                lv.EndUpdate();
            };
            txtF.TextChanged += delegate { refill(); };
            chkAll.CheckedChanged += delegate { refill(); };
            refill();

            FlowLayoutPanel bot = new FlowLayoutPanel();
            bot.Dock = DockStyle.Fill;
            Label lblSel = new Label(); lblSel.Text = "未选择"; lblSel.AutoSize = true; lblSel.ForeColor = Color.DimGray; lblSel.Padding = new Padding(2, 4, 0, 0);
            Label lblAc = new Label(); lblAc.Text = "AC值:"; lblAc.AutoSize = true; lblAc.Padding = new Padding(10, 4, 0, 0);
            TextBox txtAc = new TextBox(); txtAc.Width = 80;
            Label lblDc = new Label(); lblDc.Text = "DC值:"; lblDc.AutoSize = true; lblDc.Padding = new Padding(6, 4, 0, 0);
            TextBox txtDc = new TextBox(); txtDc.Width = 80;
            Button btnApply = new Button(); btnApply.Text = "应用"; btnApply.Width = 70;
            btnApply.Click += delegate
            {
                if (lv.SelectedItems.Count == 0) { MessageBox.Show("先选择设置项"); return; }
                Collector.PowerSettingInfo info = (Collector.PowerSettingInfo)lv.SelectedItems[0].Tag;
                int ac, dc;
                if (!int.TryParse(txtAc.Text.Trim(), out ac) || !int.TryParse(txtDc.Text.Trim(), out dc))
                { MessageBox.Show("值必须是十进制整数"); return; }
                DialogResult dr = MessageBox.Show(
                    "修改隐藏设置可能影响系统行为!\r\n\r\n" + info.FriendlyName + "\r\n" + info.SubgroupName + "\r\nAC=" + ac + " DC=" + dc + "\r\n\r\n继续?",
                    "确认修改", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
                if (dr != DialogResult.Yes) return;
                string err = Collector.SetPowerSettingRaw(info.SubgroupGuid, info.SettingGuid, ac, dc);
                if (err == null)
                {
                    info.CurrentAC = "0x" + ac.ToString("X");
                    info.CurrentDC = "0x" + dc.ToString("X");
                    lv.SelectedItems[0].SubItems[3].Text = info.CurrentAC;
                    lv.SelectedItems[0].SubItems[4].Text = info.CurrentDC;
                    SetTunStatus("已应用: " + info.FriendlyName + " AC=" + ac + " DC=" + dc);
                }
                else SetTunStatus("失败: " + err);
            };
            lv.SelectedIndexChanged += delegate
            {
                if (lv.SelectedItems.Count == 0) { lblSel.Text = "未选择"; return; }
                Collector.PowerSettingInfo info = (Collector.PowerSettingInfo)lv.SelectedItems[0].Tag;
                lblSel.Text = info.FriendlyName + " — " + (info.Description.Length > 60 ? info.Description.Substring(0, 60) + ".." : info.Description);
                if (info.CurrentAC.StartsWith("0x")) { int v; if (int.TryParse(info.CurrentAC.Substring(2), System.Globalization.NumberStyles.HexNumber, null, out v)) txtAc.Text = v.ToString(); }
                if (info.CurrentDC.StartsWith("0x")) { int v; if (int.TryParse(info.CurrentDC.Substring(2), System.Globalization.NumberStyles.HexNumber, null, out v)) txtDc.Text = v.ToString(); }
            };
            bot.Controls.Add(lblSel);
            bot.Controls.Add(lblAc); bot.Controls.Add(txtAc);
            bot.Controls.Add(lblDc); bot.Controls.Add(txtDc);
            bot.Controls.Add(btnApply);
            root.Controls.Add(bot, 0, 2);

            dlg.Controls.Add(root);
            dlg.ShowDialog(this);
        }

        // v6.4: 电源滑块 Overlay 切换 (Win11, 需管理员)
        private void SwitchOverlay(string guid, string name)
        {
            string err = _collector.SetActiveOverlay(guid);
            if (err == null)
            {
                SetTunStatus("电源滑块已切换: " + name);
                if (_lblOverlayNow != null) _lblOverlayNow.Text = "滑块: " + name;
            }
            else SetTunStatus("Overlay 切换失败: " + err);
        }

        // v6.6: 仅切电池侧 Overlay (A4 修正: 离电不再跟随插电挂最佳性能; 需管理员)
        private void SwitchOverlayDc(string guid, string name)
        {
            string err = _collector.SetActiveOverlayDc(guid);
            if (err == null)
            {
                SetTunStatus("电池侧滑块已切: " + name);
                if (_lblOverlayNow != null) _lblOverlayNow.Text = "滑块: " + name + " (仅电池侧)";
            }
            else MessageBox.Show("切换失败: " + err, "Overlay", MessageBoxButtons.OK, MessageBoxIcon.Warning);
        }

        // v6.6: 结束独显占用进程 → 逼 Optimus 掉电 (LLT "Deactivate GPU" 的零依赖简化版)
        // M: 关键系统进程保护名单 (KillGpu/KillSelected/Suspend 共用; KillGpu 的 dwm 教训)
        private static readonly string[] CriticalProcs = new string[] { "dwm", "csrss", "wininit", "winlogon",
            "services", "lsass", "svchost", "explorer", "system", "memory compression", "smss", "fontdrvhost" };
        private static bool IsCriticalProc(string name)
        {
            return Array.IndexOf(CriticalProcs, (name ?? "").ToLowerInvariant()) >= 0;
        }

        private void KillGpuBusyProcs()
        {
            if (_gpuBusyPids.Count == 0) return;
            // C5修复: 确认框 + 关键系统进程白名单 (原实现可杀 dwm → 黑屏闪烁)
            if (MessageBox.Show("确定结束占用独显的进程? 结束后应用未保存内容会丢失", "确认",
                MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes) return;
            int selfPid = System.Diagnostics.Process.GetCurrentProcess().Id;
            List<string> names = new List<string>();
            foreach (int pid in _gpuBusyPids.ToArray())
            {
                if (pid == selfPid) continue;
                string nm = "?";
                try
                {
                    using (Process pr = Process.GetProcessById(pid))
                    {
                        nm = pr.ProcessName;
                        if (IsCriticalProc(nm)) continue;   // 白名单跳过
                        pr.Kill();
                    }
                }
                catch { continue; }   // C5: Kill 失败不计入成功名单
                names.Add(nm);
            }
            RecordAlert("dGPU 断电辅助: 已结束 " + string.Join(", ", names.ToArray()));
            SetTunStatus("已结束: " + string.Join(", ", names.ToArray()) + " — 等待独显掉电…");
            // 3 秒后重新检测 (掉电需要几秒)
            System.Threading.ThreadPool.QueueUserWorkItem(delegate
            {
                System.Threading.Thread.Sleep(3000);
                try { BeginInvoke((MethodInvoker)delegate { _lastTuningLoad = DateTime.MinValue; LoadTuningState(); }); } catch { }
            });
        }

        // 进入调优页时读取当前状态 (低频, 5s 节流)
        private DateTime _lastTuningLoad = DateTime.MinValue;
        private void LoadTuningState()
        {
            if (_tuningBusy || (DateTime.Now - _lastTuningLoad).TotalSeconds < 5) return;
            _lastTuningLoad = DateTime.Now;
            _tuningBusy = true;
            try
            {
                if (!_tuningLoaded)
                {
                    int? br = _collector.GetBrightness();
                    if (br.HasValue) { _trkBright.Value = Math.Max(0, Math.Min(100, br.Value)); _lblBrightNow.Text = "亮度 " + br.Value + "%"; }
                    int?[] cpuMax = Collector.ReadPowerSetting(SUB_PROCESSOR, PROCTHROTTLEMAX);
                    if (cpuMax[0].HasValue) _trkAcMax.Value = Math.Max(50, Math.Min(100, cpuMax[0].Value));
                    if (cpuMax[1].HasValue) _trkDcMax.Value = Math.Max(50, Math.Min(100, cpuMax[1].Value));
                    int?[] vid = Collector.ReadPowerSetting(SUB_VIDEO, VIDEOIDLE);
                    if (vid[0].HasValue) _numScreenAc.Value = Math.Max(0, Math.Min(360, vid[0].Value / 60));
                    if (vid[1].HasValue) _numScreenDc.Value = Math.Max(0, Math.Min(360, vid[1].Value / 60));
                    int?[] slp = Collector.ReadPowerSetting(SUB_SLEEP, STANDBYIDLE);
                    if (slp[0].HasValue) _numSleepAc.Value = Math.Max(0, Math.Min(360, slp[0].Value / 60));
                    if (slp[1].HasValue) _numSleepDc.Value = Math.Max(0, Math.Min(360, slp[1].Value / 60));
                    int?[] usb = Collector.ReadPowerSetting(SUB_USB, USBSELECTIVESUSPEND);
                    if (usb[0].HasValue) _chkUsbAc.Checked = usb[0].Value != 0;
                    if (usb[1].HasValue) _chkUsbDc.Checked = usb[1].Value != 0;
                    int?[] aspm = Collector.ReadPowerSetting(SUB_PCIEXPRESS, PCIE_ASPM);
                    if (aspm[0].HasValue) _chkAspmAc.Checked = aspm[0].Value != 0;
                    if (aspm[1].HasValue) _chkAspmDc.Checked = aspm[1].Value != 0;
                    // v6.6: 无线功耗档位
                    int?[] wifi = _collector.ReadWirelessPower();
                    if (wifi[0].HasValue && wifi[0].Value >= 0 && wifi[0].Value <= 3) _cboWifiAc.SelectedIndex = wifi[0].Value;
                    if (wifi[1].HasValue && wifi[1].Value >= 0 && wifi[1].Value <= 3) _cboWifiDc.SelectedIndex = wifi[1].Value;
                    if (_cboWifiAc.SelectedIndex < 0) _cboWifiAc.SelectedIndex = 0;   // 未覆盖=系统默认, 视同最高性能档显示
                    if (_cboWifiDc.SelectedIndex < 0) _cboWifiDc.SelectedIndex = 0;
                    // v6.2: 最小处理器状态 + 自适应亮度
                    int?[] pmin = Collector.ReadPowerSetting(SUB_PROCESSOR, PROCTHROTTLEMIN);
                    if (pmin[0].HasValue) _numMinAc.Value = Math.Max(0, Math.Min(100, pmin[0].Value));
                    if (pmin[1].HasValue) _numMinDc.Value = Math.Max(0, Math.Min(100, pmin[1].Value));
                    int?[] adp = Collector.ReadPowerSetting(SUB_VIDEO, Collector.ADAPTBRIGHT_GUID);
                    if (adp[0].HasValue) _chkAdaptive.Checked = adp[0].Value != 0;
                    // v6.4: Boost 模式
                    int? boost = _collector.ReadBoostMode();
                    if (boost.HasValue && boost.Value >= 0 && boost.Value <= 5) _cboBoost.SelectedIndex = boost.Value;
                    // v6.5: EPP (隐藏设置, 注册表直读)
                    int?[] epp = _collector.ReadEpp();
                    if (epp[0].HasValue) _trkAcEpp.Value = Math.Max(0, Math.Min(100, epp[0].Value));
                    if (epp[1].HasValue) _trkDcEpp.Value = Math.Max(0, Math.Min(100, epp[1].Value));
                    _tuningLoaded = true;
                }
                // GPU/显示信息 (只读, 每次进页刷新)
                // v6.3: 深度解析 (P状态/时钟/功耗墙/降频原因/PCIe)
                Collector.NvidiaDeep deep = _collector.QueryNvidiaDeep();
                List<string> disp = _collector.GetDisplayInfo();
                StringBuilder sb = new StringBuilder();
                sb.AppendLine("== NVIDIA 深度 (nvidia-smi -q) ==");
                foreach (string g in deep.Lines) sb.AppendLine("  " + g);
                if (deep.ThrottleSwThermal || deep.ThrottleHwThermal || deep.ThrottleSwPowerCap)
                {
                    sb.AppendLine("  ⚠ GPU 正在降频 (Optimus 共享散热预算属正常, 持续请改善散热)");
                    if ((DateTime.Now - _lastThrottleAlert).TotalMinutes > 10)
                    {
                        _lastThrottleAlert = DateTime.Now;
                        RecordAlert("GPU 降频: " + (deep.ThrottleSwThermal ? "SW热降频 " : "") + (deep.ThrottleSwPowerCap ? "SW功耗墙" : ""));
                    }
                }
                string util = _collector.QueryNvidiaUtilDetail();
                if (util.Length > 0) sb.AppendLine("  利用率: " + util);
                // v6.6: dGPU 断电辅助 — 无显示输出时检测占用进程 (GPU Engine 每进程计数器)
                _gpuBusyPids.Clear();
                if (deep.DisplayActive == "Disabled" && _last != null)
                {
                    foreach (KeyValuePair<int, float> kv in _last.GpuPerProc)
                    {
                        if (kv.Value < 0.5f) continue;
                        string nm = "?";
                        try { using (Process pr = Process.GetProcessById(kv.Key)) nm = pr.ProcessName; } catch { }
                        _gpuBusyPids.Add(kv.Key);
                        sb.AppendLine("  ⚡ 独显被占用: " + nm + " (PID " + kv.Key + ", " + kv.Value.ToString("F0") + "%) — 结束后独显方可掉电");
                    }
                }
                if (_btnKillGpuProc != null)
                {
                    bool busy = _gpuBusyPids.Count > 0;
                    _btnKillGpuProc.Enabled = busy;
                    _btnKillGpuProc.Text = busy ? "结束占用进程(" + _gpuBusyPids.Count + ")并断电" : "独显空闲";
                }
                sb.AppendLine("== 显示适配器 ==");
                foreach (string d in disp) sb.AppendLine("  " + d);
                sb.AppendLine("(注: Boost模式/充电阈值 本机固件未暴露; 风扇手动速度编码未验证, 仅提供状态只读)");
                _txtTuningInfo.Text = sb.ToString();
                // v6.3: PowerMizer 状态
                RefreshPmLabel();

                // v6.1: Acer 硬件联动状态
                try
                {
                    if (_collector.AcerAvailable())
                    {
                        int? prof = _collector.AcerGetProfile();
                        if (prof.HasValue)
                        {
                            _lblAcerNow.Text = "当前: " + (prof.Value == 1 ? "安静" : prof.Value == 2 ? "平衡" : prof.Value == 3 ? "性能" : ("未知(" + prof.Value + ")"));
                            if (prof.Value >= 1 && prof.Value <= 3) _cboAcerProfile.SelectedIndex = prof.Value - 1;
                        }
                        else _lblAcerNow.Text = "当前: 读取失败";
                        int?[] fan = _collector.AcerGetFanStatus();
                        if (fan != null)
                            _lblFanStatus.Text = "风扇: 行为=" + fan[0] + " 速度=" + fan[1] + " (2=自动)";
                        else
                            _lblFanStatus.Text = "风扇: 读取失败";
                    }
                    else
                    {
                        _lblAcerNow.Text = "当前: 不可用 (需管理员)";
                        _lblFanStatus.Text = "风扇: 不可用";
                    }
                }
                catch { }
            }
            catch { }
            finally { _tuningBusy = false; }
        }

        // ---- v3.3: 系统维护页 ----
        private TextBox _txtMaintenance;
        private TabPage BuildMaintenancePage()
        {
            TabPage page = new TabPage("维护");
            TableLayoutPanel root = new TableLayoutPanel();
            root.Dock = DockStyle.Fill;
            root.ColumnCount = 1;
            root.RowCount = 2;
            root.Padding = new Padding(12);
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 46));

            Panel svcBox = GroupOf("系统维护", 0, 0, 1);
            _txtMaintenance = new TextBox();
            _txtMaintenance.Multiline = true;
            _txtMaintenance.ReadOnly = true;
            _txtMaintenance.ScrollBars = ScrollBars.Both;
            _txtMaintenance.Dock = DockStyle.Fill;
            _txtMaintenance.BackColor = SystemColors.Window;
            _txtMaintenance.Font = new Font("Consolas", 9F);
            svcBox.Controls.Add(_txtMaintenance);
            root.Controls.Add(svcBox, 0, 0);

            FlowLayoutPanel btnRow = new FlowLayoutPanel();
            btnRow.Dock = DockStyle.Fill;
            Button btnRefresh = new Button();
            btnRefresh.Text = "刷新";
            btnRefresh.Width = 80;
            btnRefresh.Click += delegate { UpdateMaintenancePage(); };
            Button btnSvc = new Button();
            btnSvc.Text = "服务管理";
            btnSvc.Width = 90;
            btnSvc.Click += delegate { ShowServiceManager(); };
            Button btnStartup = new Button();
            btnStartup.Text = "启动项管理";
            btnStartup.Width = 100;
            btnStartup.Click += delegate { ShowStartupManager(); };
            Button btnExport = new Button();
            btnExport.Text = "导出快照JSON";
            btnExport.Width = 120;
            btnExport.Click += delegate { ExportSnapshot(); };
            Button btnAlerts = new Button();
            btnAlerts.Text = "告警历史";
            btnAlerts.Width = 90;
            btnAlerts.Click += delegate { ShowAlertHistory(); };
            Button btnEnergy = new Button();
            btnEnergy.Text = "能耗报告(管理员)";
            btnEnergy.Width = 130;
            btnEnergy.Click += delegate { RunEnergyReport(); };
            btnRow.Controls.Add(btnRefresh);
            btnRow.Controls.Add(btnSvc);
            btnRow.Controls.Add(btnStartup);
            btnRow.Controls.Add(btnExport);
            btnRow.Controls.Add(btnAlerts);
            btnRow.Controls.Add(btnEnergy);
            root.Controls.Add(btnRow, 0, 1);

            page.Controls.Add(root);
            return page;
        }

        private void UpdateMaintenancePage()
        {
            if (_last == null) return;
            Snapshot s = _last;
            StringBuilder sb = new StringBuilder();

            // 内核版本
            sb.AppendLine("=== 系统信息 ===");
            sb.AppendLine("系统: " + s.KernelVersion);

            // v5: 传感器面板 (HWiNFO 风格, 管理员可用)
            sb.AppendLine();
            if (s.LhmAllSensors.Count > 0)
            {
                sb.AppendLine("=== 传感器 (" + s.LhmAllSensors.Count + " 项, LHM) ===");
                foreach (string sen in s.LhmAllSensors) sb.AppendLine("  " + sen);
            }
            else
                sb.AppendLine("=== 传感器 ===\n  (需管理员权限重启后可用)");

            // v5: 磁盘健康
            if (s.DiskHealth.Count > 0)
            {
                sb.AppendLine();
                sb.AppendLine("=== 磁盘健康 ===");
                foreach (string d in s.DiskHealth) sb.AppendLine("  " + d);
            }

            // v5: 网卡详情 (Mission Center 风格)
            if (s.NicInfos.Count > 0)
            {
                sb.AppendLine();
                sb.AppendLine("=== 网络接口 ===");
                foreach (string ni in s.NicInfos) sb.AppendLine("  " + ni);
                sb.AppendLine("  今日流量: " + (s.TodayRxMB / 1024.0).ToString("F2") + " GB");
            }

            // 服务状态
            sb.AppendLine();
            sb.AppendLine("=== 关键服务 ===");
            foreach (ServiceInfo svc in s.Services)
            {
                string icon = svc.Status == "Running" ? "[运行]" : (svc.Status == "Stopped" ? "[停止]" : "[未知]");
                sb.AppendLine(icon + " " + svc.DisplayName + " (" + svc.Name + ") — " + svc.Status);
            }

            // 启动项
            sb.AppendLine();
            sb.AppendLine("=== 启动项 (" + s.StartupItems.Length + " 个) ===");
            foreach (string item in s.StartupItems)
                sb.AppendLine("  " + item);

            // v5: 最近系统事件
            if (s.RecentEvents.Count > 0)
            {
                sb.AppendLine();
                sb.AppendLine("=== 最近 24h 系统事件 (错误/警告) ===");
                foreach (string ev in s.RecentEvents) sb.AppendLine("  " + ev);
            }

            // 进程排行
            sb.AppendLine();
            sb.AppendLine("=== Top-15 进程 (按累计CPU时间) ===");
            sb.AppendLine(string.Format("{0,-24} {1,-8} {2,-10} {3,-10}", "名称", "PID", "CPU累计(s)", "内存MB"));
            sb.AppendLine(new string('-', 56));
            foreach (ProcessPowerInfo p in s.TopProcesses)
                sb.AppendLine(string.Format("{0,-24} {1,-8} {2,-10:F1} {3,-10}", p.Name, p.Pid, p.CpuPct, p.MemMB));

            _txtMaintenance.Text = sb.ToString();
        }

        // v5: 服务管理对话框 (启动/停止/重启)
        private void ShowServiceManager()
        {
            if (_last == null) return;
            Form dlg = new Form();
            dlg.Text = "服务管理 (部分操作需管理员)";
            dlg.Size = new Size(560, 420);
            dlg.StartPosition = FormStartPosition.CenterParent;
            ListView lv = new ListView();
            lv.Dock = DockStyle.Fill;
            lv.View = View.Details;
            lv.FullRowSelect = true;
            lv.Columns.Add("服务", 200);
            lv.Columns.Add("名称", 140);
            lv.Columns.Add("状态", 90);
            foreach (ServiceInfo svc in _last.Services)
            {
                ListViewItem li = new ListViewItem(svc.DisplayName);
                li.SubItems.Add(svc.Name);
                li.SubItems.Add(svc.Status);
                li.Tag = svc.Name;
                lv.Items.Add(li);
            }
            Panel bp = new Panel();
            bp.Dock = DockStyle.Bottom;
            bp.Height = 40;
            Action<string> doSvc = delegate(string action)
            {
                if (lv.SelectedItems.Count == 0) return;
                string name = (string)lv.SelectedItems[0].Tag;
                try
                {
                    using (System.ServiceProcess.ServiceController sc =
                        new System.ServiceProcess.ServiceController(name))
                    {
                        // C6: 按动作等待对应状态 (原无条件等 Running 导致"停止"必超时假失败)
                        if (action == "start") { sc.Start(); sc.WaitForStatus(System.ServiceProcess.ServiceControllerStatus.Running, TimeSpan.FromSeconds(10)); }
                        else if (action == "stop") { sc.Stop(); sc.WaitForStatus(System.ServiceProcess.ServiceControllerStatus.Stopped, TimeSpan.FromSeconds(10)); }
                        else { sc.Stop(); sc.WaitForStatus(System.ServiceProcess.ServiceControllerStatus.Stopped, TimeSpan.FromSeconds(10)); sc.Start(); sc.WaitForStatus(System.ServiceProcess.ServiceControllerStatus.Running, TimeSpan.FromSeconds(10)); }
                    }
                    MessageBox.Show("服务已 " + action + ": " + name);
                    UpdateMaintenancePage();
                    dlg.Close();
                }
                catch (Exception ex) { MessageBox.Show("操作失败: " + ex.Message + "（可能需要管理员权限）"); }
            };
            string[] labels = new string[] { "启动", "停止", "重启" };
            string[] acts = new string[] { "start", "stop", "restart" };
            for (int i = 0; i < 3; i++)
            {
                string a = acts[i];
                Button b = new Button();
                b.Text = labels[i];
                b.Width = 80;
                b.Location = new Point(10 + i * 90, 6);
                b.Click += delegate { doSvc(a); };
                bp.Controls.Add(b);
            }
            dlg.Controls.Add(lv);
            dlg.Controls.Add(bp);
            dlg.ShowDialog(this);
        }

        // v5: 启动项管理对话框 (删除注册表 Run 项)
        private void ShowStartupManager()
        {
            Form dlg = new Form();
            dlg.Text = "启动项管理 (删除 = 移除注册表值, 需谨慎)";
            dlg.Size = new Size(620, 400);
            dlg.StartPosition = FormStartPosition.CenterParent;
            ListBox lb = new ListBox();
            lb.Dock = DockStyle.Fill;
            lb.Font = new Font("Consolas", 9F);
            List<KeyValuePair<string, string>> entries = new List<KeyValuePair<string, string>>(); // hive\value → display
            try
            {
                string[][] hives = new string[][] {
                    new string[] { "HKCU", "Software\\Microsoft\\Windows\\CurrentVersion\\Run" },
                    new string[] { "HKLM", "Software\\Microsoft\\Windows\\CurrentVersion\\Run" }
                };
                foreach (string[] hv in hives)
                {
                    Microsoft.Win32.RegistryKey baseKey = hv[0] == "HKCU" ? Microsoft.Win32.Registry.CurrentUser : Microsoft.Win32.Registry.LocalMachine;
                    using (Microsoft.Win32.RegistryKey k = baseKey.OpenSubKey(hv[1]))
                    {
                        if (k == null) continue;
                        foreach (string val in k.GetValueNames())
                        {
                            string disp = "[" + hv[0] + "] " + val + " = " + k.GetValue(val, "");
                            entries.Add(new KeyValuePair<string, string>(hv[0] + "|" + hv[1] + "|" + val, disp));
                            lb.Items.Add(disp);
                        }
                    }
                }
            }
            catch (Exception ex) { MessageBox.Show("读取失败: " + ex.Message); }
            Panel bp = new Panel();
            bp.Dock = DockStyle.Bottom;
            bp.Height = 40;
            Button btnDel = new Button();
            btnDel.Text = "删除选中项";
            btnDel.Width = 110;
            btnDel.Location = new Point(10, 6);
            btnDel.Click += delegate
            {
                if (lb.SelectedIndex < 0 || lb.SelectedIndex >= entries.Count) return;
                string key = entries[lb.SelectedIndex].Key;
                string[] parts = key.Split('|');
                DialogResult dr = MessageBox.Show("确定删除启动项?\r\n" + entries[lb.SelectedIndex].Value,
                    "确认", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
                if (dr != DialogResult.Yes) return;
                try
                {
                    Microsoft.Win32.RegistryKey baseKey = parts[0] == "HKCU" ? Microsoft.Win32.Registry.CurrentUser : Microsoft.Win32.Registry.LocalMachine;
                    using (Microsoft.Win32.RegistryKey k = baseKey.OpenSubKey(parts[1], true))
                    {
                        if (k != null) k.DeleteValue(parts[2]);
                    }
                    int delIdx = lb.SelectedIndex;
                    lb.Items.RemoveAt(delIdx);
                    if (delIdx < entries.Count) entries.RemoveAt(delIdx);   // C3: 同步索引, 防误删下一条
                    MessageBox.Show("已删除 (HKLM 项需管理员权限)");
                }
                catch (Exception ex) { MessageBox.Show("删除失败: " + ex.Message + "（HKLM 需管理员权限）"); }
            };
            bp.Controls.Add(btnDel);
            dlg.Controls.Add(lb);
            dlg.Controls.Add(bp);
            dlg.ShowDialog(this);
        }

        // v6.2: 能耗诊断报告 (powercfg /energy, 需管理员, 约60秒)
        private void RunEnergyReport()
        {
            try
            {
                string path = Path.Combine(Path.GetTempPath(), "energy-report.html");
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = "powercfg";
                psi.Arguments = "/energy /output \"" + path + "\" /duration 10";
                psi.Verb = "runas";
                psi.UseShellExecute = true;
                psi.WindowStyle = ProcessWindowStyle.Hidden;
                Process.Start(psi);
                MessageBox.Show("能耗诊断已启动 (需管理员授权, 约 10 秒采样)。\r\n完成后报告位于:\r\n" + path,
                    "能耗报告", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (Exception ex) { MessageBox.Show("启动失败: " + ex.Message + "（UAC 被取消或无权限）"); }
        }

        // v5: 告警历史
        private List<string> _alertHistory = new List<string>();        private void RecordAlert(string msg)
        {
            _alertHistory.Insert(0, DateTime.Now.ToString("MM-dd HH:mm:ss") + "  " + msg);
            if (_alertHistory.Count > 100) _alertHistory.RemoveAt(100);
        }

        private void ShowAlertHistory()
        {
            Form dlg = new Form();
            dlg.Text = "告警历史 (本次运行)";
            dlg.Size = new Size(560, 400);
            dlg.StartPosition = FormStartPosition.CenterParent;
            TextBox txt = new TextBox();
            txt.Dock = DockStyle.Fill;
            txt.Multiline = true;
            txt.ReadOnly = true;
            txt.ScrollBars = ScrollBars.Vertical;
            txt.Font = new Font("Consolas", 9F);
            txt.Text = _alertHistory.Count > 0 ? string.Join("\r\n", _alertHistory.ToArray()) : "(暂无告警记录)";
            dlg.Controls.Add(txt);
            dlg.ShowDialog(this);
        }

        // v5: 导出当前快照 (Glances 风格 JSON)
        private void ExportSnapshot()
        {
            if (_last == null) { MessageBox.Show("请等待数据采集完成"); return; }
            try
            {
                Snapshot s = _last;
                string path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                    "SysConsole快照_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".json");
                StringBuilder j = new StringBuilder();
                j.AppendLine("{");
                j.AppendLine("  \"time\": \"" + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "\",");
                j.AppendLine("  \"cpu_total_pct\": " + s.CpuTotal.ToString("F1") + ",");
                j.AppendLine("  \"mem_used_pct\": " + s.MemUsedPct.ToString("F1") + ",");
                j.AppendLine("  \"mem_used_mb\": " + s.MemUsedMB + ",");
                j.AppendLine("  \"gpu_util\": " + FmtN(s.NvidiaUtil) + ",");
                j.AppendLine("  \"gpu_temp\": " + FmtN(s.NvidiaTemp) + ",");
                j.AppendLine("  \"cpu_temp\": " + (s.LhmCpuTempBest.HasValue ? s.LhmCpuTempBest.Value.ToString("F1") : "null") + ",");
                j.AppendLine("  \"disk_busy\": " + s.DiskBusy.ToString("F1") + ",");
                j.AppendLine("  \"battery_pct\": " + s.BatteryPct + ",");
                j.AppendLine("  \"power\": \"" + s.PowerLine + "\",");
                j.AppendLine("  \"plan\": \"" + s.ActivePlanName + "\",");
                j.AppendLine("  \"uptime\": \"" + s.UptimeText + "\",");
                j.AppendLine("  \"today_traffic_mb\": " + s.TodayRxMB.ToString("F1") + ",");
                j.AppendLine("  \"proc_count\": " + s.SysProcCount + ",");
                j.AppendLine("  \"thread_count\": " + s.SysThreadCount);
                j.AppendLine("}");
                File.WriteAllText(path, j.ToString(), System.Text.Encoding.UTF8);
                MessageBox.Show("已导出: " + path, "导出成功", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (Exception ex) { MessageBox.Show("导出失败: " + ex.Message); }
        }

        private void AddAction(FlowLayoutPanel p, string text, EventHandler h)
        {
            Button b = new Button();
            b.Text = text;
            b.AutoSize = true;
            b.Click += h;
            p.Controls.Add(b);
        }

        private Panel GroupOf(string title, int col, int row, int span)
        {
            Panel g = new Panel();
            g.Dock = DockStyle.Fill;
            g.Margin = new Padding(4);
            g.Padding = new Padding(6, 24, 6, 6);   // v6.6: 顶部预留标题带 (修复标题被内容覆盖)
            g.BorderStyle = BorderStyle.FixedSingle;
            if (!string.IsNullOrEmpty(title))
            {
                Label t = new Label();
                t.Text = title;
                t.AutoSize = true;
                t.ForeColor = Color.DimGray;
                t.Location = new Point(3, 4);
                g.Controls.Add(t);
            }
            return g;
        }

        private Label MakeCard(TableLayoutPanel root, int col, int row, string caption)
        {
            Panel card = new Panel();
            card.Dock = DockStyle.Fill;
            card.Margin = new Padding(4);
            card.BorderStyle = BorderStyle.FixedSingle;
            Label cap = new Label();
            cap.Text = caption;
            cap.ForeColor = Color.DimGray;
            cap.AutoSize = true;
            cap.Location = new Point(8, 4);
            Label val = new Label();
            val.Text = "--";
            val.Font = new Font("Segoe UI", 16F, FontStyle.Bold);
            val.AutoSize = true;
            val.Location = new Point(8, 24);
            card.Controls.Add(cap);
            card.Controls.Add(val);
            root.Controls.Add(card, col, row);
            val.Tag = caption;
            return val;
        }

        // ================= 托盘 =================
        private NotifyIcon _tray;
        private void BuildTray()
        {
            _tray = new NotifyIcon();
            _tray.Icon = SystemIcons.Application;
            _tray.Text = "系统控制台";
            _tray.Visible = true;
            ContextMenu menu = new ContextMenu();

            // v4.1: 电源计划子菜单 (仿 Linux tray_menu.py, Popup 时动态填充)
            _traySceneItem = new MenuItem("电源计划");
            _traySceneItem.Popup += delegate
            {
                _traySceneItem.MenuItems.Clear();
                try
                {
                    List<PowerPlan> plans = _collector.ListPowerPlans();
                    foreach (PowerPlan p in plans)
                    {
                        string guid = p.Guid;
                        MenuItem mi = new MenuItem(p.Name + (p.IsActive ? "  ✓" : ""), delegate
                        {
                            string err = Collector.SwitchPowerPlan(guid);
                            if (err != null) MessageBox.Show("切换失败: " + err, "电源计划");
                            else { LoadScenePlans(); ReloadPlans(); }
                        });
                        _traySceneItem.MenuItems.Add(mi);
                    }
                }
                catch { }
            };

            // v4.1: 状态行 (OnTick 更新)
            _trayStatusItem = new MenuItem("状态: -");
            _trayStatusItem.Enabled = false;

            MenuItem miAnalysis = new MenuItem("电池科学分析", delegate { ShowUp(); ShowBatteryAnalysis(); });
            MenuItem miWidget = new MenuItem("悬浮窗", delegate { ToggleWidget(); });

            menu.MenuItems.Add("显示主窗", delegate { ShowUp(); });
            menu.MenuItems.Add("-");
            menu.MenuItems.Add(_traySceneItem);
            menu.MenuItems.Add(_trayStatusItem);
            menu.MenuItems.Add(miWidget);
            menu.MenuItems.Add(miAnalysis);
            menu.MenuItems.Add("-");
            menu.MenuItems.Add("退出", delegate { _reallyExit = true; Close(); });
            _tray.ContextMenu = menu;
            _tray.DoubleClick += delegate { ShowUp(); };
        }

        private void ShowUp()
        {
            Show();
            WindowState = FormWindowState.Normal;
            Activate();
            _timer.Interval = _baseIntervalMs;
        }

        // ================= 主循环 =================
        private void OnTick(object sender, EventArgs e)
        {
            _tickCount++;
            try { _last = _collector.Sample(); } catch { return; }
            Snapshot s = _last;
            if (s == null) return;

            // v3: 性能日志记录
            try { _collector.LogSample(s); } catch { }

            // 托盘 tooltip (≤63 字符)
            try
            {
                _tray.Text = string.Format("CPU {0:F0}%  RAM {1:F0}%  {2}",
                    s.CpuTotal, s.MemUsedPct,
                    s.BatteryPct >= 0 ? ("电池 " + s.BatteryPct + "%") : s.PowerLine);
            }
            catch { }

            // v3: 电源状态徽标
            try
            {
                if (s.PowerLine == "已接通电源")
                {
                    _lblPowerBadge.Text = "AC";
                    _lblPowerBadge.ForeColor = Color.DarkGreen;
                }
                else if (s.PowerLine == "使用电池")
                {
                    _lblPowerBadge.Text = "DC";
                    _lblPowerBadge.ForeColor = Color.DarkOrange;
                }
                else
                {
                    _lblPowerBadge.Text = "??";
                    _lblPowerBadge.ForeColor = Color.Gray;
                }
            }
            catch { }

            // v4.1: AC/DC 自动切换 (含冷启动归位)
            try
            {
                if (s.PowerLine != _lastPowerLine)
                {
                    bool first = (_lastPowerLine.Length == 0);
                    _lastPowerLine = s.PowerLine;
                    ApplyAutoSwitch(s.PowerLine);
                    if (first) Program.Trace("AC/DC 初始状态: " + s.PowerLine);
                }
            }
            catch { }

            // v4.1: 负载建议器 (持续高负载+电池供电 → 气泡建议, 不自动切)
            try
            {
                string adv = _advisor.Feed(s.CpuTotal, s.PowerLine == "使用电池", DateTime.Now);
                if (adv != null && _alertsEnabled && _tray != null)
                    _tray.ShowBalloonTip(8000, "性能建议", adv, ToolTipIcon.Info);
            }
            catch { }

            // v4.1: 托盘状态行
            try
            {
                if (_trayStatusItem != null)
                    _trayStatusItem.Text = "状态: " + (s.PowerLine == "已接通电源" ? "插电" : s.PowerLine == "使用电池" ? "离电" : "?")
                        + " | " + (string.IsNullOrEmpty(s.ActivePlanName) ? "?" : s.ActivePlanName);
            }
            catch { }

            // v5: 悬浮窗 + 托盘数字图标
            UpdateWidget(s);
            UpdateTrayIconLive(s);

            bool ov = _tabs.SelectedTab != null && _tabs.SelectedIndex == 0;
            if (ov || _tickCount % 5 == 0) // 失焦时也低频刷新卡片
            {
                _lblCpuVal.Text = s.CpuTotal.ToString("F0") + "%";
                _lblMemVal.Text = s.MemUsedPct.ToString("F0") + "%";
                _lblGpuVal.Text = s.Gpu3D.HasValue ? s.Gpu3D.Value.ToString("F0") + "%" : "N/A";
                _lblBatVal.Text = s.BatteryPct >= 0 ? s.BatteryPct + "%" : "--";

                _lblUptime.Text = "开机时长: " + s.UptimeText;
                _lblDiskIo.Text = string.Format("磁盘: {0:F0}% 繁忙 | {1:F0} KB/s",
                    s.DiskBusy, s.DiskBytesPerSec / 1024);
                StringBuilder nb = new StringBuilder("网络:");
                foreach (KeyValuePair<string, float[]> kv in s.NetPerNic)
                    nb.Append(string.Format(" [{0} ↓{1:F1} ↑{2:F1} KB/s]",
                        ShortNic(kv.Key), kv.Value[0] / 1024, kv.Value[1] / 1024));
                _lblNet.Text = nb.ToString();
                _lblPlanNow.Text = "电源计划: " + (string.IsNullOrEmpty(s.ActivePlanName) ? "?" : s.ActivePlanName)
                    + " | " + s.PowerLine;
                if (s.LhmActive && s.LhmCpuTempBest.HasValue)
                {
                    string t = "CPU 核心温度: " + s.LhmCpuTempBest.Value.ToString("F1") + "°C (LHM)";
                    if (s.LhmCpuPowerW.HasValue) t += " | CPU功耗 " + s.LhmCpuPowerW.Value.ToString("F1") + "W";
                    if (s.LhmFans.Count > 0) t += " | " + s.LhmFans[0];
                    _lblTemp.Text = t;
                }
                else if (s.TempNeedsAdmin) _lblTemp.Text = "温度区: 需管理员权限（系统页可提权）";
                else if (s.TempZones.Count > 0) _lblTemp.Text = "温度区: " + string.Join("; ", s.TempZones.ToArray());
                else _lblTemp.Text = "温度区: 无数据";

                if (!string.IsNullOrEmpty(s.NvidiaName))
                {
                    string nv = "独立GPU: " + s.NvidiaName
                        + " | 利用率 " + FmtN(s.NvidiaUtil) + "%"
                        + " | 显存 " + (s.NvidiaMemMB.HasValue ? s.NvidiaMemMB.Value.ToString() : "?") + "MB"
                        + " | 温度 " + FmtN(s.NvidiaTemp) + "°C";
                    if (s.NvidiaPowerW.HasValue) nv += " | 功耗 " + s.NvidiaPowerW.Value.ToString("F1") + "W";
                    _lblNvidia.Text = nv;
                }
                else _lblNvidia.Text = "独立GPU: 未检测到 nvidia-smi";

                // v3: CPU 频率
                if (s.CpuFreqMHz.HasValue)
                {
                    string freq = "CPU频率: " + s.CpuFreqMHz.Value + " MHz";
                    if (s.CpuFreqMaxMHz.HasValue) freq += " / " + s.CpuFreqMaxMHz.Value + " MHz";
                    _lblCpuFreq.Text = freq;
                }
                else _lblCpuFreq.Text = "CPU频率: --";

                // v3: 电池深度数据
                StringBuilder bd = new StringBuilder();
                bd.Append("电池: ");
                if (s.BatteryTempC.HasValue) bd.Append("温度 " + s.BatteryTempC.Value.ToString("F1") + "°C");
                if (s.BatteryVoltageV.HasValue) bd.Append(" | 电压 " + s.BatteryVoltageV.Value.ToString("F2") + "V");
                if (s.BatteryHealthPct.HasValue) bd.Append(" | 健康度 " + s.BatteryHealthPct.Value.ToString("F0") + "%");
                if (s.BatteryChargeRateMW.HasValue) bd.Append(" | 充电 " + s.BatteryChargeRateMW.Value + "mW");
                else if (s.BatteryDischargeRateMW.HasValue) bd.Append(" | 放电 " + s.BatteryDischargeRateMW.Value + "mW");
                if (s.BatteryDesignCapMWh.HasValue) bd.Append(" | 设计 " + s.BatteryDesignCapMWh.Value + "mWh");
                _lblBatDeep.Text = bd.ToString();
            }

            CheckAlerts(s);

            if (ov)
            {
                PushPoint(_cpuCurve, Clamp(s.CpuTotal));
                PushPoint(_memCurve, Clamp(s.MemUsedPct));
                // v5: 网络(合计, MB/s 刻度 0-10 → x10) + GPU 曲线
                double totKbs = 0;
                foreach (KeyValuePair<string, float[]> kv in s.NetPerNic) totKbs += (kv.Value[0] + kv.Value[1]) / 1024.0;
                PushPoint(_netCurve, Clamp((float)(totKbs / 1024.0 * 10.0)));   // 10MB/s 满刻度
                float gpuU = s.NvidiaUtil.HasValue ? s.NvidiaUtil.Value : (s.Gpu3D.HasValue ? s.Gpu3D.Value : 0f);
                PushPoint(_gpuCurve, Clamp(gpuU));
                if (_coreBars != null)
                    for (int i = 0; i < _coreBars.Length; i++)
                        if (i < s.CpuPerCore.Length)
                            _coreBars[i].Value = (int)Math.Max(0, Math.Min(100, s.CpuPerCore[i]));
                _memBar.Value = (int)Math.Max(0, Math.Min(100, s.MemUsedPct));
                _cpuCurve.Invalidate();
                _memCurve.Invalidate();
                _netCurve.Invalidate();
                _gpuCurve.Invalidate();
            }

            if (_tabs.SelectedIndex == 1)
            {
                StringBuilder bb = new StringBuilder();
                bb.AppendLine(s.BatteryPct >= 0
                    ? string.Format("电量 {0}%   |   {1}", s.BatteryPct, s.PowerLine)
                    : ("未检测到电池   |   " + s.PowerLine));
                bb.AppendLine(s.BatteryLifeSec > 0
                    ? string.Format("系统估计剩余: 约 {0} 小时 {1} 分钟", s.BatteryLifeSec / 3600, (s.BatteryLifeSec % 3600) / 60)
                    : "系统估计剩余: --");
                // v3: 电池深度数据
                if (s.BatteryTempC.HasValue) bb.AppendLine("温度: " + s.BatteryTempC.Value.ToString("F1") + "°C");
                if (s.BatteryVoltageV.HasValue) bb.AppendLine("电压: " + s.BatteryVoltageV.Value.ToString("F2") + "V");
                if (s.BatteryHealthPct.HasValue) bb.AppendLine("健康度: " + s.BatteryHealthPct.Value.ToString("F0") + "%");
                if (s.BatteryChargeRateMW.HasValue) bb.AppendLine("充电功率: " + s.BatteryChargeRateMW.Value + " mW");
                if (s.BatteryDischargeRateMW.HasValue) bb.AppendLine("放电功率: " + s.BatteryDischargeRateMW.Value + " mW");
                if (s.BatteryDesignCapMWh.HasValue) bb.AppendLine("设计容量: " + s.BatteryDesignCapMWh.Value + " mWh");
                if (s.BatteryFullCapMWh.HasValue) bb.AppendLine("实际满充: " + s.BatteryFullCapMWh.Value + " mWh");
                // v3.2: 充电阶段 + 健康趋势
                if (!string.IsNullOrEmpty(s.BatteryChargePhase) && s.BatteryChargePhase != "--")
                    bb.AppendLine("充电阶段: " + s.BatteryChargePhase + (s.BatteryChargePhase == "CC" ? " (恒流)" : " (恒压)"));
                if (s.BatteryHealthSlope != 0)
                {
                    string trend = s.BatteryHealthSlope < 0 ? "衰退" : "回升";
                    bb.AppendLine("健康趋势: " + (s.BatteryHealthSlope * 30).ToString("F2") + "%/月 (" + trend + ")");
                }
                _lblBatteryDetail.Text = bb.ToString();
                // v3: 充电曲线数据
                float batPct = s.BatteryPct >= 0 ? s.BatteryPct : 0;
                float batCurMA = 0;
                if (s.BatteryChargeRateMW.HasValue && s.BatteryVoltageV.HasValue && s.BatteryVoltageV.Value > 0)
                    batCurMA = s.BatteryChargeRateMW.Value / s.BatteryVoltageV.Value; // mW/V = mA
                else if (s.BatteryDischargeRateMW.HasValue && s.BatteryVoltageV.HasValue && s.BatteryVoltageV.Value > 0)
                    batCurMA = -(s.BatteryDischargeRateMW.Value / s.BatteryVoltageV.Value);
                _chargeCurve.PushPoint(batPct, batCurMA);
                _chargeCurve.Invalidate();
            }

            // v6: 调优页状态加载 (进页时)
            if (_tabs.SelectedIndex == 2)
                LoadTuningState();

            if (_tabs.SelectedIndex == 3 && (DateTime.Now - _lastProcRefresh).TotalMilliseconds > 2000)
                RefreshProcesses(false);

            // v3.3: 系统维护页刷新
            if (_tabs.SelectedIndex == 5 && (DateTime.Now - _lastProcRefresh).TotalMilliseconds > 5000)
                UpdateMaintenancePage();
        }

        private static float Clamp(float v) { return Math.Max(0f, Math.Min(100f, v)); }

        private static string FmtN(float? v)
        {
            return v.HasValue ? v.Value.ToString("F0") : "?";
        }

        // ---- 告警(v2) ----
        private int _alertBatPct = 20;   // v5: 可配置阈值
        private float _alertTempC = 80f;
        private void CheckAlerts(Snapshot s)
        {
            if (!_alertsEnabled || _tray == null || s == null) return;
            bool discharging = (s.PowerLine == "使用电池");
            if (AppLogic.ShouldLowBatteryAt(s.BatteryPct, discharging, _lastLowBatAlert, DateTime.Now, 10, _alertBatPct))
            {
                _lastLowBatAlert = DateTime.Now;
                string msg = "电池剩余 " + s.BatteryPct + "%，建议接通电源。";
                RecordAlert("低电量: " + msg);
                try { _tray.ShowBalloonTip(6000, "电量低提醒", msg, ToolTipIcon.Warning); } catch { }
                // v6.6: 低电量自动省电 (一次性, 接电重置): 切电池计划 + EPP DC 拉满省电
                if (_batAutoSave && !_batAutoDone && discharging)
                {
                    _batAutoDone = true;
                    string e1 = null;
                    if (!string.IsNullOrEmpty(_dcPlanGuid)) e1 = Collector.SwitchPowerPlan(_dcPlanGuid);
                    string e2 = Collector.ApplyPowerSetting(SUB_PROCESSOR, PERFEPP, 40, 95);
                    string m2 = "已自动省电: " + (e1 == null ? "切电池计划" : "切计划失败") + " + EPP DC=95";
                    RecordAlert("自动省电: " + m2);
                    try { _tray.ShowBalloonTip(5000, "低电量自动省电", m2, ToolTipIcon.Info); } catch { }
                }
            }
            if (AppLogic.ShouldHighTempAt(s.LhmCpuTempBest, _lastHighTempAlert, DateTime.Now, 5, _alertTempC))
            {
                _lastHighTempAlert = DateTime.Now;
                string msg = "CPU 温度 " + s.LhmCpuTempBest.Value.ToString("F0") + "°C，接近限流阈值。";
                RecordAlert("高温: " + msg);
                try { _tray.ShowBalloonTip(6000, "高温提醒", msg, ToolTipIcon.Warning); } catch { }
            }
        }

        private static string ShortNic(string name)
        {
            if (name.Length <= 22) return name;
            return name.Substring(0, 20) + "..";
        }

        private static void PushPoint(CurvePanel c, float v)
        {
            c.Data.Add(v);
            while (c.Data.Count > 120) c.Data.RemoveAt(0);
        }

        // ================= 电源页逻辑 =================
        private void ReloadPlans()
        {
            try
            {
                _planList.BeginUpdate();
                _planList.Items.Clear();
                foreach (PowerPlan p in _collector.ListPowerPlans())
                {
                    string tag = (p.IsActive ? "● 当前  " : "        ") + p.Name;
                    _planList.Items.Add(new PlanItem(p, tag));
                }
                _planList.EndUpdate();
            }
            catch { }
        }

        private class PlanItem
        {
            public PowerPlan Plan;
            public string Tag;
            public PlanItem(PowerPlan p, string tag) { Plan = p; Tag = tag; }
            public override string ToString() { return Tag; }
        }

        private void SwitchSelectedPlan()
        {
            PlanItem it = _planList.SelectedItem as PlanItem;
            if (it == null) { MessageBox.Show("请先在列表中选择一个电源方案。"); return; }
            string err = Collector.SwitchPowerPlan(it.Plan.Guid);
            if (err != null)
                MessageBox.Show("切换失败：" + err + "\r\n\r\n可尝试：系统页 →【以管理员身份重启】后重试。",
                    "权限不足", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            ReloadPlans();
        }

        private void GenerateBatteryReport()
        {
            try
            {
                string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string path = Path.Combine(desktop,
                    "battery-report_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".html");
                string outp = Collector.RunPowerCfg("/batteryreport /output \"" + path + "\"");
                if (File.Exists(path))
                {
                    DialogResult dr = MessageBox.Show("报告已生成:\r\n" + path + "\r\n\r\n立即打开？",
                        "完成", MessageBoxButtons.YesNo, MessageBoxIcon.Information);
                    if (dr == DialogResult.Yes) TryStart(path);
                }
                else MessageBox.Show("生成失败。\r\n" + outp, "错误", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
            catch (Exception ex) { MessageBox.Show("生成失败: " + ex.Message); }
        }

        // ================= 进程页逻辑 =================
        // v5: 进程路径/公司缓存 (WMI 批查, 60s 刷新)
        private Dictionary<int, string> _procPathCache = new Dictionary<int, string>();
        private DateTime _lastPathScan = DateTime.MinValue;
        private void EnsureProcPaths()
        {
            try
            {
                if ((DateTime.Now - _lastPathScan).TotalSeconds < 60) return;
                _lastPathScan = DateTime.Now;
                Dictionary<int, string> fresh = new Dictionary<int, string>();
                using (System.Management.ManagementObjectSearcher sr = new System.Management.ManagementObjectSearcher("SELECT ProcessId,ExecutablePath FROM Win32_Process"))
                    foreach (System.Management.ManagementObject o in sr.Get())
                    {
                        int pid;
                        if (int.TryParse((o["ProcessId"] ?? "").ToString(), out pid))
                        {
                            string ep = o["ExecutablePath"] as string;
                            if (!string.IsNullOrEmpty(ep)) fresh[pid] = ep;
                        }
                    }
                _procPathCache = fresh;
            }
            catch { }
        }

        private void RefreshProcesses(bool manual)
        {
            _lastProcRefresh = DateTime.Now;
            EnsureProcPaths();
            Snapshot snap = _last;
            string filter = (_procSearch != null && _procSearch.Text != null) ? _procSearch.Text.Trim().ToLower() : "";
            List<ListViewItem> items = new List<ListViewItem>();
            Dictionary<int, object[]> now = new Dictionary<int, object[]>();
            int cores = Math.Max(1, Environment.ProcessorCount);
            try
            {
                Process[] ps = Process.GetProcesses();
                foreach (Process p in ps)
                {
                    TimeSpan cpu;
                    try { cpu = p.TotalProcessorTime; }
                    catch { continue; }
                    DateTime t = DateTime.Now;
                    now[p.Id] = new object[] { cpu, t };
                    float cpuPct = 0f;
                    object[] prev;
                    if (_prevProcCpu.TryGetValue(p.Id, out prev))
                    {
                        TimeSpan pc = (TimeSpan)prev[0];
                        DateTime pt = (DateTime)prev[1];
                        double dt = (t - pt).TotalSeconds;
                        if (dt > 0.2) cpuPct = (float)((cpu - pc).TotalSeconds / dt / cores * 100.0);
                    }
                    long memMB = 0;
                    try { memMB = p.WorkingSet64 / (1024 * 1024); } catch { }
                    string name;
                    try { name = p.ProcessName; } catch { name = "?"; }

                    // v5: 筛选
                    if (filter.Length > 0 && name.ToLower().IndexOf(filter) < 0 && p.Id.ToString() != filter) continue;

                    // v5: 磁盘/GPU 每进程
                    float diskKbs = 0, gpuPct = 0;
                    if (snap != null)
                    {
                        float v;
                        if (snap.DiskPerProc.TryGetValue(p.Id, out v)) diskKbs = v / 1024f;
                        if (snap.GpuPerProc.TryGetValue(p.Id, out v)) gpuPct = v;
                    }
                    // v5: 路径/公司
                    string path = "";
                    _procPathCache.TryGetValue(p.Id, out path);
                    string company = "";
                    if (path.Length > 0)
                    {
                        int q = path.LastIndexOf('\\');
                        company = q >= 0 ? path.Substring(q + 1) : path;
                        if (company.Length > 34) company = ".." + company.Substring(company.Length - 34);
                    }

                    ListViewItem li = new ListViewItem(name);
                    li.SubItems.Add(p.Id.ToString());
                    li.SubItems.Add(cpuPct.ToString("F1"));
                    li.SubItems.Add(memMB.ToString());
                    li.SubItems.Add(diskKbs.ToString("F0"));
                    li.SubItems.Add(gpuPct.ToString("F0"));
                    li.SubItems.Add(company);
                    li.Tag = p.Id;
                    // v5: 颜色标记 (System Informer 风格简化版)
                    if (cpuPct >= 50f) li.BackColor = Color.FromArgb(255, 205, 205);
                    else if (memMB >= 500) li.BackColor = Color.FromArgb(255, 228, 190);
                    items.Add(li);
                }
                foreach (Process p in ps) { try { p.Dispose(); } catch { } }   // M: 防每轮刷新泄漏数百 Process 句柄
            }
            catch { }
            _prevProcCpu = now;

            items.Sort(delegate(ListViewItem a, ListViewItem b)
            {
                float fa, fb;
                float.TryParse(a.SubItems[2].Text, out fa);
                float.TryParse(b.SubItems[2].Text, out fb);
                return fb.CompareTo(fa); // CPU 降序
            });

            _procList.BeginUpdate();
            _procList.Items.Clear();
            int take = Math.Min(items.Count, 200);
            for (int i = 0; i < take; i++) _procList.Items.Add(items[i]);
            _procList.EndUpdate();
            EnsureEcoApplied();   // v6.6: 规则内新进程自动套用 EcoQoS
            // v5: 摘要
            try
            {
                if (_procSummary != null && snap != null)
                    _procSummary.Text = "进程 " + snap.SysProcCount + " | 线程 " + snap.SysThreadCount
                        + " | 句柄 " + snap.SysHandleCount + " | 显示 " + take + " 条";
            }
            catch { }
            if (manual && _procList.Items.Count == 0)
                MessageBox.Show("未获取到进程列表。");
        }

        private void KillSelected()
        {
            if (_procList.SelectedItems.Count == 0) return;
            ListViewItem li = _procList.SelectedItems[0];
            int pid = (int)li.Tag;
            DialogResult dr = MessageBox.Show(
                "确定结束进程 " + li.Text + " (PID " + pid + ") ？\r\n未保存的数据将丢失。",
                "确认", MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
            if (dr != DialogResult.Yes) return;
            try
            {
                using (Process p = Process.GetProcessById(pid))
                {
                    if (IsCriticalProc(p.ProcessName))   // M: 关键系统进程保护
                    { MessageBox.Show("关键系统进程 (" + p.ProcessName + ") 禁止结束", "保护", MessageBoxButtons.OK, MessageBoxIcon.Warning); return; }
                    p.Kill();
                    p.WaitForExit(3000);
                }
                RefreshProcesses(true);
            }
            catch (Exception ex)
            {
                MessageBox.Show("结束失败: " + ex.Message + "\r\n（系统级进程需要管理员权限）");
            }
        }

        private class ProcSorter : System.Collections.IComparer
        {
            public int Col;
            public bool NumMode;
            public int Compare(object x, object y)
            {
                ListViewItem a = x as ListViewItem, b = y as ListViewItem;
                if (a == null || b == null) return 0;
                if (NumMode)
                {
                    float fa, fb;
                    float.TryParse(a.SubItems[Col].Text, out fa);
                    float.TryParse(b.SubItems[Col].Text, out fb);
                    return fb.CompareTo(fa);
                }
                return string.Compare(a.SubItems[Col].Text, b.SubItems[Col].Text, StringComparison.Ordinal);
            }
        }

        // ================= 系统页逻辑 =================
        private void FillSystemInfo()
        {
            StringBuilder sb = new StringBuilder();
            try
            {
                sb.AppendLine("操作系统: " + Environment.OSVersion.VersionString);
                string osCaption = "", osBuild = "";
                using (var q = NewQuery("SELECT Caption, BuildNumber FROM Win32_OperatingSystem"))
                    foreach (var o in q.Get())
                    {
                        osCaption = "" + o["Caption"];
                        osBuild = "" + o["BuildNumber"];
                        break;
                    }
                if (osCaption != "") sb.AppendLine("产品名:   " + osCaption + "  (Build " + osBuild + ")");
                sb.AppendLine(".NET:     " + Environment.Version);
                sb.AppendLine("登录用户: " + Environment.UserDomainName + "\\" + Environment.UserName);
                sb.AppendLine("机器名:   " + Environment.MachineName);
                sb.AppendLine();
            }
            catch (Exception ex) { sb.AppendLine("(基础信息异常) " + ex.Message); }

            // 各段独立容错: 一段失败不影响其余
            try
            {
                using (var q = NewQuery("SELECT Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed FROM Win32_Processor"))
                    foreach (var o in q.Get())
                    {
                        sb.AppendLine("CPU:      " + o["Name"]);
                        sb.AppendLine("核心/线程: " + o["NumberOfCores"] + " / " + o["NumberOfLogicalProcessors"]
                            + "   基频: " + o["MaxClockSpeed"] + " MHz");
                        break;
                    }
            }
            catch (Exception ex) { sb.AppendLine("(CPU 信息异常) " + ex.Message); }
            sb.AppendLine("内存总量: " + NativeMem.TotalPhysMB() + " MB");
            try { sb.AppendLine("屏幕:     " + Screen.PrimaryScreen.Bounds.Width + "x" + Screen.PrimaryScreen.Bounds.Height); } catch { }
            sb.AppendLine();

            try
            {
                using (var q = NewQuery("SELECT Manufacturer, SMBIOSBIOSVersion FROM Win32_BIOS"))
                    foreach (var o in q.Get())
                    { sb.AppendLine("BIOS:     " + o["Manufacturer"] + " " + o["SMBIOSBIOSVersion"]); break; }
            }
            catch (Exception ex) { sb.AppendLine("(BIOS 信息异常) " + ex.Message); }

            try
            {
                using (var q = NewQuery("SELECT Manufacturer, Product FROM Win32_BaseBoard"))
                    foreach (var o in q.Get())
                    { sb.AppendLine("主板:     " + o["Manufacturer"] + " " + o["Product"]); break; }
            }
            catch (Exception ex) { sb.AppendLine("(主板信息异常) " + ex.Message); }

            try
            {
                sb.AppendLine();
                sb.AppendLine("磁盘分区:");
                foreach (DriveInfo d in DriveInfo.GetDrives())
                {
                    if (d.DriveType != DriveType.Fixed) continue;
                    try
                    {
                        sb.AppendLine(string.Format("  {0} {1}  剩余 {2:F1} GB / 共 {3:F1} GB",
                            d.Name, d.VolumeLabel, d.AvailableFreeSpace / 1073741824.0, d.TotalSize / 1073741824.0));
                    }
                    catch { }
                }
            }
            catch (Exception ex) { sb.AppendLine("(磁盘信息异常) " + ex.Message); }
            _txtSysInfo.Text = sb.ToString();
        }

        private static System.Management.ManagementObjectSearcher NewQuery(string q)
        {
            return new System.Management.ManagementObjectSearcher("root\\CIMV2", q);
        }

        private void RestartAsAdmin()
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = Application.ExecutablePath;
                psi.Verb = "runas";
                psi.UseShellExecute = true;
                Process.Start(psi);
                _reallyExit = true;
                Close();
            }
            catch (Exception ex)
            {
                MessageBox.Show("提权启动取消或失败: " + ex.Message);
            }
        }

        private void TryStart(string file) { TryStart(file, ""); }
        private void TryStart(string file, string args)
        {
            try
            {
                ProcessStartInfo psi = new ProcessStartInfo();
                psi.FileName = file;
                psi.Arguments = args ?? "";
                psi.UseShellExecute = true;
                Process.Start(psi);
            }
            catch (Exception ex) { MessageBox.Show("无法启动 " + file + ": " + ex.Message); }
        }

        // ================= 设置持久化 =================
        private string IniPath()
        {
            try { return Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "settings.ini"); }
            catch { return null; }
        }

        // ---- v5: 悬浮窗 (TrafficMonitor 风格: 网速/CPU/内存/今日流量, 可拖动/置顶/穿透) ----
        private class FloatWidget : Form
        {
            public Label Lbl;
            public Action OnCloseRequest;

            public FloatWidget()
            {
                FormBorderStyle = FormBorderStyle.None;
                StartPosition = FormStartPosition.Manual;
                ShowInTaskbar = false;
                TopMost = true;
                BackColor = Color.FromArgb(32, 32, 32);
                Size = new Size(150, 74);
                Location = new Point(Screen.PrimaryScreen.WorkingArea.Right - 170, 60);
                Lbl = new Label();
                Lbl.Dock = DockStyle.Fill;
                Lbl.ForeColor = Color.LimeGreen;
                Lbl.BackColor = Color.Transparent;
                Lbl.Font = new Font("Consolas", 9.5F);
                Lbl.TextAlign = ContentAlignment.MiddleLeft;
                Lbl.Padding = new Padding(8, 4, 2, 2);
                Controls.Add(Lbl);
                // 拖动
                bool drag = false; Point start = Point.Empty;
                Lbl.MouseDown += delegate(object s, MouseEventArgs e) { if (e.Button == MouseButtons.Left) { drag = true; start = e.Location; } };
                Lbl.MouseMove += delegate(object s, MouseEventArgs e)
                { if (drag) { Location = new Point(Location.X + e.X - start.X, Location.Y + e.Y - start.Y); } };
                Lbl.MouseUp += delegate(object s, MouseEventArgs e) { drag = false; };
                // 双击关闭
                Lbl.DoubleClick += delegate { if (OnCloseRequest != null) OnCloseRequest(); };
            }

            protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
            {
                if (keyData == Keys.Escape) { if (OnCloseRequest != null) OnCloseRequest(); return true; }
                return base.ProcessCmdKey(ref msg, keyData);
            }

            protected override CreateParams CreateParams
            {
                get
                {
                    CreateParams cp = base.CreateParams;
                    cp.ExStyle |= 0x80;                     // WS_EX_TOOLWINDOW 不进 Alt-Tab
                    return cp;
                }
            }

            protected override void OnPaintBackground(PaintEventArgs e)
            {
                base.OnPaintBackground(e);
                using (Pen p = new Pen(Color.FromArgb(70, 130, 60)))
                    e.Graphics.DrawRectangle(p, 0, 0, ClientSize.Width - 1, ClientSize.Height - 1);
            }
        }

        private void ToggleWidget()
        {
            if (_widget == null || _widget.IsDisposed)
            {
                _widget = new FloatWidget();
                _widget.OnCloseRequest = delegate { ToggleWidget(); };
                _widget.Show();
                _widgetOn = true;
            }
            else if (_widget.Visible)
            {
                _widget.Hide();
                _widgetOn = false;
            }
            else
            {
                _widget.Show();
                _widgetOn = true;
            }
            try { SaveSettings(); } catch { }
        }

        private void UpdateWidget(Snapshot s)
        {
            if (_widget == null || !_widget.Visible || s == null) return;
            try
            {
                double totalKbs = 0;
                foreach (KeyValuePair<string, float[]> kv in s.NetPerNic)
                    totalKbs += (kv.Value[0] + kv.Value[1]) / 1024.0;
                string net = totalKbs >= 1024 ? (totalKbs / 1024).ToString("F2") + " MB/s" : totalKbs.ToString("F0") + " KB/s";
                _widget.Lbl.Text =
                    "CPU " + s.CpuTotal.ToString("F0") + "%  内存 " + s.MemUsedPct.ToString("F0") + "%\r\n" +
                    "网速 " + net + "\r\n" +
                    (s.LhmCpuTempBest.HasValue ? "温度 " + s.LhmCpuTempBest.Value.ToString("F0") + "°C  " : "") +
                    "今日 " + (s.TodayRxMB / 1024.0).ToString("F2") + " GB";
            }
            catch { }
        }

        // ---- v5: 托盘数字图标 (任务管理器风格: 图标上实时绘制 CPU%) ----
        private void UpdateTrayIconLive(Snapshot s)
        {
            try
            {
                if ((DateTime.Now - _lastIconDraw).TotalMilliseconds < 900) return;
                _lastIconDraw = DateTime.Now;
                using (Bitmap bmp = new Bitmap(16, 16))
                using (Graphics g = Graphics.FromImage(bmp))
                {
                    g.Clear(Color.FromArgb(40, 40, 46));
                    using (SolidBrush bar = new SolidBrush(Color.LimeGreen))
                        g.FillRectangle(bar, 0, 13, (int)Math.Max(1, 16 * s.CpuTotal / 100f), 3); // 底部进度条
                    using (Font f = new Font("Arial", 8F, FontStyle.Bold))
                    using (SolidBrush tb = new SolidBrush(Color.White))
                    {
                        string txt = s.CpuTotal >= 100 ? "99" : ((int)s.CpuTotal).ToString();
                        SizeF sz = g.MeasureString(txt, f);
                        g.DrawString(txt, f, tb, (16 - sz.Width) / 2f, 0);
                    }
                    IntPtr hIcon = bmp.GetHicon();
                    Icon newIcon = Icon.FromHandle(hIcon);
                    Icon old = _trayIconLive;
                    _tray.Icon = newIcon;
                    _trayIconLive = newIcon;
                    // M修复: FromHandle 的句柄归本方法所有 — 新图标就位后再销毁"旧"句柄
                    // (原实现立即 DestroyIcon 正在使用的句柄 → 托盘悬空图标; old.Dispose 还会二次销毁)
                    if (old != null) { try { DestroyIcon(old.Handle); } catch { } }
                }
            }
            catch { }
        }

        [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Auto)]
        private static extern bool DestroyIcon(IntPtr hIcon);

        private void SaveSettings()
        {
            try
            {
                string ini = IniPath();
                if (ini == null) return;
                StringBuilder sb = new StringBuilder();
                // C4修复: merge 写 — 保留本方法不管理的键 (mod0..mod4 布局键等), 防全量重写丢失
                if (File.Exists(ini))
                {
                    string[] known = new string[] { "x", "y", "w", "h", "tab", "alerts", "interval", "autoswitch",
                        "acplan", "dcplan", "widget", "topmost", "alertbat", "alerttemp", "linkacer", "ecoqos", "batt60hz", "batautosave" };
                    foreach (KeyValuePair<string, string> kv in AppLogic.ParseIni(ini))
                        if (Array.IndexOf(known, kv.Key) < 0) sb.AppendLine(kv.Key + "=" + kv.Value);
                }
                sb.AppendLine("x=" + Location.X);
                sb.AppendLine("y=" + Location.Y);
                sb.AppendLine("w=" + Size.Width);
                sb.AppendLine("h=" + Size.Height);
                sb.AppendLine("tab=" + _tabs.SelectedIndex);
                sb.AppendLine("alerts=" + (_alertsEnabled ? "1" : "0"));
                sb.AppendLine("interval=" + _baseIntervalMs);
                // v4.1: AC/DC 自动切换
                sb.AppendLine("autoswitch=" + (_autoSwitch ? "1" : "0"));
                sb.AppendLine("acplan=" + _acPlanGuid);
                sb.AppendLine("dcplan=" + _dcPlanGuid);
                // v5: 悬浮窗/置顶
                sb.AppendLine("widget=" + (_widgetOn ? "1" : "0"));
                sb.AppendLine("topmost=" + (TopMost ? "1" : "0"));
                // v5: 告警阈值
                sb.AppendLine("alertbat=" + _alertBatPct);
                sb.AppendLine("alerttemp=" + ((int)_alertTempC));
                // v6.2: Acer 联动
                sb.AppendLine("linkacer=" + (_linkAcerProfile ? "1" : "0"));
                // v6.6: EcoQoS 持久规则 (进程名 ; 分隔)
                sb.AppendLine("ecoqos=" + string.Join(";", new List<string>(_ecoqosNames).ToArray()));
                // v6.6: 刷新率跟随 + 低电量自动省电
                sb.AppendLine("batt60hz=" + (_batt60hz ? "1" : "0"));
                sb.AppendLine("batautosave=" + (_batAutoSave ? "1" : "0"));
                File.WriteAllText(ini, sb.ToString());
            }
            catch { }
        }

        private void LoadSettings()
        {
            try
            {
                string ini = IniPath();
                if (ini == null || !File.Exists(ini)) return;
                Dictionary<string, string> cfg = AppLogic.ParseIni(ini);
                int v;
                string sv;
                int x = 0, y = 0, w = 0, h = 0, tab = 0;
                if (cfg.TryGetValue("x", out sv) && int.TryParse(sv, out v)) x = v;
                if (cfg.TryGetValue("y", out sv) && int.TryParse(sv, out v)) y = v;
                if (cfg.TryGetValue("w", out sv) && int.TryParse(sv, out v)) w = v;
                if (cfg.TryGetValue("h", out sv) && int.TryParse(sv, out v)) h = v;
                if (cfg.TryGetValue("tab", out sv) && int.TryParse(sv, out v)) tab = v;
                if (cfg.TryGetValue("alerts", out sv)) _alertsEnabled = (sv == "1");
                if (cfg.TryGetValue("interval", out sv))
                {
                    if (sv == "2000") _baseIntervalMs = 2000;
                    else if (sv == "5000") _baseIntervalMs = 5000;
                    else if (sv == "1000") _baseIntervalMs = 1000;
                }
                // v4.1: AC/DC 自动切换
                if (cfg.TryGetValue("autoswitch", out sv)) _autoSwitch = (sv == "1");
                if (cfg.TryGetValue("acplan", out sv)) _acPlanGuid = sv;
                if (cfg.TryGetValue("dcplan", out sv)) _dcPlanGuid = sv;
                // v5: 悬浮窗/置顶
                if (cfg.TryGetValue("topmost", out sv)) TopMost = (sv == "1");
                if (cfg.TryGetValue("widget", out sv) && sv == "1") { ToggleWidget(); }
                // v5: 告警阈值
                int ab;
                if (cfg.TryGetValue("alertbat", out sv) && int.TryParse(sv, out ab)
                    && ab >= 5 && ab <= 50) _alertBatPct = ab;
                int at;
                if (cfg.TryGetValue("alerttemp", out sv) && int.TryParse(sv, out at)
                    && at >= 60 && at <= 100) _alertTempC = at;
                // v6.2: Acer 联动
                if (cfg.TryGetValue("linkacer", out sv)) _linkAcerProfile = (sv == "1");
                // v6.6: EcoQoS 持久规则
                if (cfg.TryGetValue("ecoqos", out sv) && sv.Length > 0)
                {
                    foreach (string nm in sv.Split(';'))
                    {
                        string b = EcoBaseName(nm);
                        if (b.Length > 0) _ecoqosNames.Add(b);
                    }
                }
                // v6.6: 刷新率跟随 + 低电量自动省电
                if (cfg.TryGetValue("batt60hz", out sv)) _batt60hz = (sv == "1");
                if (cfg.TryGetValue("batautosave", out sv)) _batAutoSave = (sv == "1");
                if (w >= MinimumSize.Width && h >= MinimumSize.Height) Size = new Size(w, h);
                if (x > -100 && y > -100 && x < Screen.PrimaryScreen.Bounds.Width
                    && y < Screen.PrimaryScreen.Bounds.Height) Location = new Point(x, y);
                if (tab >= 0 && tab < _tabs.TabPages.Count) _tabs.SelectedIndex = tab;
            }
            catch { }
        }

        // ---- 自绘曲线控件 ----
        private class CurvePanel : Panel
        {
            public List<float> Data = new List<float>();
            private Color _line;
            public CurvePanel(Color line)
            {
                _line = line;
                DoubleBuffered = true;
                ResizeRedraw = true;
                BackColor = Color.WhiteSmoke;
            }
            protected override void OnPaint(PaintEventArgs e)
            {
                base.OnPaint(e);
                Graphics g = e.Graphics;
                int w = ClientSize.Width, h = ClientSize.Height;
                if (w < 10 || h < 10) return;
                using (Pen grid = new Pen(Color.Gainsboro))
                {
                    for (int i = 1; i < 4; i++)
                        g.DrawLine(grid, 0, h * i / 4, w, h * i / 4);
                    for (int i = 1; i < 6; i++)
                        g.DrawLine(grid, w * i / 6, 0, w * i / 6, h);
                }
                if (Data.Count < 2) return;
                List<PointF> pts = new List<PointF>();
                lock (Data)
                {
                    for (int i = 0; i < Data.Count; i++)
                    {
                        float fx = (float)i / (Data.Count - 1) * (w - 2) + 1;
                        float fy = h - 1 - (Data[i] / 100f) * (h - 2);
                        pts.Add(new PointF(fx, fy));
                    }
                }
                using (Pen pen = new Pen(_line, 1.6f))
                    g.DrawLines(pen, pts.ToArray());
                // 最新值标注
                if (pts.Count > 0)
                {
                    PointF lastPt = pts[pts.Count - 1];
                    string txt = ((int)Data[Data.Count - 1]).ToString() + "%";
                    g.DrawString(txt, Font, Brushes.Gray, Math.Min(lastPt.X + 4, w - 30), Math.Max(0, lastPt.Y - 14));
                }
            }
        }

        // v3: 双轴曲线控件 (充电曲线: 容量% + 电流mA)
        private class DualAxisCurvePanel : Panel
        {
            public List<float> DataLeft = new List<float>();   // 左轴: 容量% (0-100)
            public List<float> DataRight = new List<float>();  // 右轴: 电流mA (0-2000)
            public string LeftLabel = "容量%";
            public string RightLabel = "电流mA";
            public Color LeftColor = Color.FromArgb(48, 140, 198);
            public Color RightColor = Color.FromArgb(200, 80, 80);
            public int MaxPoints = 120;

            public DualAxisCurvePanel()
            {
                DoubleBuffered = true;
                ResizeRedraw = true;
                BackColor = Color.WhiteSmoke;
            }

            public void PushPoint(float left, float right)
            {
                lock (DataLeft) { DataLeft.Add(left); if (DataLeft.Count > MaxPoints) DataLeft.RemoveAt(0); }
                lock (DataRight) { DataRight.Add(right); if (DataRight.Count > MaxPoints) DataRight.RemoveAt(0); }
            }

            protected override void OnPaint(PaintEventArgs e)
            {
                base.OnPaint(e);
                Graphics g = e.Graphics;
                int w = ClientSize.Width, h = ClientSize.Height;
                if (w < 40 || h < 20) return;
                int left = 35, right = w - 5, top = 4, bot = h - 14;
                int pw = right - left, ph = bot - top;

                // 网格
                using (Pen grid = new Pen(Color.Gainsboro))
                {
                    for (int i = 1; i < 4; i++) g.DrawLine(grid, left, top + ph * i / 4, right, top + ph * i / 4);
                    for (int i = 1; i < 6; i++) g.DrawLine(grid, left + pw * i / 6, top, left + pw * i / 6, bot);
                }

                // 左轴刻度 (0-100%)
                using (Font f = new Font("Consolas", 7f))
                {
                    for (int i = 0; i <= 4; i++)
                    {
                        int y = bot - ph * i / 4;
                        g.DrawString((i * 25).ToString(), f, Brushes.Gray, 0, y - 5);
                    }
                    // 右轴刻度 (0-2000mA)
                    for (int i = 0; i <= 4; i++)
                    {
                        int y = bot - ph * i / 4;
                        g.DrawString((i * 500).ToString(), f, Brushes.Gray, right - 2, y - 5);
                    }
                    // 标签
                    g.DrawString(LeftLabel, f, Brushes.Gray, left, top - 2);
                    g.DrawString(RightLabel, f, Brushes.Gray, right - 50, top - 2);
                }

                // 左轴曲线 (容量%)
                DrawCurve(g, DataLeft, left, top, pw, ph, LeftColor, 0f, 100f);
                // 右轴曲线 (电流mA)
                DrawCurve(g, DataRight, left, top, pw, ph, RightColor, 0f, 2000f);
            }

            private void DrawCurve(Graphics g, List<float> data, int left, int top, int pw, int ph, Color color, float minVal, float maxVal)
            {
                if (data.Count < 2) return;
                List<PointF> pts = new List<PointF>();
                lock (data)
                {
                    for (int i = 0; i < data.Count; i++)
                    {
                        float fx = left + (float)i / (data.Count - 1) * pw;
                        float norm = (data[i] - minVal) / (maxVal - minVal);
                        float fy = top + ph - norm * ph;
                        pts.Add(new PointF(fx, Math.Max(top, Math.Min(top + ph, fy))));
                    }
                }
                using (Pen pen = new Pen(color, 1.6f))
                    g.DrawLines(pen, pts.ToArray());
                // 最新值标注
                if (pts.Count > 0)
                {
                    PointF lastPt = pts[pts.Count - 1];
                    string txt = data[data.Count - 1].ToString("F0");
                    g.DrawString(txt, new Font("Consolas", 8f), new SolidBrush(color), Math.Min(lastPt.X + 3, left + pw - 25), Math.Max(top, lastPt.Y - 12));
                }
            }
        }
    }

    // 内存总量 P/Invoke 独立类(供系统页复用)
    internal static class NativeMem
    {
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

        public static long TotalPhysMB()
        {
            try
            {
                MEMORYSTATUSEX m = new MEMORYSTATUSEX();
                if (GlobalMemoryStatusEx(m)) return (long)(m.ullTotalPhys / (1024 * 1024));
            }
            catch { }
            return 0;
        }
    }
}
