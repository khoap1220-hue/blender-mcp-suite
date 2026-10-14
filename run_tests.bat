@echo off
setlocal EnableDelayedExpansion

title Blender MCP Test Suite Runner
echo ===============================================================================
echo                Blender MCP Automated End-to-End Test Suite Runner
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

rem Locate Python Interpreter
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
    echo [ERROR] Python 3.10+ interpreter could not be found on this system.
    echo ===============================================================================
    pause
    exit /b 1
)

echo [INFO] PYTHONPATH: %PYTHONPATH%

if "%~1"=="" (
    echo [INFO] Running primary E2E test suite: tests/test_blender_mcp_e2e.py -v --tb=short
    echo ===============================================================================
    echo.
    "%PYTHON_BIN%" -m pytest tests/test_blender_mcp_e2e.py -v --tb=short
) else (
    echo [INFO] Running pytest with custom arguments: %*
    echo ===============================================================================
    echo.
    "%PYTHON_BIN%" -m pytest %*
)

set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" goto :TEST_ERROR

echo.
echo ===============================================================================
echo [SUCCESS] All Blender MCP tests passed successfully. Exit code: 0
echo ===============================================================================
endlocal
exit /b 0

:TEST_ERROR
echo.
echo ===============================================================================
echo [ERROR] Test suite failed with exit code: %EXIT_CODE%
echo ===============================================================================
echo Troubleshooting:
echo  1. Check whether Blender 4.1+ is installed at default path.
echo  2. Check if another process is holding port 9876.
echo  3. Review the traceback above for specific assertion failures.
echo ===============================================================================
echo.
pause
exit /b %EXIT_CODE%
