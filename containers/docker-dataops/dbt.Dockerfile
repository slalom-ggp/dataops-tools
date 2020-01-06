ARG source_image=slalomggp/spark:latest-dev
# ARG source_image=python:3.7

FROM ${source_image}

ARG dbt_spark_source=git+https://github.com/fishtown-analytics/dbt-spark@master

# Set version filters, e.g. '>=0.1.0', '>=1.0,<=2.0'
# Optionally, use the text 'skip' to skip or '' to use latest version
ARG dbt_version_filter=''
ARG meltano_version_filter='skip'

RUN mkdir -p /projects && \
    mkdir -p /.c && \
    mkdir -p /venv
WORKDIR /projects

RUN apt-get update && apt-get install -y -q \
    build-essential \
    git \
    g++ \
    libsasl2-2 \
    libsasl2-dev \
    libsasl2-modules-gssapi-mit \
    libpq-dev \
    python-dev \
    python3-dev \
    python3-pip \
    python3-venv

ENV MELTANOENV /venv/meltano
RUN if [ "$meltano_version_filter" = "skip" ]; then exit 0; fi && \
    python -m venv $MELTANOENV && \
    $MELTANOENV/bin/pip3 install "meltano$meltano_version_filter" && \
    ln -s $MELTANOENV/bin/meltano /usr/bin/meltano && \
    meltano --version
RUN if [ "$meltano_version_filter" = "skip" ]; then exit 0; fi && \
    meltano --version && \
    meltano init sample-meltano-project && \
    cd sample-meltano-project && \
    meltano upgrade && \
    meltano discover all && \
    meltano --version

# Install DBT
ENV DBTENV /venv/dbt
RUN python3 -m venv $DBTENV && \
    $DBTENV/bin/pip3 install "dbt$dbt_version_filter" && \
    ln -s $DBTENV/bin/dbt /usr/bin/dbt && \
    dbt --version
RUN dbt init sample-dbt-project && \
    cd sample-dbt-project && \
    dbt --version

# Install dbt-spark
ENV DBTSPARKENV /venv/dbt-spark
RUN python3 -m venv $DBTSPARKENV && \
    $DBTSPARKENV/bin/pip3 install ${dbt_spark_source} && \
    ln -s $DBTSPARKENV/bin/dbt /usr/bin/dbt-spark && \
    dbt-spark --version
RUN dbt-spark init sample-dbtspark-project && \
    cd sample-dbtspark-project && \
    dbt-spark --version

# Install pipelinewise
ENV PIPELINEWISE_HOME /venv/pipelinewise
ENV PIPELINEWISEENV /venv/pipelinewise/.virtualenvs/pipelinewise
RUN cd /venv && \
    git clone https://github.com/transferwise/pipelinewise.git && \
    cd pipelinewise && ./install.sh --acceptlicenses && \
    ln -s $PIPELINEWISEENV/bin/pipelinewise /usr/bin/pipelinewise && \
    pipelinewise --version
RUN pipelinewise init --dir sample_pipelinewise_project --name sample_pipelinewise_project && \
    pipelinewise import --dir sample_pipelinewise_project

# Install tap-salesforce
RUN python3 -m venv /venv/tap-salesforce && \
    /venv/tap-salesforce/bin/pip3 install git+https://gitlab.com/meltano/tap-salesforce.git && \
    ln -s /venv/tap-salesforce/bin/tap-salesforce /usr/bin/tap-salesforce && \
    tap-salesforce --help

# Capture command history, allows recall if used with `-v ./.devcontainer/.bashhist:/root/.bash_history`
RUN mkdir -p /root/.bash_history && \
    echo "export PROMPT_COMMAND='history -a'" >> "/root/.bashrc" && \
    echo "export HISTFILE=/root/.bash_history/.bash_history" >> "/root/.bashrc"

RUN echo '#!/bin/bash \n\
    echo "Starting boostrap.sh script..." \n\
    source /venv/meltano/bin/activate \n\
    meltano --version || true \n\
    if [[ ! -d ".meltano" ]]; then \n\
    LOG_FILE=.meltano-install-log.txt \n\
    echo "Folder ''.meltano'' is missing. Beginning Meltano install as background process on `date`..." | tee -a $LOG_FILE \n\
    echo "Logging install progress to: $LOG_FILE" \n\
    echo "View progress with ''jobs -l'' or ''tail -f $LOG_FILE''" \n\
    nohup sh -c ''meltano upgrade && echo -e "Install complete on `date`\n\n"'' | tee -a $LOG_FILE & \n\
    fi \n\
    meltano --version || true \n\
    date \n\
    echo "Running meltano with provided command args: $@..." \n\
    $@ \n\
    ' > /projects/bootstrap.sh && \
    chmod 777 /projects/bootstrap.sh

# COPY bootstrap.sh $DBT_DIR/bootstrap.sh
# ENTRYPOINT ["$VENV/bin/meltano"]

ENTRYPOINT ["/projects/bootstrap.sh"]
# CMD ["meltano", "ui"]
CMD ["bash"]
