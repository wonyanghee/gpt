@echo off
cd /d "%~dp0"
echo [1/2] Installing packages...
python -m pip install -q pandas numpy pyyaml
if errorlevel 1 (
  echo Python is not installed or not on PATH. Install it from python.org and check "Add Python to PATH".
  pause
  exit /b 1
)
echo [2/2] Running demo (about 30 seconds)...
python run_demo.py --quiet --html demo.html
if errorlevel 1 (
  pause
  exit /b 1
)
start "" demo.html
pause
