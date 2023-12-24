# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory to /app
WORKDIR /fastapi-app

# Copy the requirements file into the container at /app
COPY requirements.txt . 

# Install any needed packages specified in requirements.txt
RUN pip install -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . .

# Run integrationsFAST.py when the container launches
CMD ["python", "integrationsfast:app"]
