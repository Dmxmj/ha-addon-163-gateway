ARG BUILD_FROM
FROM ${BUILD_FROM}

# 定义构建参数（从workflow传入）
ARG BUILD_VERSION
ARG BUILD_DATE

# 标签信息
LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="addon" \
    io.hass.arch="amd64|aarch64" \
    org.opencontainers.image.version="${BUILD_VERSION}" \
    org.opencontainers.image.created="${BUILD_DATE}" \
    org.opencontainers.image.source="https://github.com/${GITHUB_REPOSITORY}"

# 安装Python依赖
RUN \
    apk add --no-cache \
        python3 \
        py3-pip \
    && pip3 install --no-cache-dir \
        paho-mqtt==1.6.1 \
        requests==2.31.0 \
        ntplib==0.4.0

# 复制Add-on文件到镜像中
COPY . /app/
WORKDIR /app

# 赋予启动脚本执行权限
RUN chmod +x /app/run.sh

# 启动命令（执行run.sh）
CMD ["/app/run.sh"]
