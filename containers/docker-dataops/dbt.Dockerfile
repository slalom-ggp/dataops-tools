ARG source_image=python:3.7

FROM ${source_image}

# Update and install system packages
RUN apt-get update -y && \
    apt-get install -y -q \
    git \
    build-essential \
    libpq-dev \
    python-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install DBT
RUN pip install dbt==0.14.3

# Set environment variables
ENV DBT_DIR /dbt

# Set working directory
WORKDIR $DBT_DIR

COPY bootstrap.sh $DBT_DIR/bootstrap.sh
#COPY project $DBT_DIR/project
# Run dbt
ENTRYPOINT [ "bash","./bootstrap.sh" ]
CMD ["dbt"]
