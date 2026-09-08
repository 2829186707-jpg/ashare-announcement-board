@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   A股公告看板启动器
echo ============================================
echo.
echo   [1] 启动看板服务（浏览器访问 http://127.0.0.1:8765）
echo   [2] 手动抓取一次公告数据
echo   [3] 更新行业映射表（每月跑一次即可）
echo   [0] 退出
echo.
set /p choice=请输入选项后回车: 

if "%choice%"=="1" goto start
if "%choice%"=="2" goto fetch
if "%choice%"=="3" goto industry
goto end

:start
echo.
echo 看板服务启动中... 浏览器打开 http://127.0.0.1:8765
echo 按 Ctrl+C 停止服务
echo.
"C:\Users\veken\AppData\Local\Programs\Python\Python314\python.exe" server.py
goto end

:fetch
echo.
echo 开始抓取公告（断点续抓，自动补上次之后的所有日期）...
"C:\Users\veken\AppData\Local\Programs\Python\Python314\python.exe" fetch.py
pause
goto end

:industry
echo.
echo 更新行业映射表...
"C:\Users\veken\AppData\Local\Programs\Python\Python314\python.exe" build_industry.py
pause
goto end

:end
exit
