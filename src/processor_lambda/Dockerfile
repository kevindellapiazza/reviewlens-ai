# Stage 1: Choose the base
FROM public.ecr.aws/lambda/python:3.12

# Stage 2: Copy the necessary files into the box.
COPY requirements.txt .

# Stage 3: Install the tools.
RUN pip install -r requirements.txt --no-cache-dir

# Stage 4: Copy the code.
COPY main.py .

# Stage 5: Tell which command to run on startup.
CMD [ "main.handler" ]