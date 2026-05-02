FROM python:3.13-slim

RUN pip install --no-cache-dir requests==2.32.* \
 && useradd -r -u 10001 watchdog

WORKDIR /app
COPY watchdog.py /app/watchdog.py
USER watchdog

ENTRYPOINT ["python", "-u", "/app/watchdog.py"]
