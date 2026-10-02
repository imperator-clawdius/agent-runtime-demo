FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
ENV HOST=0.0.0.0
RUN useradd --uid 10001 --create-home app
USER app

EXPOSE 8000

CMD ["python", "src/agent.py"]
