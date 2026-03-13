# Dockerfile

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# install directly to system python — no venv, explicit pip path
RUN /usr/local/bin/pip install --no-cache-dir --upgrade pip && \
    /usr/local/bin/pip install --no-cache-dir -r requirements.txt

CMD ["/usr/local/bin/python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]