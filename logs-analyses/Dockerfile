FROM python:3.9-slim
RUN pip install kubernetes
COPY logs-analyses/log_collector.py /app/log_collector.py
WORKDIR /app
CMD ["python", "log_collector.py"]