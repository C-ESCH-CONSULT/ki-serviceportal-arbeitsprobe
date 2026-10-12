FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY kommunal_ki ./kommunal_ki
COPY data ./data

RUN useradd --create-home portal && mkdir -p /app/protokoll && chown portal /app/protokoll
USER portal

EXPOSE 8000
CMD ["uvicorn", "kommunal_ki.api:app", "--host", "0.0.0.0", "--port", "8000"]
