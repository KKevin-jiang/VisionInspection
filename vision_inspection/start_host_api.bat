@echo off
REM 上位机 HTTP API 服务 — 后台启动脚本（无控制台窗口）
REM 用于 Windows 任务计划程序或 NSSM 服务管理器调用

cd /d "D:\HostAPI"

REM 优先使用 pythonw.exe（无控制台窗口），找不到则用 python.exe
set PYTHON=pythonw
if not exist "C:\Program Files\Python311\pythonw.exe" set PYTHON=python
if exist "D:\Python311\pythonw.exe" set PYTHON=D:\Python311\pythonw.exe

start "" /B %PYTHON% host_api_server.py
