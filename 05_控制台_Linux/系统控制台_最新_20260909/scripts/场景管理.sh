#!/bin/bash
# 场景管理器 — 按场景一键配置电源管理
# 用法: ./场景管理.sh <场景名>
# 场景: ac-perf ac-bal ac-quiet bat-save bat-bal bat-perf status bench
# 修正: BAT/AC自动检测(ACAD/BAT1), 温度第4列, C-State按真实名称(无C5), PL1钳制警告

BENCH="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)/bench"  # readlink: 经 sc-* 别名调用时解析真实位置
RAPL="/sys/class/powercap/intel-rapl:0"
PL1_MAX=$(cat $RAPL/constraint_0_max_power_uw 2>/dev/null)
PL2_MAX=$(cat $RAPL/constraint_1_max_power_uw 2>/dev/null)

detect_ac() {
    for d in /sys/class/power_supply/*; do
        [ "$(cat "$d/type" 2>/dev/null)" = "Mains" ] && [ "$(cat "$d/online" 2>/dev/null)" = "1" ] && { echo 1; return; }
    done
    echo 0
}

detect_bat() {
    for d in /sys/class/power_supply/BAT*; do
        [ -d "$d" ] && { echo "$d"; return; }
    done
}

detect_wlan() {
    iw dev 2>/dev/null | awk '/Interface/{print $2; exit}'
}

get_temp() {
    sensors 2>/dev/null | awk '/^Package/{print $4}' | tr -d '+°C' | head -1
}

show_status() {
    local GOV EPP PL1 PL2 TURBO TEMP BAT AC
    echo "=== 当前电源状态 ==="
    GOV=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null)
    EPP=$(cat /sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference 2>/dev/null)
    PL1=$(cat $RAPL/constraint_0_power_limit_uw 2>/dev/null)
    PL2=$(cat $RAPL/constraint_1_power_limit_uw 2>/dev/null)
    TURBO=$(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null)
    TEMP=$(get_temp)
    BAT=$(detect_bat)
    AC=$(detect_ac)

    echo "电源: $([ "$AC" = "1" ] && echo 'AC插电' || echo '电池供电')"
    echo "电池: $([ -n "$BAT" ] && cat "$BAT/capacity" 2>/dev/null || echo '未检测到')%"
    echo "温度: ${TEMP:-N/A}°C"
    echo "Governor: $GOV"
    echo "EPP: $EPP"
    echo "PL1: $((${PL1:-15000000}/1000000))W (本机上限: $((${PL1_MAX:-0}/1000000))W)"
    echo "PL2: $((${PL2:-25000000}/1000000))W"
    echo "Turbo: $([ "$TURBO" = "0" ] && echo 'ON' || echo 'OFF')"
    echo ""
    echo "=== 推荐场景 ==="
    if [ "$AC" = "1" ]; then
        echo "ac-perf  → 编译/渲染/跑分(最大性能)"
        echo "ac-bal   → 日常办公/开发(平衡)"
        echo "ac-quiet → 夜间/安静环境(静音)"
    else
        echo "bat-save → 外出/无电源(最大续航)"
        echo "bat-bal  → 离电日常(平衡)"
        echo "bat-perf → 离电急需性能(受限)"
    fi
}

# 限制CPU C-State深度: 传入最深的允许状态名(POLL/C1/C1E/C3/C6/C7s/C8/C9/C10)
# C0 表示不限制(恢复全部状态)
set_cstate() {
    local maxrank
    case "$1" in
        C0)  maxrank=99 ;;
        C1)  maxrank=1 ;;
        C1E) maxrank=2 ;;
        C3)  maxrank=3 ;;
        C6)  maxrank=4 ;;
        C7s) maxrank=5 ;;
        C8)  maxrank=6 ;;
        C9)  maxrank=7 ;;
        C10) maxrank=8 ;;
        *) echo "未知C-State: $1"; return 1 ;;
    esac
    # 2026-08-20 优化: 一次 sudo 批量写入, 避免每 state 一条 sudo 日志
    sudo bash -c '
        for st in /sys/devices/system/cpu/cpu[0-9]*/cpuidle/state*; do
            [ -d "$st" ] || continue
            name=$(cat "$st/name" 2>/dev/null)
            case "$name" in
                POLL) rank=0 ;; C1) rank=1 ;; C1E) rank=2 ;; C3) rank=3 ;;
                C6) rank=4 ;; C7s) rank=5 ;; C8) rank=6 ;; C9) rank=7 ;; C10) rank=8 ;;
                *) continue ;;
            esac
            if [ "$rank" -gt '"$maxrank"' ]; then
                echo 1 > "$st/disable"
            else
                echo 0 > "$st/disable"
            fi
        done
    ' 2>/dev/null
}

set_rapl() {
    local pl1=$1 pl2=$2
    if [ -n "$PL1_MAX" ] && [ "$pl1" -gt "$PL1_MAX" ]; then
        echo "⚠️ 警告: PL1目标$((pl1/1000000))W超过本机固件上限$((PL1_MAX/1000000))W,写入将被内核钳制!"
    fi
    echo "$pl1" | sudo tee $RAPL/constraint_0_power_limit_uw > /dev/null 2>&1
    echo "$pl2" | sudo tee $RAPL/constraint_1_power_limit_uw > /dev/null 2>&1
}

set_turbo() {
    echo $1 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo > /dev/null 2>&1
}

set_wifi_pm() {
    local wlan=$(detect_wlan)
    [ -n "$wlan" ] && sudo iw dev "$wlan" set power_save $1 2>/dev/null
}

set_usb_as() {
    local v=$1
    # 2026-08-20 优化: 一次 sudo 批量写入, 避免每设备一条 sudo 日志(单次场景切换 40+ 条 -> 1 条)
    sudo bash -c "for usb in /sys/bus/usb/devices/*/power/autosuspend; do echo '$v' > \"\$usb\" 2>/dev/null; done"
}

apply_scene() {
    local scene=$1
    echo "=== 应用场景: $scene ==="

    case "$scene" in
        ac-perf)
            systemctl is-active power-profiles-daemon >/dev/null 2>&1 && powerprofilesctl set performance
            echo "插电高性能模式"
            echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor > /dev/null
            echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference > /dev/null
            set_rapl 25000000 25000000
            set_turbo 0
            set_cstate C1E
            systemctl is-active thermald >/dev/null 2>&1 && sudo systemctl stop thermald
            set_wifi_pm off
            set_usb_as -1
            echo "✓ 已切换到插电高性能模式 (PL1=25W, Governor=performance)"
            echo "   ℹ PL1固件上限15W,若实际表现不达预期可尝试30W/更高(实测写入25W成功)"
            ;;

        ac-bal)
            systemctl is-active power-profiles-daemon >/dev/null 2>&1 && powerprofilesctl set balanced
            echo "插电平衡模式"
            echo powersave | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor > /dev/null
            echo balance_performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference > /dev/null
            set_rapl 15000000 25000000
            set_turbo 0
            set_cstate C3
            systemctl is-active thermal-guard >/dev/null 2>&1 || sudo systemctl start thermald 2>/dev/null || true
            set_wifi_pm off
            set_usb_as 2
            echo "✓ 已切换到插电平衡模式 (PL1=15W, EPP=balance_performance)"
            ;;

        ac-quiet)
            systemctl is-active power-profiles-daemon >/dev/null 2>&1 && powerprofilesctl set balanced
            echo "插电静音模式"
            echo powersave | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor > /dev/null
            echo balance_power | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference > /dev/null
            set_rapl 10000000 15000000
            set_turbo 0
            set_cstate C6
            systemctl is-active thermal-guard >/dev/null 2>&1 || sudo systemctl start thermald 2>/dev/null || true
            set_wifi_pm on
            set_usb_as 2
            echo "✓ 已切换到插电静音模式 (PL1=10W, EPP=balance_power)"
            ;;

        bat-save)
            systemctl is-active power-profiles-daemon >/dev/null 2>&1 && powerprofilesctl set power-saver
            echo "离电省电模式"
            echo powersave | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor > /dev/null
            echo power | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference > /dev/null
            set_rapl 10000000 12000000
            set_turbo 1
            set_cstate C0
            set_wifi_pm on
            set_usb_as auto
            sudo powertop --auto-tune 2>/dev/null
            echo "✓ 已切换到离电省电模式 (Turbo OFF, EPP=power)"
            ;;

        bat-bal)
            systemctl is-active power-profiles-daemon >/dev/null 2>&1 && powerprofilesctl set power-saver
            echo "离电均衡模式"
            echo powersave | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor > /dev/null
            echo balance_power | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference > /dev/null
            set_rapl 12000000 18000000
            set_turbo 0
            set_cstate C7s
            set_wifi_pm on
            set_usb_as 2
            echo "✓ 已切换到离电均衡模式 (PL1=12W, EPP=balance_power)"
            ;;

        bat-perf)
            systemctl is-active power-profiles-daemon >/dev/null 2>&1 && powerprofilesctl set balanced
            echo "离电性能模式(⚠️受固件限制,实际PL1≈8W/1.6GHz)"
            echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor > /dev/null
            echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference > /dev/null
            set_rapl 15000000 25000000
            set_turbo 0
            set_cstate C1E
            set_wifi_pm off
            set_usb_as -1
            echo "✓ 已切换到离电性能模式 (⚠️ 实际受EC固件限制~8W)"
            ;;

        bench)
            echo "=== 运行性能测试 ==="
            if [ ! -f "$BENCH" ]; then
                echo "错误: 测试程序不存在: $BENCH"
                exit 1
            fi
            echo "测试条件: 8线程 LCG 20秒满载"
            T0=$(date +%H:%M:%S.%3N)
            RES=$("$BENCH")  # 引号: 项目路径含空格, 裸 $BENCH 会被拆词(2026-09-11 修复)
            T1=$(date +%H:%M:%S.%3N)
            ITERS=$(echo "$RES" | awk '/^total=/{sub("total=","");print}')
            KPS=$(awk "BEGIN{printf \"%.1f\", $ITERS/20/10000}")
            echo "迭代次数: $ITERS"
            echo "吞吐量: ${KPS}万/s"
            echo "耗时: $T0 → $T1"
            ;;

        *)
            echo "未知场景: $scene"
            exit 1
            ;;
    esac
}

case "$1" in
    status|"")
        show_status
        ;;
    ac-perf|ac-bal|ac-quiet|bat-save|bat-bal|bat-perf|bench)
        apply_scene "$1"
        show_status
        ;;
    *)
        echo "用法: $0 {status|ac-perf|ac-bal|ac-quiet|bat-save|bat-bal|bat-perf|bench}"
        echo ""
        echo "场景说明:"
        echo "  ac-perf   插电高性能 (编译/渲染/跑分)"
        echo "  ac-bal    插电平衡   (日常办公/开发)"
        echo "  ac-quiet  插电静音   (夜间/安静环境)"
        echo "  bat-save  离电省电   (最大续航)"
        echo "  bat-bal   离电均衡   (离电日常)"
        echo "  bat-perf  离电性能   (受限于固件墙)"
        echo "  bench     运行性能测试"
        echo "  status    显示当前状态"
        ;;
esac