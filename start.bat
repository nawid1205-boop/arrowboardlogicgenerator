@echo off
cd /d "%~dp0"
py -3 -c "import tkinter" >nul 2>&1
if %errorlevel%==0 (
    py -3 "%~dp0main.py"
    goto :end
)
python -c "import tkinter" >nul 2>&1
if %errorlevel%==0 (
    python "%~dp0main.py"
    goto :end
)
echo Nie znaleziono Pythona 3.11+ z Tkinter.
echo Zainstaluj Python ze strony python.org i zaznacz tcl/tk.
pause
:end
