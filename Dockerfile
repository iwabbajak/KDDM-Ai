FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    wget \
  && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# Install Python deps from requirements.txt
WORKDIR /workspace
COPY requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Create model directory and download model (≈4GB)
WORKDIR /workspace/models
RUN wget -O mistral.gguf \
  https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF/resolve/main/mistral-7b-instruct-v0.1.Q4_K_M.gguf

# Copy app code
WORKDIR /workspace
COPY app.py /workspace/app.py

# Copy logo ico
WORKDIR /workspace
COPY logo.ico /workspace/static/logo.ico

# Copy logo png
WORKDIR /workspace
COPY logo.png /workspace/static/logo.png


# Expose Flask port
EXPOSE 8000

# Default command: run Flask app
ENV MODEL_PATH=/workspace/models/mistral.gguf \
    CTX=4096 \
    THREADS=4 \
    N_GPU_LAYERS=0 \
    CHAT_FORMAT=mistral-instruct \
    MAX_TOKENS=512 \
    TEMPERATURE=0.7 \
    TOP_P=0.9

#CMD ["python", "app.py"]
CMD ["gunicorn", "-w", "1", "-k", "gthread", "--threads", "8", "-b", "0.0.0.0:8000", "app:app"]