# Use Python 3.11 as base
FROM python:3.11-slim

# Install Node.js 20.x
RUN apt-get update && apt-get install -y \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy all files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Build frontend
WORKDIR /app/frontend
RUN npm install
RUN npm run build

# Set working directory to backend for execution
WORKDIR /app/backend

# Expose port (Railway will set PORT env var)
ENV PORT=8000
EXPOSE 8000

# Start the backend
CMD ["python", "main.py"]
