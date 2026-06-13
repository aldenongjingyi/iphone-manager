@echo off
REM iPhone Manager — Windows setup script
REM Run as a regular user (no admin required for pip/venv)

setlocal EnableDelayedExpansion
set "SCRIPT_DIR=%~dp0"

echo.
echo ================================================
echo   iPhone Manager -- Windows Setup
echo ================================================
echo.

REM ── 1. Check Python ──────────────────────────────────────────────
echo [1/5] Checking Python 3...
python --version >nul 2>&1
if errorlevel 1 (
    py --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python 3 not found.
        echo.
        echo Please install Python 3.10+ from https://www.python.org/downloads/
        echo Make sure to check "Add Python to PATH" during installation.
        pause
        exit /b 1
    ) else (
        set "PYTHON=py"
    )
) else (
    set "PYTHON=python"
)

for /f "tokens=*" %%v in ('!PYTHON! --version') do echo Found: %%v

REM ── 2. Check Apple Devices / iTunes ──────────────────────────────
echo.
echo [2/5] Checking Apple Devices driver...
echo.
REM pymobiledevice3 on Windows uses the Apple Mobile Device Support driver.
REM This is installed with iTunes or the Apple Devices app from Microsoft Store.
REM We just warn if it's not found — the user may have it already.

sc query "Apple Mobile Device Service" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Apple Mobile Device Service not detected.
    echo        Install one of these to enable iPhone USB communication:
    echo          Option A: Apple Devices app — Microsoft Store (search "Apple Devices")
    echo          Option B: iTunes — https://www.apple.com/itunes/download/win64
    echo.
    echo        If already installed, this warning can be ignored.
) else (
    echo Apple Mobile Device Service: found
)

REM ── 3. Virtual environment ────────────────────────────────────────
echo.
echo [3/5] Setting up Python virtual environment...
if exist "%SCRIPT_DIR%.venv\Scripts\activate.bat" (
    echo Virtual environment already exists.
) else (
    !PYTHON! -m venv "%SCRIPT_DIR%.venv"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created.
)

REM ── 4. Install packages ───────────────────────────────────────────
echo.
echo [4/5] Installing Python packages...
call "%SCRIPT_DIR%.venv\Scripts\activate.bat"

python -m pip install --upgrade pip --quiet
if errorlevel 1 echo [WARN] pip upgrade failed, continuing...

pip install -r "%SCRIPT_DIR%requirements.txt"
if errorlevel 1 (
    echo [ERROR] Package installation failed.
    echo Try running:  pip install flask pymobiledevice3
    pause
    exit /b 1
)

echo Packages installed successfully.

REM ── 5. Create run.bat ─────────────────────────────────────────────
echo.
echo [5/5] Creating run.bat...
(
    echo @echo off
    echo cd /d "%%~dp0"
    echo call ".venv\Scripts\activate.bat"
    echo python app.py
    echo pause
) > "%SCRIPT_DIR%run.bat"
echo Created run.bat

REM ── Done ──────────────────────────────────────────────────────────
echo.
echo ================================================
echo   Setup complete!
echo ================================================
echo.
echo To start iPhone Manager, run:
echo   run.bat
echo.
echo Or from command prompt:
echo   .venv\Scripts\activate
echo   python app.py
echo.
pause
