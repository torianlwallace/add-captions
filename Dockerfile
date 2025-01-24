FROM python:3.9-slim

# Install ImageMagick and its dependencies
RUN apt-get update && apt-get install -y \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

# Configure ImageMagick policy to allow reading PDFs and text operations
COPY policy.xml /etc/ImageMagick-6/policy.xml

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy function code
COPY main.py .

# Cloud Function handler
ENTRYPOINT ["python", "-m", "functions_framework", "--target=add_captions"]