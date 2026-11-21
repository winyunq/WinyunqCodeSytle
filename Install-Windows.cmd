@echo off
setlocal
cd /d "%~dp0"
call Bootstrap-Doxygen.cmd || exit /b 1

if defined VSCMD_VER goto configure
for /f "usebackq delims=" %%I in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -prerelease -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "CODESTYLE_VS=%%I"
if not defined CODESTYLE_VS (
    echo Install Visual Studio with the Desktop development with C++ workload. 1>&2
    exit /b 1
)
call "%CODESTYLE_VS%\VC\Auxiliary\Build\vcvars64.bat" || exit /b 1

:configure
set "CODESTYLE_NINJA=%VSINSTALLDIR%Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
if not exist "%CODESTYLE_NINJA%" set "CODESTYLE_NINJA=ninja"
cmake -S . -B .runtime\native-build -G Ninja "-DCMAKE_MAKE_PROGRAM=%CODESTYLE_NINJA%" -DCMAKE_BUILD_TYPE=Release || exit /b 1
cmake --build .runtime\native-build --parallel 4 || exit /b 1
cmake --install .runtime\native-build --prefix .runtime\native
exit /b %errorlevel%
