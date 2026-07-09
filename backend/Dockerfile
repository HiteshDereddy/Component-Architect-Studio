FROM python:3.11-slim

# Install system dependencies required for building llama.cpp
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies (building llama-cpp-python from source for optimal architecture support)
# CMAKE_ARGS allows compiling with hardware acceleration if available (e.g. CUDA on cloud)
ENV CMAKE_ARGS="-DLLAMA_METAL=OFF -DLLAMA_CUBLAS=OFF"
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY . .

# We assume the design-system.json is mounted or copied in via compose, but we'll create a placeholder directory
WORKDIR /app/backend

# Expose the FastAPI port
EXPOSE 8000

# Run the uvicorn server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
