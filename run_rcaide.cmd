@echo off
setlocal
set "RCAIDE_ROOT=%~dp0"
set "RCAIDE_ENV=%RCAIDE_ROOT%envs\RCAIDE"
set "RCAIDE_PYTHON=%RCAIDE_ENV%\python.exe"
if not exist "%RCAIDE_PYTHON%" set "RCAIDE_PYTHON=%RCAIDE_ENV%\Scripts\python.exe"
if not exist "%RCAIDE_PYTHON%" (
    echo Project Python was not found in "%RCAIDE_ENV%".
    echo Follow the setup instructions in README.md.
    exit /b 2
)
set "PATH=%RCAIDE_ENV%;%RCAIDE_ENV%\Library\bin;%RCAIDE_ENV%\Scripts;%PATH%"
set "PYTHONDONTWRITEBYTECODE=1"
if not exist "%RCAIDE_ROOT%outputs" mkdir "%RCAIDE_ROOT%outputs"
if not defined MPLCONFIGDIR set "MPLCONFIGDIR=%RCAIDE_ROOT%outputs\matplotlib-cache"
if "%~1"=="" (
    "%RCAIDE_PYTHON%" -E -s -B "%RCAIDE_ROOT%examples\verify_atmosphere.py"
) else (
    "%RCAIDE_PYTHON%" -E -s -B %*
)
exit /b %errorlevel%
