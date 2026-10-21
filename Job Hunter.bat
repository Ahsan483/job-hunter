@echo off
where pythonw >nul 2>nul && (start "" pythonw -I "%~dp0gui.py" & exit /b)
where pyw >nul 2>nul && (start "" pyw -3 -I "%~dp0gui.py" & exit /b)
echo Python was not found. Install Python 3.10+ from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during setup.
pause
