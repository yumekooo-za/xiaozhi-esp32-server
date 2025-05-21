@echo off
echo 正在检查Python环境...

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo Python未安装，请先安装Python 3.9或更高版本
    pause
    exit /b 1
)

REM 检查venv模块
python -c "import venv" >nul 2>&1
if errorlevel 1 (
    echo 正在安装venv模块...
    python -m pip install virtualenv
)

REM 检查虚拟环境是否存在
if not exist "venv" (
    echo 正在创建虚拟环境...
    python -m venv venv
)

REM 激活虚拟环境
echo 正在激活虚拟环境...
call venv\Scripts\activate.bat

REM 安装依赖
echo 正在安装依赖...
python -m pip install -r requirements.txt

REM 启动服务
echo 正在启动服务...
python server/server.py

REM 如果服务异常退出，保持窗口打开
pause 