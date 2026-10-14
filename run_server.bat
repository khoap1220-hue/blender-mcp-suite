@echo off
setlocal EnableDelayedExpansion

title Blender MCP Server
echo ===============================================================================
echo                Production-Grade Blender Model Context Protocol (MCP) Server
echo ===============================================================================

rem Set repository paths
set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"
set "SRC_DIR=%REPO_ROOT%\src"

rem Set PYTHONPATH to include both repository root and src directory
if defined PYTHONPATH (
    set "PYTHONPATH=%SRC_DIR%;%REPO_ROOT%;!PYTHONPATH!"
) else (
    set "PYTHONPATH=%SRC_DIR%;%REPO_ROOT%"
)

rem Locate Python Interpreter (Check virtual envs first, then PATH, then py launcher)
set "PYTHON_BIN="

if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON_BIN=%REPO_ROOT%\.venv\Scripts\python.exe"
    echo [INFO] Using virtual environment: %REPO_ROOT%\.venv
) else if exist "%REPO_ROOT%\venv\Scripts\python.exe" (
    set "PYTHON_BIN=%REPO_ROOT%\venv\Scripts\python.exe"
    echo [INFO] Using virtual environment: %REPO_ROOT%\venv
) else if exist "%REPO_ROOT%\env\Scripts\python.exe" (
    set "PYTHON_BIN=%REPO_ROOT%\env\Scripts\python.exe"
    echo [INFO] Using virtual environment: %REPO_ROOT%\env
) else (
    where python >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%I in ('where python 2^>nul') do (
            if not defined PYTHON_BIN set "PYTHON_BIN=%%I"
        )
        echo [INFO] Using system Python: !PYTHON_BIN!
    ) else (
        where py >nul 2>&1
        if not errorlevel 1 (
            set "PYTHON_BIN=py -3"
            echo [INFO] Using Windows Python Launcher: py -3
        )
    )
)

if not defined PYTHON_BIN (
    echo.
    echo ===============================================================================
    echo [ERROR] Python 3.10+ interpreter could not be found on this system!
    echo ===============================================================================
    echo Please ensure Python 3.10 or higher is installed and added to your PATH,
    echo or create a virtual environment in .venv.
    echo.
    pause
    exit /b 1
)

echo [INFO] PYTHONPATH: %PYTHONPATH%
echo [INFO] Starting Blender MCP Server on stdio transport...
echo [INFO] Blender Daemon target: 127.0.0.1:9876 (Auto-detected / Auto-spawned)
echo ===============================================================================
echo.

"%PYTHON_BIN%" -m src.blender_mcp.server %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" goto :SERVER_ERROR

endlocal
exit /b 0

:SERVER_ERROR
echo.
echo ===============================================================================
echo [ERROR] Blender MCP Server exited with error code: %EXIT_CODE%
echo ===============================================================================
echo Common troubleshooting tips:
echo  1. Port Conflict: Ensure port 9876 is free [netstat -ano ^| findstr 9876].
echo  2. Blender 4.1+: Ensure Blender 4.1+ is installed in default location or set
echo     BLENDER_PATH to your blender.exe.
echo  3. Missing Dependencies: Run 'pip install -r requirements.txt' or ensure 'mcp'
echo     is installed.
echo ===============================================================================
echo.
pause
exit /b %EXIT_CODE%
