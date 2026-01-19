@echo off
setlocal

:: 定义源目录和目标目录
set "SOURCE_DIR=%~dp0.agent\skills"
set "TARGET_DIR=%USERPROFILE%\.gemini\antigravity\skills"

echo --- Winyunq Agent Skill Global Installer ---
echo Source: "%SOURCE_DIR%"
echo Target: "%TARGET_DIR%"

:: 检查源目录是否存在
if not exist "%SOURCE_DIR%" (
    echo [ERROR] Source directory ".agent\skills" not found!
    exit /b 1
)

:: 创建目标目录
if not exist "%TARGET_DIR%" (
    mkdir "%TARGET_DIR%"
)

:: 同步 Skill 文件夹
echo Installing skills...
xcopy "%SOURCE_DIR%" "%TARGET_DIR%" /E /I /Y /Q

if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] Skills installed successfully to system space.
) else (
    echo [ERROR] Installation failed with error code %ERRORLEVEL%.
)

pause
