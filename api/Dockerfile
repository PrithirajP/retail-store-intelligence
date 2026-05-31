# Use lightweight python base image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install curl for the Docker healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire api folder contents into /app
COPY . .

# Expose the FastAPI port
EXPOSE 8000

# Run Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]