# Dockerfile

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY . .

# upgrade pip first
RUN /usr/local/bin/pip install --no-cache-dir --upgrade pip

# install uvicorn explicitly first to confirm it works
RUN /usr/local/bin/pip install --no-cache-dir uvicorn==0.41.0

# install the rest
RUN /usr/local/bin/pip install --no-cache-dir -r requirements.txt

# verify
RUN /usr/local/bin/python -m uvicorn --version

CMD ["/usr/local/bin/python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]