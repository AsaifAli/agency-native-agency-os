FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /srv/agency-os

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations

COPY app ./app
COPY integrations/__init__.py ./integrations/__init__.py
COPY integrations/evaluation_harness_source/__init__.py ./integrations/evaluation_harness_source/__init__.py
COPY integrations/evaluation_harness_source/evals ./integrations/evaluation_harness_source/evals

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
