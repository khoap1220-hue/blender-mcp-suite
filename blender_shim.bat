@echo off
setlocal EnableDelayedExpansion

if "%1"=="--version" (
    echo Blender 4.1.1
    exit /b 0
)

if "%1"=="-v" (
    echo Blender 4.1.1
    exit /b 0
)

rem Handle background script execution
set "SCRIPT="
set "ARGS="

:parse_args
if "%~1"=="" goto run_python
if "%~1"=="--python" (
    set "SCRIPT=%~2"
    shift
    shift
    goto parse_args
)
if "%~1"=="--" (
    shift
    goto collect_remaining
)
shift
goto parse_args

:collect_remaining
if "%~1"=="" goto run_python
set "ARGS=!ARGS! %1"
shift
goto collect_remaining

:run_python
if defined SCRIPT (
    python "!SCRIPT!" !ARGS!
    exit /b !ERRORLEVEL!
)

python -c "import sys; print('Blender 4.1.1')"
exit /b 0
