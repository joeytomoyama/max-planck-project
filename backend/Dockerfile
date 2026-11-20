FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./src/ ./src/
COPY ./tests/ ./tests/

# Create static directory with React index.html
RUN mkdir -p /app/static

# Expose port and run backend
EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
