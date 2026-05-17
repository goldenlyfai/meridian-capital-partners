FROM python:3.12-slim

WORKDIR /app

# System deps for lxml, pyarrow
RUN apt-get update && apt-get install -y \
    gcc g++ libxml2-dev libxslt-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent data lives on Railway's volume mount at /data
# We override the DB path via env var MERIDIAN_DB_PATH
ENV MERIDIAN_DB_PATH=/data/meridian.db
ENV MERIDIAN_OUTPUT_DIR=/data/output
ENV MERIDIAN_CACHE_DIR=/data/cache

RUN mkdir -p /data/output /data/cache /data/output/reports

EXPOSE 8000

COPY docker_start.sh /docker_start.sh
RUN chmod +x /docker_start.sh

CMD ["/docker_start.sh"]
