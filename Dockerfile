# Use official Python image as base
FROM python:3.11-slim

# Install system dependencies for Bluetooth
RUN apt-get update && apt-get install -y \
    bluez \
    bluetooth \
    libbluetooth-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file and install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY . ./

# Expose port 5000 for Flask
EXPOSE 5000

# Set environment variables
ENV FLASK_APP=monitor.py
ENV PYTHONUNBUFFERED=1

# Command to run the application
CMD ["python", "monitor.py"]