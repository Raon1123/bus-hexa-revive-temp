# app/Dockerfile

FROM continuumio/miniconda3:24.9.2-0

# Set the working directory
WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    cron \
    vim \
    && rm -rf /var/lib/apt/lists/*

RUN ln -snf /usr/share/zoneinfo/Asia/Seoul /etc/localtime

# Copy the current directory contents into the container at /app
COPY requirements.yaml /app

RUN conda env create -f requirements.yaml

# activate the environment
RUN echo "conda activate $(head -1 /app/requirements.yaml | cut -d' ' -f2)" >> ~/.bashrc
ENV PATH=/opt/conda/envs/bushexa/bin:$PATH

COPY runscript.sh /app
COPY ./secret /app/secret

EXPOSE 8501 8501

RUN chmod +x /app/runscript.sh
ENTRYPOINT ["/bin/bash", "runscript.sh"]
