# 基于Home Assistant官方基础镜像
ARG BUILD_FROM
FROM ${BUILD_FROM}

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-setuptools \
    py3-wheel \
    gcc \
    python3-dev \
    musl-dev \
    linux-headers \
    ntpdate

# 复制依赖清单
COPY requirements.txt .

# 安装Python依赖
RUN pip3 install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 复制插件所有文件
COPY . .

# 给启动脚本添加可执行权限
RUN chmod +x /app/run.sh

# 暴露日志输出
ENV PYTHONUNBUFFERED=1

# 启动命令
CMD ["/app/run.sh"]
