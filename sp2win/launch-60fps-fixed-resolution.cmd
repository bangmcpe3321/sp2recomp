@echo off
setlocal
set "NX_PLAZA_60FPS=1"
set "NX_DISABLE_DYNAMIC_RESOLUTION=1"
call "%~dp0launch-controller-gameplay.cmd" %*
