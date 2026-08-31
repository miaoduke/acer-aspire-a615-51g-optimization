// LoadAdvisor.cs — 负载自适应建议器 (移植自 Linux load_advisor.py)
// 逻辑: 持续高负载 + 电池供电 → 建议切换到性能计划(仅建议, 不自动切, 避免抢控制权)
// 纯逻辑类, 便于自检测试
using System;
using System.Collections.Generic;

namespace SysConsole
{
    public class LoadAdvisor
    {
        private readonly double _highThreshold;   // 高负载阈值 %
        private readonly int _sustainSamples;     // 持续样本数
        private readonly int _cooldownSec;        // 建议冷却秒
        private readonly Queue<float> _history = new Queue<float>();
        private DateTime _lastAdvice = DateTime.MinValue;

        public LoadAdvisor(double highThresholdPct, int sustainSec, int sampleIntervalSec, int cooldownMin)
        {
            _highThreshold = highThresholdPct;
            _sustainSamples = Math.Max(1, sustainSec / Math.Max(1, sampleIntervalSec));
            _cooldownSec = cooldownMin * 60;
        }

        /// 每次采样调用. 返回建议消息(触发时), 否则 null. 触发后自动清空历史+进入冷却.
        public string Feed(float cpuPct, bool onBattery, DateTime now)
        {
            _history.Enqueue(cpuPct);
            while (_history.Count > _sustainSamples) _history.Dequeue();
            if (_history.Count < _sustainSamples) return null;
            if (!onBattery) return null;
            double sinceAdvice = (now - _lastAdvice).TotalSeconds;
            if (sinceAdvice >= 0 && sinceAdvice < _cooldownSec) return null;   // M: 时钟回拨(now<last)视为冷却已过, 不再锁死

            double sum = 0; bool allHigh = true;
            foreach (float v in _history)
            {
                sum += v;
                if (v < _highThreshold * 0.8) allHigh = false;
            }
            double avg = sum / _history.Count;
            if (avg >= _highThreshold && allHigh)
            {
                _lastAdvice = now;
                _history.Clear();
                return string.Format("检测到持续高负载（平均 {0:F0}%），电池供电下可能受限。建议切换到高性能电源计划。", avg);
            }
            return null;
        }

        public void Reset() { _history.Clear(); _lastAdvice = DateTime.MinValue; }
    }
}
