FROM python:3.11-slim

# Install required libraries
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libcairo2 \
    libffi-dev \
    libssl-dev \
    build-essential \
    libpango1.0-dev \
    libgdk-pixbuf2.0-dev \
    libglib2.0-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . /app
WORKDIR /app

# Run the application
CMD ["python", "app.py"]
