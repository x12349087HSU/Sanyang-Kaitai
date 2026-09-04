@echo off
REM Windows Task Scheduler 排程呼叫這支，跑 scripts\prefetch_and_publish.py
REM 並把輸出附加寫進 logs\prefetch.log（排程無人值守執行，事後要能查 log 診斷）。
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs

echo. >> logs\prefetch.log
echo ==== %date% %time% ==== >> logs\prefetch.log
call .venv\Scripts\activate.bat
python scripts\prefetch_and_publish.py >> logs\prefetch.log 2>&1
set EXITCODE=%ERRORLEVEL%
echo exit code: %EXITCODE% >> logs\prefetch.log
exit /b %EXITCODE%
