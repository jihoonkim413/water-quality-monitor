FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
COPY static ./static

# Readings live on a mounted volume so rebuilding the image never touches them
ENV WATER_DB=/data/water.db \
    PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

CMD ["python", "app.py"]
