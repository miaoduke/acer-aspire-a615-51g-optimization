@echo off
rem build.cmd - compile with built-in csc (.NET Framework 4.8), zero external deps
setlocal
set CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe
if not exist "%CSC%" set CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe
if not exist "%CSC%" (
  echo [ERROR] csc.exe not found
  exit /b 1
)

set REFS=/r:System.dll /r:System.Core.dll /r:System.Management.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll /r:System.ServiceProcess.dll
set PLATFORM=/platform:x86

echo [1/2] building release (winexe)...
"%CSC%" /nologo /target:winexe /optimize+ %PLATFORM% /codepage:65001 %REFS% /out:".\SysConsole.exe" Program.cs Collector.cs MainForm.cs LoadAdvisor.cs
if errorlevel 1 goto :fail

echo [2/2] building debug console (for --selftest)...
"%CSC%" /nologo /target:exe /optimize+ %PLATFORM% /codepage:65001 %REFS% /out:".\SysConsoleDebug.exe" Program.cs Collector.cs MainForm.cs LoadAdvisor.cs
if errorlevel 1 goto :fail

echo.
echo Done:
dir /b *.exe
exit /b 0

:fail
echo [FAILED]
exit /b 1