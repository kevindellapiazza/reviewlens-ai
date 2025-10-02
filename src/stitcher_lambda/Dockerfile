# Use the official AWS base image for Python
FROM public.ecr.aws/lambda/python:3.12

# Copy the requirements file
COPY requirements.txt .

# Install the dependencies
RUN pip install -r requirements.txt --no-cache-dir

# Copy the application code
COPY main.py .

# Set the command to run the handler
CMD [ "main.handler" ]