@echo off
setlocal
cd /d "%~dp0"
if exist "C:\power_streaming\.venv\Scripts\python.exe" (
    "C:\power_streaming\.venv\Scripts\python.exe" -E -u "%~dp0aplicar_atualizacao.py"
) else (
    py -3.12 -E -u "%~dp0aplicar_atualizacao.py"
)
if errorlevel 1 echo A atualizacao nao foi concluida. Leia o erro acima.
pause
endlocal
