using System;
using System.Collections.Generic;
using SysConsole;

// TestRefresh.cs — Collector 刷新率 API 功能自检 (60Hz 往返, 2 秒后恢复)
static class TestRefresh
{
    static int Main()
    {
        int? cur = Collector.GetRefreshRate();
        Console.WriteLine("当前刷新率: " + (cur.HasValue ? cur.Value.ToString() : "读取失败"));
        if (!cur.HasValue) return 1;

        List<int> rates = Collector.EnumRefreshRates();
        Console.WriteLine("可用档位: " + string.Join(", ", rates.ToArray()) + (rates.Count == 0 ? " (枚举失败)" : ""));
        if (rates.Count == 0) return 2;

        if (cur.Value > 60)
        {
            string e1 = Collector.SetRefreshRate(60);
            int? now = Collector.GetRefreshRate();
            Console.WriteLine("降 60Hz: " + (e1 == null ? "OK" : "失败 " + e1) + " | 读回: " + (now.HasValue ? now.Value.ToString() : "?"));
            System.Threading.Thread.Sleep(1500);
            string e2 = Collector.SetRefreshRate(cur.Value);
            int? back = Collector.GetRefreshRate();
            Console.WriteLine("恢复 " + cur.Value + "Hz: " + (e2 == null ? "OK" : "失败 " + e2) + " | 读回: " + (back.HasValue ? back.Value.ToString() : "?"));
            return (e1 == null && e2 == null && back == cur.Value) ? 0 : 3;
        }
        else
        {
            int best = rates[rates.Count - 1];
            Console.WriteLine("当前<=60Hz, 跳过降档测试 (最高档 " + best + ")");
            return 0;
        }
    }
}
