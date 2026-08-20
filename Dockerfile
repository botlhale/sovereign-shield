# SovereignShield portal container.
#
# Exists for the Azure Container Apps deployment, where the portal is reachable
# without a workspace login. Databricks Apps builds its own image from
# src/app.yaml and never uses this file.
#
# Only ./src is copied: the ingestion job, the synthetic data and the BIS
# rulebook workbook are not part of the serving path and have no business in a
# publicly reachable container.

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

COPY src/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/api_gateway.py src/portal_ui.py src/uc_query.py src/sdmx_ml_exporter.py ./
COPY src/templates ./templates

# The portal never writes to disk and holds no credential on the filesystem;
# it runs unprivileged so a serialization bug cannot become a container escape.
RUN useradd --create-home --uid 10001 portal
USER portal

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "api_gateway:app", "--host", "0.0.0.0", "--port", "8000"]
