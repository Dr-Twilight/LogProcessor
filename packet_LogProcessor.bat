@echo off
cd /d %~dp0

echo 开始打包LogProcessor.py...
pyinstaller --clean -F --hidden-import=pandas --hidden-import=openpyxl --name "LogProcessor" LogProcessor.py

echo.
echo 打包完成。可执行文件位于dist目录下。
pause