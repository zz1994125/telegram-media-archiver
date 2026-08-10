FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && pip install --no-cache-dir yt-dlp \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app.py /app/app.py
RUN useradd --create-home --uid 10001 archiver && mkdir /data && chown archiver:archiver /data
USER archiver
VOLUME ["/data"]
CMD ["python", "-u", "/app/app.py"]
