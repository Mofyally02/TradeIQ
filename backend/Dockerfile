FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY metaapi_worker ./metaapi_worker

RUN pip install --no-cache-dir .

EXPOSE 8000
