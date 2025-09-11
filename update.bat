@echo off
setlocal

:: ====== Configuration ======
set "REPO_URL=https://github.com/TommyB69420/MM-Bot-updates.git"
set "BRANCH=main"

echo.
echo ==========================================
echo     MafiaMatrix Bot Safe Self-Updater
echo ==========================================
echo.

:: Step 1: Check if Git is installed
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Git for Windows is not installed on this system.
    echo Please download and install it from:
    echo https://github.com/git-for-windows/git/releases
    pause
    exit /b 1
)

:: Step 2: Work from this script's folder
cd /d "%~dp0"

:: Step 3: Make sure .gitignore protects local-only files
if not exist ".gitignore" (
    > ".gitignore" echo settings.ini
    >> ".gitignore" echo game_data/
) else (
    findstr /i /r "^settings\.ini$" ".gitignore" >nul || (>> ".gitignore" echo settings.ini)
    findstr /i /r "^game_data/$"     ".gitignore" >nul || (>> ".gitignore" echo game_data/)
)

:: (Optional) Step 3.1: Quick backups of preserved files
if exist "settings.ini" (
    if not exist "_backup" mkdir "_backup"
    copy /y "settings.ini" "_backup\settings.ini.bak" >nul
)
if exist "game_data" (
    if not exist "_backup\game_data" mkdir "_backup\game_data"
    xcopy /e /i /y "game_data" "_backup\game_data" >nul
)

:: Step 4: Initialize repo if needed
if not exist ".git" (
    echo Initializing repository...
    git init
    git remote add origin "%REPO_URL%"
)

:: Step 5: Fetch the latest
echo Fetching latest from GitHub...
git fetch --depth=1 origin "%BRANCH%"
if %errorlevel% neq 0 (
    echo ERROR: Could not fetch from origin. Check your network or repo URL.
    pause
    exit /b 1
)

:: Step 6: Ensure we are on the target branch locally
git rev-parse --verify "%BRANCH%" >nul 2>&1
if %errorlevel% neq 0 (
    git checkout -b "%BRANCH%" || (echo ERROR: Could not create local branch & pause & exit /b 1)
) else (
    git checkout "%BRANCH%" >nul 2>&1 || (echo ERROR: Could not checkout local branch & pause & exit /b 1)
)

:: Step 7: Force reset tracked files to exactly match origin/%BRANCH%
echo Forcing local tracked files to match origin/%BRANCH%...
git reset --hard "origin/%BRANCH%"
if %errorlevel% neq 0 (
    echo ERROR: git reset --hard failed.
    pause
    exit /b 1
)

:: NOTE:
:: - The reset above overwrites ALL tracked files to the remote version.
:: - Because settings.ini and game_data/ are ignored, they are NOT tracked and won't be touched.

echo.
echo Update complete! Local edits to tracked files have been overwritten.
if exist settings.ini  echo Preserved local settings.ini
if exist game_data     echo Preserved local game_data directory
echo (Backups, if any: .\_backup\)
echo.
pause
exit /b 0