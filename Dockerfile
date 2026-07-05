FROM python:3.10-slim

# Install system dependencies for PyTorch, OpenCV, Pillow, and ReportLab
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    libfreetype6-dev \
    libwebp-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements file first for layer caching optimization
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

# Copy remaining source code
COPY . .

# Expose port
EXPOSE 5000

# Start app
CMD ["python", "backend_app.py"]
