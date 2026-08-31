FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=80

WORKDIR /app

# Install system dependencies if any
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Expose port 80 (mapped to host 3000 by docker run)
EXPOSE 80

# Run FastAPI app via Uvicorn
CMD ["python3", "-m", "uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "80"]
