@echo off
setlocal

chcp 65001 >nul

cd /d "%~dp0"

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
set "APP_ENTRY=%~dp0vision_inspection\app\main.py"
set "PYQT5_DIR=%~dp0.venv\Lib\site-packages\PyQt5"
set "QT_PLUGIN_DIR=%PYQT5_DIR%\Qt5\plugins"
set "QT_PLATFORM_PLUGIN_DIR=%QT_PLUGIN_DIR%\platforms"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] 未找到虚拟环境 Python：
    echo %PYTHON_EXE%
    echo.
    echo 请先创建虚拟环境并安装依赖后再启动。
    pause
    exit /b 1
)

if not exist "%APP_ENTRY%" (
    echo [ERROR] 未找到程序入口文件：
    echo %APP_ENTRY%
    pause
    exit /b 1
)

if not exist "%QT_PLATFORM_PLUGIN_DIR%\qwindows.dll" (
    echo [ERROR] 未找到 Qt 平台插件：
    echo %QT_PLATFORM_PLUGIN_DIR%\qwindows.dll
    echo.
    echo 请检查 PyQt5 是否已正确安装到虚拟环境。
    pause
    exit /b 1
)

set "QT_PLUGIN_PATH=%QT_PLUGIN_DIR%"
set "QT_QPA_PLATFORM_PLUGIN_PATH=%QT_PLATFORM_PLUGIN_DIR%"

echo [INFO] 正在启动视觉检测软件...
echo [INFO] Python: %PYTHON_EXE%
echo [INFO] Entry : %APP_ENTRY%
echo [INFO] QtPlugins: %QT_PLATFORM_PLUGIN_DIR%
echo.

"%PYTHON_EXE%" "%APP_ENTRY%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] 程序异常退出，退出码：%EXIT_CODE%
    pause
)

exit /b %EXIT_CODE%