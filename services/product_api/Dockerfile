FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/product_api ./services/product_api
COPY shared ./shared

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -e ./services/product_api

EXPOSE 8000

CMD ["uvicorn", "product_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
