FROM python:3.13-slim
LABEL org.opencontainers.image.source="https://github.com/Quackudy/2110471-Computer-Network-I-Websocket-Project"
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home relay
COPY server.py .
COPY static ./static
USER relay
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=3)"
CMD ["python", "server.py"]
