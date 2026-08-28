FROM python:3.12.11-slim-bookworm@sha256:c00fc7b44d844b6da22861ec24af43968a5200eac4ec607b4725d585165d6b49 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

# QA materializes this verified wheelhouse and non-editable local wheel before
# selecting the release target with Docker networking disabled.
FROM base AS release
COPY .github/ci/python-bootstrap.lock /locks/python-bootstrap.lock
COPY .github/ci/python-product-runtime.lock /locks/python-runtime.lock
COPY .release/product/wheelhouse/ /wheelhouse/
COPY .release/product/product_api-0.1.0-py3-none-any.whl /wheelhouse/product_api-0.1.0-py3-none-any.whl
COPY .release/product/project-wheel.sha256 /wheelhouse/project-wheel.sha256
COPY shared /app/shared
COPY services/product_api/alembic.ini /app/alembic.ini
COPY services/product_api/alembic /app/alembic
RUN cd /wheelhouse \
    && sha256sum -c wheelhouse.sha256 \
    && sha256sum -c project-wheel.sha256 \
    && python -m pip install --no-index --find-links=/wheelhouse --no-deps --only-binary=:all: --require-hashes -r /locks/python-bootstrap.lock \
    && python -m pip install --no-index --find-links=/wheelhouse --no-deps --only-binary=:all: --require-hashes -r /locks/python-runtime.lock \
    && python -m pip install --no-index --find-links=/wheelhouse --no-deps /wheelhouse/product_api-0.1.0-py3-none-any.whl \
    && python -m pip check \
    && python -c "import importlib.metadata as m,json; rows=sorted((d.metadata['Name'].lower().replace('_','-'),d.version) for d in m.distributions()); open('/app/python-installed.json','w',encoding='utf-8',newline='\n').write(json.dumps(rows,separators=(',',':'))+'\n')" \
    && python -c "import product_api.main; import product_api.company_reports.worker; import product_api.company_reports.company_card_v2.narrative.worker" \
    && rm -rf /wheelhouse /locks

EXPOSE 8000
CMD ["uvicorn", "product_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Developer Compose keeps an exact hash-locked build. CI/release never selects
# this online target; no dependency resolution, editable install or build
# isolation is used here either.
FROM base AS local
COPY .github/ci/python-bootstrap.lock /locks/python-bootstrap.lock
COPY .github/ci/python-product-runtime.lock /locks/python-runtime.lock
COPY services/product_api /app/services/product_api
COPY shared /app/shared
RUN python -m pip install --no-deps --only-binary=:all: --require-hashes -r /locks/python-bootstrap.lock \
    && python -m pip install --no-deps --only-binary=:all: --require-hashes -r /locks/python-runtime.lock \
    && python -m pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/local-wheel /app/services/product_api \
    && python -m pip install --no-index --find-links=/tmp/local-wheel --no-deps /tmp/local-wheel/product_api-0.1.0-py3-none-any.whl \
    && python -m pip check \
    && rm -rf /tmp/local-wheel /locks /app/services/product_api

EXPOSE 8000
CMD ["uvicorn", "product_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
