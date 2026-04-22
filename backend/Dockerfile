# Use a CN mirror registry to avoid Docker Hub timeouts on cloud servers.
FROM docker.m.daocloud.io/library/python:3.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    # Use a stable PyPI mirror on CN cloud hosts
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn \
    # Large wheels (e.g. torch) need higher timeout
    PIP_DEFAULT_TIMEOUT=600

WORKDIR /app/backend

# System deps for scientific/python wheels fallback build
RUN set -eux; \
    # Use faster mirrors on common CN cloud hosts (Aliyun/Tencent/etc.)
    if [ -f /etc/apt/sources.list ]; then \
      sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' /etc/apt/sources.list || true; \
      sed -i 's|http://security.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list || true; \
    fi; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' /etc/apt/sources.list.d/debian.sources || true; \
      sed -i 's|http://security.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources || true; \
    fi; \
    apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30 update; \
    apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    curl \
  ; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/backend/requirements.txt
RUN pip install --prefer-binary --retries 10 --timeout 600 \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    --trusted-host download.pytorch.org \
    torch==2.2.2+cpu \
 && pip install --prefer-binary --retries 10 --timeout 600 -r /app/backend/requirements.txt

COPY . /app/backend

EXPOSE 8000

RUN chmod +x /app/backend/scripts/docker_entrypoint.sh /app/backend/scripts/docker_scheduler.sh

ENTRYPOINT ["/app/backend/scripts/docker_entrypoint.sh"]
