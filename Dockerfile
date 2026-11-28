FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /srv/agency-os

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations

COPY app ./app

RUN groupadd --system --gid 10001 agency \
    && useradd --system --uid 10001 --gid agency --home-dir /nonexistent --shell /usr/sbin/nologin agency

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
