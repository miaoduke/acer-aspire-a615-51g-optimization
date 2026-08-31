@echo off
rem 双击此文件 -> UAC 点"是" -> 以管理员运行采集自检(LHM 完整传感器测试)
rem 结果写入同目录 selftest_result.txt
powershell -NoProfile -Command "Start-Process -FilePath ('%~dp0SysConsoleDebug.exe') -ArgumentList '--selftest' -Verb RunAs"
echo 已发起管理员自检，几秒后可查看 selftest_result.txt
