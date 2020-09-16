# Alpine base image can lead to long compilation times and errors.
# https://pythonspeed.com/articles/base-image-python-docker-images/
# The one below is based on Debian 10.
FROM python:3.8.5-slim-buster

LABEL maintainer="jeff@cloudreactor.io"

# For the web-server task example only.
# If you are deploying the web-server, uncomment this line.
# EXPOSE 7070

WORKDIR /usr/src/app

# Install any OS libraries required to build python libraries
# For example, libpq-dev is required to build psycopg2
RUN apt-get update \
 && apt-get install -y libpq-dev=11.7-0+deb10u1 build-essential=12.6 --no-install-recommends \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN pip install --no-input --no-cache-dir --upgrade pip==20.2.3
RUN pip install --no-input --no-cache-dir pip-tools==5.3.1 MarkupSafe==1.1.1 requests==2.24.0

COPY requirements.in .

RUN pip-compile --allow-unsafe --generate-hashes \
  requirements.in --output-file requirements.txt

# Install dependencies
# https://stackoverflow.com/questions/45594707/what-is-pips-no-cache-dir-good-for
RUN pip install --no-input --no-cache-dir -r requirements.txt

# Run as non-root user for better security
RUN groupadd appuser && useradd -g appuser --create-home appuser
USER appuser
WORKDIR /home/appuser

# Pre-create this directory so that it has the correct permission
# when ECS mounts a volume, otherwise it will be owned by root.
RUN mkdir scratch

# Output directly to the terminal to prevent logs from being lost
# https://stackoverflow.com/questions/59812009/what-is-the-use-of-pythonunbuffered-in-docker-file
ENV PYTHONUNBUFFERED 1

# Don't write *.pyc files
ENV PYTHONDONTWRITEBYTECODE 1

# Enable the fault handler for segfaults
# https://docs.python.org/3/library/faulthandler.html
ENV PYTHONFAULTHANDLER 1

ENV PYTHONPATH /home/appuser/src

COPY deploy/files/proc_wrapper_1.3.0.py proc_wrapper.py

COPY src ./src

ARG ENV_FILE_PATH=deploy/files/.env.dev

# copy deployment environment settings
COPY ${ENV_FILE_PATH} .env

ENTRYPOINT python proc_wrapper.py $TASK_COMMAND
