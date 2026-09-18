@echo off
chcp 65001 >nul
echo ========================================
echo   AI语音服务打包工具
echo ========================================

REM 切换到脚本目录
cd /d "%~dp0"

REM 安装依赖
echo [1/4] 检查依赖包...
python -m pip install pyinstaller -q

REM 清理旧文件
echo [2/4] 清理旧构建...
if exist "dist\AI_VoiceService.exe" del /q "dist\AI_VoiceService.exe"
if exist "build" rd /s /q "build"
if exist "AI_VoiceService.spec" del /q "AI_VoiceService.spec"

REM 执行打包
echo [3/4] 正在打包（约需1-3分钟）...
python -m PyInstaller --onefile ^
    --name "AI_VoiceService" ^
    --add-data ".;." ^
    --hidden-import faster_whisper ^
    --hidden-import duckduckgo_search ^
    --hidden-import ddgs ^
    --hidden-import primp ^
    --console ^
    --clean ^
    "voice_service.py"

REM 检查结果
echo [4/4] 检查打包结果...
if exist "dist\AI_VoiceService.exe" (
    echo.
    echo ========================================
    echo   打包成功！
    echo   文件位置: dist\AI_VoiceService.exe
    echo ========================================
) else (
    echo.
    echo ========================================
    echo   打包失败！请检查错误信息。
    echo ========================================
)

pause
