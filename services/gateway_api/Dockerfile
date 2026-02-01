FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/gateway_api ./services/gateway_api
COPY shared ./shared

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -e ./services/gateway_api

EXPOSE 8001

CMD ["uvicorn", "gateway_api.main:app", "--host", "0.0.0.0", "--port", "8001"]
