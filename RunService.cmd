@echo off
:restart
echo ========================================
echo  Starting %~1...
echo ========================================
echo.
%~2 %~3
echo.
echo ========================================
echo  %~1 stopped. Press any key to restart.
echo ========================================
pause >nul
goto restart
