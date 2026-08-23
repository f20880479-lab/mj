@echo off
chcp 65001 >nul
echo 正在安装依赖（pynput + pillow，国内镜像）...
python -m pip install pynput pillow -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.
echo 安装完成！双击「启动特效.bat」即可使用。
pause
