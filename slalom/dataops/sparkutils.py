""" slalom.dataops.sparkutils module """

import datetime
import importlib.util
import time
import os
import sys

from pathlib import Path

import docker
import fire
import pyspark
from py4j.java_gateway import java_import
from pyspark import SparkContext, SparkConf
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    StructType,
    StructField,
    DateType,
    TimestampType,
    Row as SparkRow,
)
from pyspark.sql.functions import (
    unix_timestamp,
    from_unixtime,
    to_date,
    input_file_name,
    lit,
)

from slalom.dataops import io
from slalom.dataops import dockerutils
from slalom.dataops import jobs
from slalom.dataops.logs import (
    get_logger,
    logged,
    logged_block,
    _get_printable_context,
    bytes_to_string,
)
from slalom.dataops import pandasutils

logging = get_logger("slalom.dataops.sparkutils")

try:
    import pandas as pd
except Exception as ex:
    pd = None
    logging.warning(f"Could not load pandas library. Try 'pip install pandas'. {ex}")

ENV_VAR_SPARK_UDF_MODULE = "SPARK_UDF_MODULE"

_SERVING_SPARK_REQUESTS = "serving spark requests"
ENABLE_SQL_JDBC = bool(os.environ.get("ENABLE_SQL_JDBC", False))
METASTORE_TYPE = os.environ.get("METASTORE_TYPE", "Derby")
METASTORE_SERVER = os.environ.get("METASTORE_SERVER", None) or "localhost"
METASTORE_DB_USER = os.environ.get("METASTORE_DB_USER", None)
METASTORE_DB_PASSWORD = os.environ.get("METASTORE_DB_PASSWORD", None)
SUPPORT_CLUSTER_BY = False

DOCKER_SPARK_IMAGE = os.environ.get("DOCKER_SPARK_IMAGE", "slalomggp/dataops:latest-dev")
CONTAINER_ENDPOINT = "spark://localhost:7077"
SPARK_DRIVER_MEMORY = "4g"
SPARK_EXECUTOR_MEMORY = "4g"
SPARK_WAREHOUSE_DIR = os.environ.get("SPARK_WAREHOUSE_DIR", "/spark_warehouse/data")
SPARK_S3_PREFIX = "s3a://"
SPARK_LOG_LEVEL = os.environ.get(
    "SPARK_LOG_LEVEL", "ERROR"
)  # ALL, DEBUG, ERROR, FATAL, INFO, WARN
HADOOP_HOME = os.environ.get("HADOOP_HOME", "/usr/local/hdp")
# SPARK_HOME = os.environ.get("SPARK_HOME", None)
# SPARK_CLASS_PATH = os.path.join(os.environ["SPARK_HOME"], "jars/*")

SPARK_EXTRA_AWS_JARS = [
    # Hadoop 2.7.7:
    os.path.join(HADOOP_HOME, "share/hadoop/tools/lib/aws-java-sdk-1.7.4.jar"),
    os.path.join(HADOOP_HOME, "share/hadoop/tools/lib/hadoop-aws-2.7.7.jar")
    # # Hadoop 3.1.2:
    # os.path.join(HADOOP_HOME, "share/hadoop/tools/lib/aws-java-sdk-bundle-1.11.271.jar"),
    # os.path.join(HADOOP_HOME, "share/hadoop/tools/lib/hadoop-aws-3.1.2.jar")
    # os.path.join(HADOOP_HOME, "share/hadoop/tools/lib/aws-java-sdk-core-1.10.6.jar")
    # os.path.join(HADOOP_HOME, "share/hadoop/tools/lib/aws-java-sdk-kms-1.10.6.jar")
    # os.path.join(HADOOP_HOME, "share/hadoop/tools/lib/aws-java-sdk-s3-1.10.6"),
]


def _add_derby_metastore_config(hadoop_conf):
    """ Returns a new hadoop_conf dict with added metastore params """
    derby_log = "/home/data/derby.log"
    derby_home = "/home/data/derby_home"
    derby_hive_metastore_dir = "/home/data/hive_metastore_db"
    for folder in [SPARK_WAREHOUSE_DIR, derby_hive_metastore_dir]:
        io.create_folder(derby_home)
    derby_options = (
        f"-Dderby.stream.error.file={derby_log} -Dderby.system.home={derby_home}"
    )
    hadoop_conf.update(
        {
            "derby.system.home": derby_home,
            "derby.stream.error.file": derby_log,
            "driver-java-options": derby_options,
            "spark.driver.extraJavaOptions": derby_options,
            "spark.executor.extraJavaOptions": derby_options,
            "hive.metastore.warehouse.dir": f"file://{derby_hive_metastore_dir}",
            # "javax.jdo.option.ConnectionURL": "jdbc:derby:memory:databaseName=metastore_db;create=true",
            "javax.jdo.option.ConnectionURL": "jdbc:derby:;databaseName=/home/data/metastore_db;create=true",
            "javax.jdo.option.ConnectionDriverName": "org.apache.derby.jdbc.EmbeddedDriver",
        }
    )
    return hadoop_conf


def _add_mysql_metastore_config(hadoop_conf):
    """ Returns a new hadoop_conf dict with added metastore params """
    hadoop_conf.update(
        {
            "javax.jdo.option.ConnectionURL": (
                f"jdbc:mysql://{METASTORE_SERVER}/"
                "metastore_db?createDatabaseIfNotExist=true&useSSL=false"
            ),
            "javax.jdo.option.ConnectionDriverName": "com.mysql.jdbc.Driver",
            "javax.jdo.option.ConnectionUserName": "root",
            "javax.jdo.option.ConnectionPassword": "root",
        }
    )
    if METASTORE_DB_USER:
        hadoop_conf["javax.jdo.option.ConnectionUserName"] = METASTORE_DB_USER
    if METASTORE_DB_PASSWORD:
        hadoop_conf["javax.jdo.option.ConnectionPassword"] = METASTORE_DB_PASSWORD
    return hadoop_conf


def _add_aws_creds_config(hadoop_conf):
    """ Returns a new hadoop_conf dict with added metastore params """
    hadoop_conf.update(
        {
            "fs.s3.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
            "fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
            "fs.s3a.endpoint": (
                f"s3.{os.environ.get('AWS_DEFAULT_REGION', 'us-east-2')}.amazonaws.com"
            ),
            "spark.jars": ",".join(SPARK_EXTRA_AWS_JARS),
            "com.amazonaws.services.s3.enableV4": "true",
        }
    )
    os.environ["HADOOP_OPTS"] = (
        os.environ.get("HADOOP_OPTS", "")
        + " -Djava.net.preferIPv4Stack=true -Dcom.amazonaws.services.s3.enableV4=true"
    )
    try:
        key, secret, token = io.parse_aws_creds()
        io.set_aws_env_vars(key, secret, token)
        logging.info(
            f"Successfully loaded AWS creds for access key: ****************{key[-4:]}"
        )
        # TODO: Confirm that these settings are not needed (avoid leaks to logs)
        # if key:
        #     hadoop_conf["fs.s3a.access.key"] = key
        # if secret:
        #     hadoop_conf["fs.s3a.secret.key"] = secret
    except Exception as ex:
        logging.info(f"Could not load AWS creds ({ex})")
    return hadoop_conf


def _get_hadoop_conf():
    hadoop_conf = {
        "spark.driver.memory": SPARK_DRIVER_MEMORY,
        "spark.executor.memory": SPARK_EXECUTOR_MEMORY,
        "spark.jars.packages": "io.delta:delta-core_2.11:0.4.0",
        "spark.logConf": "true",
        "spark.sql.warehouse.dir": SPARK_WAREHOUSE_DIR,
        "spark.ui.showConsoleProgress": "false",  # suppress updates e.g. 'Stage 2=====>'
        "log4j.rootCategory": SPARK_LOG_LEVEL,
        "log4j.logger.org.apache.hive.service.server": SPARK_LOG_LEVEL,
        "log4j.logger.org.apache.spark.api.python.PythonGatewayServer": SPARK_LOG_LEVEL,
    }
    # Add Thrift JDBC Server settings
    hadoop_conf.update(
        {
            "spark.sql.hive.thriftServer.singleSession": "true",
            "hive.server2.thrift.port": 10000,
            "hive.server2.http.endpoint": "cliservice",
            "log4j.logger.org.apache.spark.sql.hive.thriftserver": SPARK_LOG_LEVEL,
        }
    )
    hadoop_conf = _add_aws_creds_config(hadoop_conf)
    if METASTORE_TYPE.upper() == "MYSQL":
        hadoop_conf = _add_mysql_metastore_config(hadoop_conf)
    else:
        hadoop_conf = _add_derby_metastore_config(hadoop_conf)
    return hadoop_conf


# GLOBALS

spark = None
sc = None
thrift = None
_spark_container = None


@logged("starting Spark container '{spark_image}' with args: with_jupyter={with_jupyter}")
def _init_spark_container(spark_image=DOCKER_SPARK_IMAGE, with_jupyter=False):
    global _spark_container

    if _spark_container:
        return _spark_container
    port_map = {
        "4040": "4040",  # App Web UI
        "7077": "7077",  # Standalone master driver
        "8080": "8080",  # Standalone-mode master Web UI
        "8081": "8081",  # Standalone-mode worker Web UI
        "8888": "8888",  # Jupyter Notebook Server
        "10000": "10000",  # Thrift JDBC port for SQL queries
        "18080": "18080",  # History Server Web UI
    }
    io.set_aws_env_vars()
    env = [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "BATCH_ID=SparkContainerTest",
        "ENABLE_SQL_JDBC=True",
        "METASTORE_TYPE=MySQL",
    ]
    if "AWS_ACCESS_KEY_ID" in os.environ:
        env.append(f"AWS_ACCESS_KEY_ID={os.environ['AWS_ACCESS_KEY_ID']}")
    if "AWS_SECRET_ACCESS_KEY" in os.environ:
        env.append(f"AWS_SECRET_ACCESS_KEY={os.environ['AWS_SECRET_ACCESS_KEY']}")
    docker_client = docker.from_env()  # WSL1
    # docker_client = docker.DockerClient(base_url="npipe:////./pipe/docker_wsl")  # WSL2
    try:
        dockerutils.pull(spark_image)
    except Exception as ex:
        logging.warning(f"Could not pull latest Spark image '{spark_image}'. {ex}")
    try:
        old_container = docker_client.containers.get("spark_server")
        if old_container:
            with logged_block("terminating previous 'spark_server' docker container"):
                old_container.stop()
                logging.info("Waiting for cleanup of old Spark container...")
                time.sleep(2)
    except Exception as _:
        pass
    spark_image_cmd = "sparkutils start_server"
    if with_jupyter:
        spark_image_cmd = f"{spark_image_cmd} --with_jupyter"
    _spark_container = docker_client.containers.run(
        image=spark_image,
        name="spark_server",
        command=spark_image_cmd,
        detach=True,
        auto_remove=True,
        ports=port_map,
        environment=env,
        # stream=True,
    )
    logging.info(
        f"Attempting to initialize Spark docker container "
        f"(status={_spark_container.status})..."
    )
    MAX_WAIT_TIME = int(60 * 5)
    start = time.time()
    for line in _spark_container.logs(stream=True, until=int(start + MAX_WAIT_TIME)):
        logging.info(f"SPARK CONTAINER LOG: {line.decode('utf-8').rstrip()}")
        # time.sleep(0.2)
        if _SERVING_SPARK_REQUESTS in line.decode("utf-8"):
            logging.info(
                f"Spark container reported success after "
                f"{int(time.time() - start)} seconds"
            )
            break
        elif time.time() > start + MAX_WAIT_TIME:
            logging.info(f"Max timeout wait exceeded ({MAX_WAIT_TIME} seconds)")
            break
    if _spark_container.status in ["running", "created"]:
        return _spark_container
    else:
        raise RuntimeError(
            "Spark docker container exited unexpectedly "
            f"(status={_spark_container.status})."
        )


def _destroy_spark_container():
    global _spark_container

    if _spark_container:
        _spark_container.stop()
        _spark_container = None


@logged(
    "initializing Spark with args: dockerized={dockerized}, with_jupyter={with_jupyter}"
)
def _init_spark(dockerized=False, with_jupyter=False, daemon=False):
    """Return an initialized spark object"""
    global spark, sc, thrift

    if dockerized:
        container = _init_spark_container(with_jupyter=with_jupyter)
        # context = SparkContext(conf=conf)
        os.environ["PYSPARK_PYTHON"] = sys.executable
        with logged_block("connecting to spark container"):
            spark = SparkSession.builder.master(CONTAINER_ENDPOINT).getOrCreate()
        spark.sparkContext.setLogLevel(SPARK_LOG_LEVEL)
        sc = spark.sparkContext
    elif daemon:
        cmd = f"{sys.executable} -m slalom.dataops.sparkutils start_server"
        wait_test = lambda line: _SERVING_SPARK_REQUESTS in line
        wait_max = 120  # Max wait in seconds
        if with_jupyter:
            cmd = f"{cmd} --with_jupyter"
        jobs.run_command(cmd, daemon=True, wait_test=wait_test, wait_max=wait_max)
    else:
        _init_local_spark()


def _init_local_spark():
    """Return an initialized local spark object"""
    global spark, sc, thrift

    # context = SparkContext(conf=conf)
    for folder in [SPARK_WAREHOUSE_DIR]:
        io.create_folder(folder)
    conf = SparkConf()
    hadoop_conf = _get_hadoop_conf()
    for fn in [conf.set]:
        # for fn in [conf.set, SparkContext.setSystemProperty, context.setSystemProperty]:
        for k, v in hadoop_conf.items():
            fn(k, v)
    os.environ["PYSPARK_PYTHON"] = sys.executable
    with logged_block("creating spark session"):
        spark = (
            SparkSession.builder.config(conf=conf)
            .master("local")
            .appName("Python Spark")
            .enableHiveSupport()
            .getOrCreate()
        )
        sc = spark.sparkContext
        # Set the property for the driver. Doesn't work using the same syntax
        # as the executor because the jvm has already been created.
        sc.setSystemProperty("com.amazonaws.services.s3.enableV4", "true")
    if not ENABLE_SQL_JDBC:
        logging.info(f"Skipping Thrift server launch (ENABLE_SQL_JDBC={ENABLE_SQL_JDBC})")
        thrift = None
    else:
        with logged_block("starting Thrift server"):
            java_import(sc._gateway.jvm, "")
            spark_hive = sc._gateway.jvm.org.apache.spark.sql.hive
            thrift_class = spark_hive.thriftserver.HiveThriftServer2
            thrift = thrift_class.startWithContext(spark._jwrapped)
        logging.info("Sleeping while waiting for Thrift Server...")
        time.sleep(1)
    spark.sparkContext.setLogLevel(SPARK_LOG_LEVEL)
    _print_conf_debug(sc)
    if ENV_VAR_SPARK_UDF_MODULE in os.environ:
        add_udf_module(os.environ.get(ENV_VAR_SPARK_UDF_MODULE))
    else:
        logging.info("Skipping loading UDFs (env variable not set)")
    for jar_path in SPARK_EXTRA_AWS_JARS:
        sc.addPyFile(jar_path)


@logged("importing from dynamic python file '{absolute_file_path}'")
def path_import(absolute_file_path):
    """implementation taken from https://docs.python.org/3/library/importlib.html#importing-a-source-file-directly"""
    module_name = os.path.basename(absolute_file_path)
    module_name = ".".join(module_name.split(".")[:-1])  # removes .py suffix
    spec = importlib.util.spec_from_file_location(module_name, absolute_file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@logged("loading UDFs from module directory '{module_dir}'")
def add_udf_module(module_dir=None):
    """
    Add a package from module_dir (or zip file) and register any udfs within the package
    The module must contain a '__init__.py' file and functions to be imported should be
    annotated using the @udf() decorator.
    # https://stackoverflow.com/questions/47558704/python-dynamic-import-methods-from-file
    """
    global sc
    from inspect import getmembers, isfunction

    # module_dir = module_dir or os.environ.get(ENV_VAR_SPARK_UDF_MODULE)
    module_dir = os.path.realpath(module_dir)
    # module_root = Path(module_dir).parent
    # module_name = os.path.basename(module_dir)
    # if module_root not in sys.path:
    #     sys.path.append(module_root)
    if not os.path.isdir(module_dir):
        raise ValueError(f"Folder '{module_dir}' does not exist.")
    for file in io.list_files(module_dir):
        if file.endswith(".py"):
            module = path_import(file)
            for member in getmembers(module):
                if isfunction(member[1]):
                    logging.info(f"Found module function: {member}")
                    func_name, func = member[0], member[1]
                    if func_name[:1] != "_" and func_name != "udf":
                        logging.info(f"Registering UDF '{func_name}':\n{func.__dict__}")
                        spark.udf.register(func_name, func)
                # else:
                #     logging.info(f"Found module entity: {member}")
    # sc.addPyFile(jar_path)


@logged("starting Jupyter notebooks server")
def start_jupyter(nb_directory="/home/jovyan/work", nb_token="qwerty123"):
    jupyter_run_command = (
        f"jupyter lab"
        f" --NotebookApp.notebook_dir='{nb_directory}'"
        f" --NotebookApp.token='{nb_token}'"
        f" --allow-root"
    )
    log_file = "jupyter_log.txt"
    jobs.run_command(jupyter_run_command, daemon=True, log_file_path=log_file)
    time.sleep(5)
    logging.info("\nJUPYTER_LOG:".join(io.get_text_file_contents(log_file).splitlines()))
    logging.info(
        "Jupyter notebooks server started at: https://localhost:8888/?token=qwerty123"
    )


def get_spark(dockerized=False):
    global spark

    if not spark:
        _init_spark(dockerized=dockerized)
    return spark


def _print_conf_debug(sc):
    """ Print all spark and hadoop config settings """
    logging.debug(
        "SparkSession 'spark' and SparkContext 'sc' initialized with settings:\n"
        f"{_get_printable_context(dict(sc._conf.getAll()))}"
    )


# Spark Helper Function:
@logged("creating table '{table_name}'", success_detail="{result.count():,.0f} rows")
def create_spark_sql_table(
    table_name,
    sql,
    print_row_count=True,
    print_n_rows=None,
    run_audit=True,
    schema_only=False,
):
    spark.sql(f"DROP TABLE IF EXISTS {table_name}")
    distribution_clause = ""
    for col in ["AccountId", "OpportunityId"]:
        if SUPPORT_CLUSTER_BY and not distribution_clause and col in sql:
            distribution_clause = "\n    DISTRIBUTE BY {col}"
    sql_command = f"""
    CREATE TABLE {table_name}
    USING PARQUET
    AS
    {sql}
    {distribution_clause}
    """
    spark.sql(sql_command)
    df = spark.sql(f"SELECT * FROM {table_name}")
    if print_n_rows:
        sample_spark_table(table_name, n=print_n_rows)
    if run_audit:
        audit_spark_table_keys(table_name)
    return df


def audit_spark_table_keys(table_name, key_col_suffix="Id", raise_error=False):
    df = spark.sql(f"SELECT * FROM {table_name}")
    key_cols = [c for c in df.columns if key_col_suffix in c]
    if not key_cols:
        key_cols.append(df.columns[0])
    cols = ",".join(
        [
            f"COUNT(DISTINCT {c}) AS {c}__values,\nCOUNT(*) - COUNT({c}) as {c}__null"
            for c in key_cols
        ]
    )
    sql = f"SELECT COUNT(*) AS __num_rows, {cols}\nFROM {table_name}"
    logging.info(f"Running '{table_name}' table audit...")
    result = spark.sql(sql).collect()[0]
    num_rows = result["__num_rows"]
    unique = []
    empty = []
    for col in key_cols:
        if result[col + "__null"] >= num_rows:
            empty.append(col)
        elif result[col + "__values"] >= num_rows - 1:
            unique.append(col)
    result_text = (
        f"Found unique column(s) [{','.join(unique) or '(none)'}] "
        f"and empty columns [{','.join(empty) or '(none)'}]. "
        f"Table profile: {result}"
    )
    if not unique:
        failure_msg = f"Audit failed for table '{table_name}'. {result_text}"
        if raise_error:
            raise RuntimeError(failure_msg)
        else:
            logging.warning(f"Table audit warning for '{table_name}'. {result_text}")
    elif len(empty):
        logging.warning(f"Table audit warning for '{table_name}'. {result_text}")
    else:
        logging.info(f"Table audit successful for '{table_name}'. {result_text}")


def sample_spark_table(table_name, n=1):
    df = spark.sql(f"SELECT * FROM {table_name} LIMIT {n}")
    sample_spark_df(df, n=n, name=table_name)


def sample_spark_df(df, n=1, name=None, log_fn=logging.debug):
    log_fn(
        f"Spark Dataframe column list: "
        f"{', '.join(['{dtype[0]} ({dtype[1]})' for dtype in df.dtypes])}"
        f"'{name or 'Dataframe'}' row sample:\n{df.limit(n).toPandas().head(n)}\n"
    )


def create_spark_table(
    df, table_name, print_n_rows=None, run_audit=False, schema_only=False
):
    start_time = time.time()
    if isinstance(df, pyspark.sql.DataFrame):
        logging.info(f"Creating spark table '{table_name}' from spark dataframe...")
        spark_df = df
    elif pd and isinstance(df, pd.DataFrame):
        # Coerce all values in string columns to string
        logging.debug("Coercing column types string prior to save...")
        for col in df.select_dtypes(["object"]):
            df[col] = df[col].astype("str")
        logging.debug("Converting pandas dataframe to spark dataframe prior to save...")
        spark_df = spark.createDataFrame(df)
        logging.info(f"Creating spark table '{table_name}' from pandas dataframe...")
    else:
        logging.info(
            f"Creating table '{table_name}' from unknown type '{type(df).__name__}"
        )
        spark_df = spark.createDataFrame(df, verifySchema=False)
    spark_df.write.saveAsTable(table_name, mode="overwrite")
    if print_n_rows:
        sample_spark_table(table_name, n=print_n_rows)
    if run_audit:
        audit_spark_table_keys(table_name)


def _verify_path(file_path):
    return file_path.replace(
        "s3://", SPARK_S3_PREFIX
    )  # .replace("propensity-to-buy", "propensity-to-buy-2")


@logged("loading spark table '{table_name}'")
def load_to_spark_table(
    table_name,
    file_path,
    entity_type=None,
    infer_schema=True,
    date_format=None,
    timestamp_format=None,
    filename_column="filename",
    df_cleanup_function=None,
    print_n_rows=None,
    clean_col_names=False,
    schema_only=False,
):
    start_time = time.time()
    file_path = _verify_path(file_path)

    if ".xlsx" in file_path.lower():
        if pd:
            logging.debug(
                f"Using pandas to load spark table '{table_name}' from '{file_path}'..."
            )
            df = pandasutils.get_pandas_df(file_path)
            create_spark_table(df, table_name, print_n_rows=print_n_rows)
        else:
            pandasutils._raise_if_missing_pandas()
    else:
        logging.debug(f"Loading spark table '{table_name}' from file '{file_path}'...")
        df = spark.read.csv(
            file_path,
            header=True,
            escape='"',
            quote='"',
            multiLine=True,
            inferSchema=True,
            enforceSchema=False,
            dateFormat=date_format,
            timestampFormat=timestamp_format,
            columnNameOfCorruptRecord="__READ_ERRORS",
        )
        if filename_column:
            df = df.withColumn(filename_column, input_file_name())
        if df_cleanup_function:
            df = df_cleanup_function(df)
        create_spark_table(
            df,
            table_name,
            print_n_rows=print_n_rows,
            run_audit=False,
            schema_only=schema_only,
        )


@logged("saving '{table_name}' to file")
def save_spark_table(
    table_name,
    file_path,
    entity_type=None,
    force_single_file=False,
    compression="gzip",
    schema_only=True,
    overwrite=True,
):
    start_time = time.time()
    file_path = _verify_path(file_path)
    df = spark.sql(f"SELECT * FROM {table_name}")
    if io.file_exists(os.path.join(file_path, "_SUCCESS")):
        if overwrite:
            logging.warning(
                "Saved table already exists and overwrite=True. Deleting older files."
            )
            for oldfile in io.list_files(file_path):
                io.delete_file(oldfile)
    if force_single_file:
        logging.debug(
            f"Saving spark table '{table_name}' to single file: '{file_path}'..."
        )
        df = df.coalesce(1)
    else:
        logging.debug(f"Saving spark table '{table_name}' to folder: '{file_path}'...")
    try:
        df.write.csv(  # SAFE
            file_path,
            mode="overwrite",
            header=True,
            compression=compression,
            quote='"',
            escape='"',
        )
    except Exception as ex:  # intermittent failures can be caused by eventual consistency
        logging.warning(
            f"Retrying S3 table save operation because the first attempt failed ({ex})"
        )
        time.sleep(20)  # Sleep to allow S3 to reach eventual consistency
        df.write.csv(  # SAFE
            file_path,
            mode="overwrite",
            header=True,
            compression=compression,
            quote='"',
            escape='"',
        )


def get_spark_table_as_pandas(table_name):
    if not pd:
        raise RuntimeError(
            "Could not execute get_pandas_from_spark_table(): Pandas library not loaded."
        )
    return spark.sql(f"SELECT * FROM {table_name}").toPandas()


# Create Dates table
def create_calendar_table(table_name, start_date, end_date):
    num_days = (end_date - start_date).days
    date_rows = [
        SparkRow(start_date + datetime.timedelta(days=n)) for n in range(0, num_days)
    ]
    df = spark.createDataFrame(date_rows)
    df = df.selectExpr("_1 AS calendar_date", "date_format(_1, 'yMMdd') AS YYYYMMDD")
    create_spark_table(df, table_name)


@logged(
    "starting spark server with args:"
    " dockerized={dockerized}, with_jupyter={with_jupyter}"
)
def start_server(dockerized: bool = None, with_jupyter: bool = True, daemon: bool = None):
    if dockerized is None:
        dockerized = (
            False
            if any(["SPARK_HOME" in os.environ, "HADOOP_CONF_DIR" in os.environ])
            else True
        )
    if daemon is None:
        daemon = dockerized
    if dockerized:
        container = _init_spark_container(with_jupyter=with_jupyter)
        if daemon:
            logging.info("Now serving spark requests via docker.")
        else:
            with logged_block("hosting spark container"):
                while True:
                    time.sleep(30)
    else:
        _init_spark(dockerized=False, with_jupyter=with_jupyter, daemon=daemon)
        logging.info(
            "Spark server started. "
            "Monitor via http://localhost:4040 or http://127.0.0.1:4040"
        )
        # if with_jupyter:
        #     start_jupyter()
        # else:
        #     logging.info("Skipping Jupyter notebooks server launch...")
        if not daemon:
            with logged_block(_SERVING_SPARK_REQUESTS):
                # NOTE: When run containerized, the above message triggers
                #       the host to stop echoing logs
                while True:
                    time.sleep(30)


def main():
    fire.Fire({"start_server": start_server, "start_jupyter": start_jupyter})


if __name__ == "__main__":
    main()
