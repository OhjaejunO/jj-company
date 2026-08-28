@echo off
setlocal EnableDelayedExpansion
rem ============================================================================
rem  JJ ONLY - move a Threads approval draft into publish_approval\
rem
rem  The move IS the signature. Nothing else signs an approval: an agent can
rem  write a draft into reports\ but it cannot write into publish_approval\ and
rem  it cannot run this file. So a file being in publish_approval\ means exactly
rem  one thing - a person put it there.
rem
rem  Double-click to use. Reads the drafts in reports\, shows them, asks, moves.
rem
rem  ASCII-only on purpose (charter section 6): .bat is read in the OEM codepage
rem  and Korean turns to noise here. The Korean explanation lives in
rem  docs\workers\publish-threads.md.
rem
rem  --probe  writes a marker and exits WITHOUT moving anything. Only the
rem           permission probe uses it, to check that an agent cannot run this
rem           file at all. Probe mode must stay harmless: if the gate were open
rem           the probe would actually execute this, and it must not move a real
rem           approval when that happens.
rem ============================================================================

set "HQ=C:\Users\ojaej\jj-company"
set "SRC=%HQ%\reports"
set "DST=%HQ%\publish_approval"
set "MARKER=%HQ%\logs\_move-approval-ran.marker"

if /I "%~1"=="--probe" (
    if not exist "%HQ%\logs" mkdir "%HQ%\logs"
    echo ran %DATE% %TIME%> "%MARKER%"
    echo [move-approval] probe mode - marker written, nothing moved.
    exit /b 0
)

echo ============================================================
echo  Threads approval - move draft to publish_approval\
echo ============================================================
echo.
echo  from : %SRC%
echo  to   : %DST%
echo.

set COUNT=0
for %%F in ("%SRC%\*.approval.json") do (
    set /a COUNT+=1
    echo   [!COUNT!] %%~nxF
    set "F!COUNT!=%%~fF"
    set "N!COUNT!=%%~nxF"
)

if %COUNT%==0 (
    echo   no draft found. The agent writes drafts as ^<ep^>.approval.json
    echo.
    pause
    exit /b 1
)

echo.
echo  Read the five posts in the manuscript first. Moving a file here
echo  IS approving it - there is no second confirmation later.
echo.
set "PICK="
set /p "PICK=number to move (blank = cancel): "
if not defined PICK goto :cancelled

set "SRCFILE=!F%PICK%!"
set "NAME=!N%PICK%!"
if not defined SRCFILE goto :badpick

rem  Target name drops the .approval part: ep39.approval.json -> ep39.json
rem  because the worker looks for publish_approval\<ep>.json.
for /f "tokens=1 delims=." %%A in ("!NAME!") do set "EP=%%A"

if not exist "%DST%" mkdir "%DST%"
if exist "%DST%\!EP!.json" (
    echo.
    echo   !EP!.json already exists in publish_approval\ - refusing.
    echo   An approval is written once. Remove the old one yourself if you
    echo   really mean to replace it.
    echo.
    pause
    exit /b 1
)

move /y "!SRCFILE!" "%DST%\!EP!.json" >nul
if errorlevel 1 (
    echo   move failed.
    pause
    exit /b 1
)
echo.
echo   moved: !NAME!  ->  publish_approval\!EP!.json
echo   signed by the move. The worker will now see it.
echo.
pause
exit /b 0

:cancelled
echo   cancelled - nothing moved.
pause
exit /b 1

:badpick
echo   no such number - nothing moved.
pause
exit /b 1
