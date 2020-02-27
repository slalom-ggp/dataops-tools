ARG source_image=slalomggp/dbt:latest-dev

FROM ${source_image}

ENV ENABLE_SQL_JDBC true
ENV METASTORE_TYPE MySQL
ENV SPARK_WAREHOUSE_ROOT /spark_warehouse
ENV SPARK_WAREHOUSE_DIR /spark_warehouse/data
ENV SPARK_METASTORE_DIR /spark_warehouse/metastore

# e.g. ['MySQL', 'derby']

RUN pip install --upgrade pip

RUN mkdir -p /home/jovyan/work/samples
WORKDIR /home/jovyan/work/samples
RUN curl https://gist.githubusercontent.com/aaronsteers/f4c072058a3317ee3904f713b1e4b6cb/raw/183e666c3c9b1818e092c97161fef9723dc5bbe9/AIDungeon.ipynb > AIDungeon.ipynb
# RUN curl https://raw.githubusercontent.com/AIDungeon/AIDungeon/develop/AIDungeon_2.ipynb > AIDungeon.ipynb

COPY . /home/dataops-tools
ENV SPARK_UDF_MODULE /home/dataops-tools/slalom/tests/resources/spark_udf_tests/udfs

WORKDIR /home/dataops-tools
RUN python3 setup.py install

RUN mkdir -p ${SPARK_WAREHOUSE_ROOT} && \
    mkdir -p ${SPARK_WAREHOUSE_DIR} && \
    cd ${SPARK_WAREHOUSE_ROOT} && \
    mv /var/lib/mysql metastore && \
    ls -la && \
    echo "----" && \
    cd /var/lib && \
    ln -s ${SPARK_METASTORE_DIR} mysql && \
    pwd && ls -la /var/lib/mysql && \
    chown --no-dereference mysql:mysql /var/lib/mysql && \
    chmod 750 /var/lib/mysql

WORKDIR /home
COPY ./containers/docker-dataops/bootstrap.sh /home/bootstrap.sh
ENTRYPOINT [ "bash", "/home/bootstrap.sh" ]
