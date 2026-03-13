# Dockerfile

FROM python:3.11-slim

# set working directory
WORKDIR /app

# install system dependencies needed by some Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# copy requirements first — Docker caches this layer
# if requirements.txt hasn't changed, this layer is reused (faster builds)
COPY requirements.txt .

# install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# copy the rest of the code
COPY . .

# Railway injects PORT at runtime — expose it
EXPOSE $PORT

# start the app
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]