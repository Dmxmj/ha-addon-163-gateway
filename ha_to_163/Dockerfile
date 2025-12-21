FROM alpine:3.18

# 安装Python、构建依赖及SSL证书（新增ca-certificates）
RUN apk add --no-cache \
    python3 \
    py3-pip \
    gcc \
    python3-dev \
    musl-dev \
    ca-certificates && \  # 支持SSL证书验证
    rm -rf /var/cache/apk/*

WORKDIR /app

# 复制依赖文件并按固定版本安装
COPY requirements.txt .
RUN pip3 install --no-cache-dir \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --extra-index-url https://pypi.org/simple \
    -r requirements.txt  # 直接使用requirements.txt确保版本一致

# 验证版本是否匹配（精确检查）
RUN grep -E "paho-mqtt==|requests==|ntplib==" requirements.txt | while read -r line; do \
    if ! pip3 list | grep -q "$line"; then \
        echo "依赖版本不匹配: $line"; \
        exit 1; \
    fi; \
done

COPY . .

CMD ["python3", "/app/main.py"]
