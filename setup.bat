@echo off
setlocal

REM ---------------------------------------------------------------------------
REM setup.bat
REM   One-time setup: downloads the 605 QPC v2 TTF fonts from
REM   https://github.com/nuqayah/qpc-fonts (folder mushaf-v2) into res\fonts\.
REM ---------------------------------------------------------------------------

echo.
echo === python-quran-images setup ===
echo.

REM --- check prerequisites ---------------------------------------------------
where git >nul 2>&1
if errorlevel 1 (
    echo ERROR: git is not installed or not on PATH.
    echo Install Git for Windows from https://git-scm.com/download/win
    exit /b 1
)

REM --- ensure target dir exists ---------------------------------------------
if not exist "res\fonts" mkdir "res\fonts"

REM --- skip if fonts already present ----------------------------------------
if exist "res\fonts\QCF2001.ttf" if exist "res\fonts\QCF2604.ttf" (
    echo Fonts already installed in res\fonts\ - nothing to do.
    goto :done
)

REM --- sparse clone of nuqayah/qpc-fonts ------------------------------------
echo Downloading fonts from nuqayah/qpc-fonts (mushaf-v2 only)...
if exist "_tmp_qpc_fonts" rd /S /Q "_tmp_qpc_fonts"

git clone --depth=1 --filter=blob:none --sparse ^
    https://github.com/nuqayah/qpc-fonts.git _tmp_qpc_fonts
if errorlevel 1 (
    echo Clone failed. Check your network or git version (>= 2.25 required).
    exit /b 1
)

pushd _tmp_qpc_fonts
git sparse-checkout set mushaf-v2
if errorlevel 1 (
    popd
    rd /S /Q "_tmp_qpc_fonts"
    echo sparse-checkout failed.
    exit /b 1
)
popd

echo Copying TTF files to res\fonts\...
copy /Y "_tmp_qpc_fonts\mushaf-v2\*.ttf" "res\fonts\" >nul
if errorlevel 1 (
    rd /S /Q "_tmp_qpc_fonts"
    echo Copy failed.
    exit /b 1
)

rd /S /Q "_tmp_qpc_fonts"

REM --- verify --------------------------------------------------------------
set FONT_COUNT=0
for /f %%n in ('dir /b /a-d "res\fonts\QCF2*.ttf" 2^>nul ^| find /c ".ttf"') do set FONT_COUNT=%%n
echo Installed %FONT_COUNT% TTF files in res\fonts\.

:done
echo.
echo Setup complete. Next steps:
echo   python migrate_v2.py            ^(build quran_v2.db^)
echo   python generate.py              ^(render pages to output\^)
echo   to_avif.bat output output-avif  ^(optional: AVIF conversion^)
echo.

endlocal
