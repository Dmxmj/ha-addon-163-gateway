#!/bin/sh
set -e

# 再次确认依赖
echo "验证依赖是否安装..."
if ! python3 -c "import requests"; then
    echo "紧急安装 requests..."
    pip3 install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple requests==2.31.0
fi
echo "等待Home Assistant启动...（延迟${STARTUP_DELAY:-30}秒）"
sleep ${STARTUP_DELAY:-30}

# 启动主程序
echo "启动HA to 163 Gateway..."
exec python3 /app/main.py
