#!/bin/bash
# start.sh — 启动系统控制台 GUI（相对路径，换机/重装后复制整个文件夹即可运行）
# 用法: ./start.sh  或  桌面双击「系统控制台.desktop」
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR" || exit 1
exec python3 console.py