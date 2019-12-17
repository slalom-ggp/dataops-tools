ARG source_image=slalomggp/dbt:latest-dev

FROM ${source_image}

ENV ENABLE_SQL_JDBC true
ENV METASTORE_TYPE MySQL
# e.g. ['MySQL', 'derby']

COPY . /home/dataops-tools
COPY bootstrap.sh /home/bootstrap.sh

WORKDIR /home/dataops-tools
RUN python3 setup.py install
RUN mkdir -p /home/jovyan/work/samples
WORKDIR /home/jovyan/work/samples
RUN curl https://gist.githubusercontent.com/aaronsteers/f4c072058a3317ee3904f713b1e4b6cb/raw/183e666c3c9b1818e092c97161fef9723dc5bbe9/AIDungeon.ipynb > AIDungeon.ipynb
# RUN curl https://raw.githubusercontent.com/AIDungeon/AIDungeon/develop/AIDungeon_2.ipynb > AIDungeon.ipynb

WORKDIR /home
ENTRYPOINT [ "bash", "/home/bootstrap.sh" ]
