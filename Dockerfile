FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir flask requests gunicorn
COPY app.py .
COPY tm_agent.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh
EXPOSE 8000 8001
CMD ["./entrypoint.sh"]
