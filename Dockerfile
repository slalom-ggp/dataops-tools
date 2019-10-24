ARG source_image=slalomggp/spark-ds
ARG source_tag=latest-dev

FROM ${source_image}:${source_tag}


COPY slalom /home/slalom
WORKDIR /home
COPY bootstrap.sh /home/bootstrap.sh

ENTRYPOINT [ "bash", "/home/bootstrap.sh" ]
