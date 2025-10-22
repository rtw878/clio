@echo off
echo ========================================
echo    Batch CO Series Cloning Script
echo ========================================
echo.
echo Choose an option:
echo.
echo 1. Start from beginning (CO 1+)
echo 2. Clone specific range (e.g., CO 1-23)
echo 3. Continue from where we left off
echo 4. Custom configuration
echo.
set /p choice="Enter your choice (1-4): "

if "%choice%"=="1" (
    echo.
    echo Starting from CO 1 (beginning)...
    python batch_clone_co_series.py --start-series 1 --batch-size 5 --delay 2
) else if "%choice%"=="2" (
    echo.
    set /p start="Enter start series number: "
    set /p end="Enter end series number: "
    echo.
    echo Cloning CO %start%-%end%...
    python batch_clone_co_series.py --start-series %start% --end-series %end% --batch-size 10 --delay 3
) else if "%choice%"=="3" (
    echo.
    echo Continuing from where we left off (CO 31+)...
    python batch_clone_co_series.py --start-series 31 --batch-size 10 --delay 3
) else if "%choice%"=="4" (
    echo.
    echo Running with custom configuration...
    python batch_clone_co_series.py
) else (
    echo Invalid choice!
    pause
    exit /b 1
)

echo.
echo Batch cloning completed!
pause
