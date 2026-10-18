FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY static static
EXPOSE 8000
# 1 worker is plenty: a turn is ~1 ms of CPU; scale out with more containers
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
