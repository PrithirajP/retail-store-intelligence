FROM python:3.12-slim

WORKDIR /app/cv_pipeline

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# OpenCV / Ultralytics runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/cv_pipeline/requirements.txt

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/cv_pipeline/requirements.txt

COPY . /app/cv_pipeline

CMD ["python", "orchestrator.py"]