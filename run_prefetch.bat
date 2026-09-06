@echo off
REM Windows Task Scheduler 排程呼叫這支：跑 scripts\prefetch_stock_index.py
REM （股票代號/名稱索引，給「直接篩選個股」用）、scripts\prefetch_and_publish.py
REM （均線篩選資料）、scripts\prefetch_fundamentals.py（基本面摘要資料）三支，
REM 各自獨立 commit/push，刻意不用 && 串接——其中一支失敗不該連帶讓另一支
REM 不執行，各自的 exit code 分開記錄，方便從 log 看出是哪段出包。輸出附加
REM 寫進 logs\prefetch.log（排程無人值守執行，事後要能查 log 診斷）。
REM
REM 執行順序刻意把 prefetch_stock_index.py 排在最前面：這台電腦沒有設定
REM FINMIND_TOKEN，FinMind 呼叫都是匿名額度，而 prefetch_fundamentals.py
REM 一次要對 150 檔股票各打 4-5 個 FinMind 資料集（見「公司基本面分析」
REM 專案 config.py 的說明，實測跑到約 40 檔就會把匿名額度用完），如果排在
REM stock_index 前面，會把額度用光、害 stock_index 那唯一一次 FinMind 呼叫
REM （TaiwanStockInfo）也跟著收到 402 失敗——這不是新的 IP 封鎖，單純是
REM 執行順序害量小的呼叫被量大的呼叫搶先用光額度，讓量小的排最前面即可。
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs

echo. >> logs\prefetch.log
echo ==== %date% %time% ==== >> logs\prefetch.log
call .venv\Scripts\activate.bat

python scripts\prefetch_stock_index.py >> logs\prefetch.log 2>&1
set INDEX_EXITCODE=%ERRORLEVEL%
echo [prefetch_stock_index] exit code: %INDEX_EXITCODE% >> logs\prefetch.log

python scripts\prefetch_and_publish.py >> logs\prefetch.log 2>&1
set MA_EXITCODE=%ERRORLEVEL%
echo [prefetch_and_publish] exit code: %MA_EXITCODE% >> logs\prefetch.log

python scripts\prefetch_fundamentals.py >> logs\prefetch.log 2>&1
set FUND_EXITCODE=%ERRORLEVEL%
echo [prefetch_fundamentals] exit code: %FUND_EXITCODE% >> logs\prefetch.log

set EXITCODE=0
if not "%MA_EXITCODE%"=="0" set EXITCODE=1
if not "%FUND_EXITCODE%"=="0" set EXITCODE=1
if not "%INDEX_EXITCODE%"=="0" set EXITCODE=1
echo overall exit code: %EXITCODE% >> logs\prefetch.log
exit /b %EXITCODE%
