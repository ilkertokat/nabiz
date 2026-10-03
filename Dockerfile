FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY nabiz ./nabiz
ENV NABIZ_DB=/data/nabiz.db
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/health')"
CMD ["python", "-m", "nabiz", "--host", "0.0.0.0", "--port", "8080", "--db", "/data/nabiz.db"]
