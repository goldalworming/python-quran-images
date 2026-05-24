@echo off
setlocal enabledelayedexpansion

set "SRC=%~1"
set "DST=%~2"
if "%SRC%"=="" set "SRC=output"
if "%DST%"=="" set "DST=output-avif"

if not exist "%SRC%" (
    echo Source folder "%SRC%" not found.
    exit /b 1
)
if not exist "%DST%" mkdir "%DST%"

for %%F in ("%SRC%\*.png") do (
    set "OUT=%DST%\%%~nF.avif"
    if exist "!OUT!" (
        echo SKIP %%~nxF  ^(already exists^)
    ) else (
        echo CONV %%~nxF  -^>  !OUT!
        ffmpeg -hide_banner -loglevel error -y -i "%%F" -c:v libaom-av1 -still-picture 1 -crf 30 "!OUT!"
    )
)

echo Done.
endlocal
