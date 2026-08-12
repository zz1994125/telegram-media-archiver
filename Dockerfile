FROM python:3.13-slim

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && pip install --no-cache-dir yt-dlp "mcp==2.0.0" playwright \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app.py /app/app.py
COPY douyin_adapter.py /app/douyin_adapter.py
RUN useradd --create-home --uid 10001 archiver && mkdir /data && chown archiver:archiver /data
USER archiver
VOLUME ["/data"]
CMD ["python", "-u", "/app/app.py"]
