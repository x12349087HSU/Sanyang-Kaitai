@echo off
REM Windows Task Scheduler 排程呼叫這支：跑 scripts\prefetch_and_publish.py
REM （均線篩選資料）、scripts\prefetch_fundamentals.py（基本面摘要資料）、
REM scripts\prefetch_stock_index.py（股票代號/名稱索引，給「直接篩選個股」
REM 用）三支，各自獨立 commit/push，刻意不用 && 串接——其中一支失敗不該
REM 連帶讓另一支不執行，各自的 exit code 分開記錄，方便從 log 看出是哪段
REM 出包。輸出附加寫進 logs\prefetch.log（排程無人值守執行，事後要能查
REM log 診斷）。
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs

echo. >> logs\prefetch.log
echo ==== %date% %time% ==== >> logs\prefetch.log
call .venv\Scripts\activate.bat

python scripts\prefetch_and_publish.py >> logs\prefetch.log 2>&1
set MA_EXITCODE=%ERRORLEVEL%
echo [prefetch_and_publish] exit code: %MA_EXITCODE% >> logs\prefetch.log

python scripts\prefetch_fundamentals.py >> logs\prefetch.log 2>&1
set FUND_EXITCODE=%ERRORLEVEL%
echo [prefetch_fundamentals] exit code: %FUND_EXITCODE% >> logs\prefetch.log

python scripts\prefetch_stock_index.py >> logs\prefetch.log 2>&1
set INDEX_EXITCODE=%ERRORLEVEL%
echo [prefetch_stock_index] exit code: %INDEX_EXITCODE% >> logs\prefetch.log

set EXITCODE=0
if not "%MA_EXITCODE%"=="0" set EXITCODE=1
if not "%FUND_EXITCODE%"=="0" set EXITCODE=1
if not "%INDEX_EXITCODE%"=="0" set EXITCODE=1
echo overall exit code: %EXITCODE% >> logs\prefetch.log
exit /b %EXITCODE%
