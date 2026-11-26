FROM python:3.12-slim
ARG HC_BUILD_REVISION=unknown
ENV HC_BUILD_REVISION=$HC_BUILD_REVISION \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=3000 \
    HC_DATA_DIR=/data
# LilyPond engraves the score; poppler-utils turns score pages into images for the browser.
RUN apt-get update \
 && apt-get install -y --no-install-recommends lilypond poppler-utils \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY engine ./engine
COPY app ./app
COPY pieces ./pieces
RUN mkdir -p /data
VOLUME ["/data"]
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','3000'), timeout=2)"
CMD ["sh", "-c", "uvicorn server:app --app-dir app --host 0.0.0.0 --port ${PORT}"]
