FROM python:3.12-slim

WORKDIR /app

# Install build essentials for numpy/pandas
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies with pip upgrade
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code and data files
COPY app.py .
COPY recipe_api.csv .

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application with optimizations
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]