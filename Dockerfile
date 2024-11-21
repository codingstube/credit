# Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create templates directory
RUN mkdir -p templates

# Create an instance directory for the SQLite database
RUN mkdir -p instance && chmod 777 instance

EXPOSE 5000

CMD ["python", "loan_tracker.py"]
