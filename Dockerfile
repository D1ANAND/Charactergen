# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

# Set the working directory to /fastapi-app
WORKDIR /INTEGRATE

ENV HOST 0.0.0.0

# Copy the requirements file into the container at /app
COPY requirements.txt . 

# Install any needed packages specified in requirements.txt
RUN pip install -r requirements.txt

# Copy the current directory contents into the container 
COPY . .

# Expose the port your app runs on
EXPOSE 8000

# Run integrationsFAST.py when the container launches
CMD [ "python", "-m", "uvicorn", "integrationsfast:app", "--host", "0.0.0.0", "--port", "8080" ]
# "python" , "integrationsfast.py"