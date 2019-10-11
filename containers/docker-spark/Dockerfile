FROM jupyter/all-spark-notebook:latest
# based on Ubuntu 18.04 (as of 9/25/2019)
# https://hub.docker.com/r/jupyter/all-spark-notebook
# https://jupyter-docker-stacks.readthedocs.io/en/latest/using/running.html

ENV LIVY_VERSION 0.6.0
ENV NB_UID 1000
ENV NB_GID 100
ENV CHOWN_HOME yes
ENV CHOWN_HOME_OPTS '-R'
ENV GEN_CERT yes

ENV HADOOP_VERSION 2.7.7
ENV HADOOP_HOME /usr/local/hdp
ENV SPARK_HOME /usr/local/spark
### Spark installed by parent image
ENV HADOOP_CONF_DIR /usr/local/spark/conf
### Using the spark env instead of the hadoop directory

ENV PYTHONUNBUFFERED 1
ENV HOME /home/jovyan
WORKDIR /home/jovyan

USER root

RUN apt-get update && \
    apt-get install -y \
    libcurl4-openssl-dev \
    libmysql-java \
    libsasl2-dev \
    libssl-dev \
    libxml2-dev \
    openssh-client \
    mysql-server \
    net-tools \
    r-base

# Workaround for BitBucket security:
# https://community.atlassian.com/t5/Bitbucket-articles/Changes-to-make-your-containers-more-secure-on-Bitbucket/ba-p/998464#U1022556
RUN mkdir -p /usr/local/src
RUN export PYTHONPATH=$PYTHONPATH:/usr/local/src

RUN jupyter nbextension enable --py --sys-prefix widgetsnbextension
ENV PIP_INSTALL_PATH /opt/conda/lib/python3.7/site-packages

USER $NB_UID

# # Install python dependencies
# RUN export PYTHONPATH=$PYTHONPATH:/usr/local/src
RUN pip install --upgrade \
    autocorrect \
    dbt \
    dbt-spark \
    gensim \
    joblib \
    boto3 \
    fire \
    junit-xml \
    matplotlib \
    nltk \
    pyhive[hive] \
    s3fs \
    scipy \
    sklearn \
    statsmodels>=0.10.0rc2 \
    tqdm \
    xmlrunner
# RE: scipi::statsmodels version conflict: https://github.com/statsmodels/statsmodels/issues/5747#issuecomment-495683485

# Install R packages
ENV R_PACKAGES \
    \"codetools\", \
    \"xml2\", \
    \"stringi\", \
    \"tokenizers\", \
    \"aws.s3\", \
    \"base64enc\", \
    \"curl\", \
    \"dplyr\", \
    \"openssl\", \
    \"digest\", \
    \"fuzzyjoin\", \
    \"httr\", \
    \"openxlsx\", \
    \"plyr\", \
    \"Rcpp\", \
    \"readxl\", \
    \"scales\", \
    \"splitstackshape\", \
    \"stringdist\", \
    \"stringr\", \
    \"tidytext\", \
    \"data.table\"

RUN R_PACKAGES=$(echo $R_PACKAGES | tr -d '\\040\\011\\012\\015') && \
    echo "R_PACKAGES = c($R_PACKAGES); print(paste(\"List of missing/failed packages:\", paste(R_PACKAGES[!(R_PACKAGES %in% installed.packages(lib.loc=\"/opt/conda/lib/R/library\")[,\"Package\"])], sep=\",\")))" | R --no-save

RUN R_PACKAGES=$(echo $R_PACKAGES | tr -d '\\040\\011\\012\\015') && \
    echo -e "Installing Packages: $R_PACKAGES" && \
    echo "install.packages(c($R_PACKAGES), \"/opt/conda/lib/R/library\", repos=\"https://cran.rstudio.com\")" | R --no-save

RUN R_PACKAGES=$(echo $R_PACKAGES | tr -d '\\040\\011\\012\\015') && \
    echo "R_PACKAGES = c($R_PACKAGES); print(paste(\"List of missing/failed packages:\", paste(R_PACKAGES[!(R_PACKAGES %in% installed.packages(lib.loc=\"/opt/conda/lib/R/library\")[,\"Package\"])], sep=\",\")))" | R --no-save

USER root
# Install sparkmagics
RUN pip install sparkmagic && \
    chmod +775 -R $PIP_INSTALL_PATH/sparkmagic && \
    ls -la $PIP_INSTALL_PATH/sparkmagic/kernels
RUN jupyter-kernelspec install $PIP_INSTALL_PATH/sparkmagic/kernels/sparkkernel
RUN jupyter serverextension enable --py sparkmagic


#Install Hadoop, import needed hadoop libraries (AWS & S3)
RUN cd /usr/local && \
    curl -o hadoop-$HADOOP_VERSION.tar.gz https://apache.claz.org/hadoop/common/hadoop-$HADOOP_VERSION/hadoop-$HADOOP_VERSION.tar.gz && \
    tar -xzf hadoop-$HADOOP_VERSION.tar.gz && \
    mv hadoop-$HADOOP_VERSION $HADOOP_HOME && \
    chown -R root:root $HADOOP_HOME && \
    chmod -R 777 $HADOOP_HOME && \
    rm hadoop-$HADOOP_VERSION.tar.gz
RUN echo -e "HADOOP_HOME=$HADOOP_HOME\nSPARK_HOME=$SPARK_HOME" && \
    find $HADOOP_HOME/share/hadoop/tools/lib/ -name "*aws*.jar" && \
    cp `find $HADOOP_HOME/share/hadoop/tools/lib/ -name "*aws*.jar"` $SPARK_HOME/jars/ && \
    find $SPARK_HOME/jars -name "*aws*.jar" -print

#Copy mysql jdbc driver into spark classpath
RUN cp `find /usr/share/java/ -name "*mysql-connector-java*.jar"` $SPARK_HOME/jars/ && \
    find $SPARK_HOME/jars -name "*mysql-connector-java*.jar" -print

#Docker in docker
RUN apt-get update -qq && apt-get install -qqy \
    apt-transport-https \
    ca-certificates \
    lxc \
    iptables

# Install Docker from Docker Inc. repositories.
RUN curl -sSL https://get.docker.com/ | sh

# Install livy REST endpoint
ENV LIVY_HOME /usr/local/livy
RUN ZIP_NAME=apache-livy-${LIVY_VERSION}-incubating-bin.zip && \
    wget https://mirror.olnevhost.net/pub/apache/incubator/livy/${LIVY_VERSION}-incubating/$ZIP_NAME
RUN unzip apache-livy-${LIVY_VERSION}-incubating-bin.zip && \
    mv apache-livy-${LIVY_VERSION}-incubating-bin $LIVY_HOME && \
    cd $LIVY_HOME && \
    echo "livy.spark.master = local[*]" > $LIVY_HOME/conf/livy.conf && \
    mv $LIVY_HOME/conf/log4j.properties.template $LIVY_HOME/conf/log4j.properties && \
    ls -la $LIVY_HOME && ls -la $LIVY_HOME/conf && \
    mkdir -p /usr/local/livy/logs

RUN pip install docker

RUN mkdir /$HOME/scratch

USER $NB_UID

RUN pip install --upgrade \
    pyarrow \
    sk-dist

USER root

COPY bootstrap.sh $HOME/bin/
RUN chmod -R 777 $HOME/bin/*

# COPY project $HOME/project
# RUN chmod -R 777 $HOME/project/*
# RUN cd $HOME/src && python setup.py install

# RUN mv $HADOOP_CONF_DIR/hive-site.xml $HADOOP_CONF_DIR/hive-site.xml.bak
# COPY conf/hive-site.xml $HADOOP_CONF_DIR/hive-site.xml
# COPY conf/my.cnf $HOME/my.cnf

# USER $NB_UID

USER root
