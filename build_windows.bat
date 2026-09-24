:: /markbook_desktop/build_windows.bat
:: Builds dist\Markbook\markbook.exe, then the installer if Inno Setup is present.
@echo off
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
    echo Creating a virtual environment...
    python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat

echo Installing requirements...
python -m pip install -q --upgrade pip || goto :error
python -m pip install -q -r requirements.txt pyinstaller || goto :error

echo Building markbook.exe...
rmdir /s /q build dist\Markbook 2>nul
python -m PyInstaller markbook.spec --noconfirm --log-level WARN || goto :error
echo.
echo Built: dist\Markbook\markbook.exe

set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
    echo Building the installer...
    %ISCC% installer\markbook.iss || goto :error
    echo Installer: dist\installer\
) else (
    echo.
    echo Inno Setup was not found, so only the program folder was built.
    echo Install it from https://jrsoftware.org/isdl.php to produce MarkbookSetup.exe
)
echo.
echo Done.
goto :eof

:error
echo.
echo Build failed - see the messages above.
exit /b 1
