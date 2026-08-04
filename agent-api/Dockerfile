FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace/agent-api

COPY agent-api/requirements.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY agent-api/app ./app
COPY agent-api/scripts ./scripts
COPY knowledge ../knowledge

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
