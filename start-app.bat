@echo off
setlocal
cd /d "%~dp0"

rem Neu bien moi truong ELECTRON_RUN_AS_NODE dinh sang tu tien trinh cha (VD chay tu
rem trong Claude Code) thi electron.cmd se chi chay nhu Node.js thuong, KHONG mo cua so
rem that - xoa han bien nay o day de dam bao luon chay dung electron.exe that.
set ELECTRON_RUN_AS_NODE=

echo ============================================
echo   StudioFlow - dang khoi dong (che do dev)
echo ============================================

echo [1/3] Dang dong cac tien trinh cu (neu co)...
powershell -NoProfile -Command "Get-Process -Name electron,node -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue" >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/3] Dang khoi dong frontend (Vite dev server)...
start "StudioFlow - Frontend (dung cua so nay khi thoat)" /min cmd /c "npm run dev:frontend > frontend_dev.log 2>&1"
timeout /t 4 /nobreak >nul

echo [3/3] Dang bien dich + mo StudioFlow (backend se tu khoi dong ben trong)...
echo   (Luu y: "npm run dev:electron" bi loi tren may nay vi lenh "electron"
echo   khong tro dung electron.exe that - dung truc tiep duong dan .bin de tranh loi.)
echo.
echo   Dong cua so nay se KHONG tu dong tat app frontend.
echo   Muon thoat han: dong cua so app StudioFlow + dong ca cua so
echo   "StudioFlow - Frontend" (dang thu nho o taskbar).
echo.
call node_modules\.bin\tsc.cmd -p electron\tsconfig.json
call node_modules\.bin\electron.cmd ./electron/dist/main.js

endlocal
