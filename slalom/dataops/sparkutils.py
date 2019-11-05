""" Standard sparkutils module """

import datetime
import time
import os
import sys

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
from slalom.dataops.logs import (
    get_logger,
    logged,
    logged_block,
    _get_printable_context,
    bytes_to_string,
)


logging = get_logger("slalom.dataops.sparkutils")

try:
    import pandas as pd
except Exception as ex:
    pd = None
    logging.warning(f"Could not load pandas library. Try 'pip install pandas'. {ex}")


USE_THRIFT_SERVER = bool(os.environ.get("USE_THRIFT_SERVER", False))
METASTORE_TYPE = os.environ.get("METASTORE_TYPE", "Derby")
METASTORE_SERVER = os.environ.get("METASTORE_SERVER", None) or "localhost"
METASTORE_DB_USER = os.environ.get("METASTORE_DB_USER", None)
METASTORE_DB_PASSWORD = os.environ.get("METASTORE_DB_PASSWORD", None)
SUPPORT_CLUSTER_BY = False

# SPARK_IMAGE = "slalom/spark"
# SPARK_IMAGE_CMD = "jupyter lab"
SPARK_IMAGE = "local-dataops"
SPARK_IMAGE_CMD = "python -m slalom.dataops.sparkutils start_server"
CONTAINER_ENDPOINT = "spark://localhost:7077"
SPARK_DRIVER_MEMORY = "4g"
SPARK_EXECUTOR_MEMORY = "4g"
SPARK_WAREHOUSE_ROOT = "/tmp/spark-sql/warehouse"
SPARK_S3_PREFIX = "s3a://"
SPARK_LOG_LEVEL = "ERROR"  # ALL, DEBUG, ERROR, FATAL, INFO, WARN
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
    derby_log = "/tmp/derby.log"
    derby_home = "/tmp/derby"
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
        }
    )
    return hadoop_conf


def _add_mysql_metastore_config(hadoop_conf):
    """ Returns a new hadoop_conf dict with added metastore params """
    hadoop_conf.update(
        {
            "javax.jdo.option.ConnectionURL": (
                f"jdbc:mysql://{METASTORE_SERVER}/"
                "metastore_db?createDatabaseIfNotExist=true"
            ),
            "javax.jdo.option.ConnectionDriverName": "com.mysql.jdbc.Driver",
        }
    )
    if METASTORE_DB_USER:
        hadoop_conf["javax.jdo.option.ConnectionUserName"] = METASTORE_DB_USER
    if METASTORE_DB_PASSWORD:
        hadoop_conf["javax.jdo.option.ConnectionPassword"] = METASTORE_DB_PASSWORD
    return hadoop_conf


def _get_aws_creds(update_env_vars=True):
    """ Load AWS creds. Returns a 2-item duple or None. """

    def _parse_key_config(key_name, file_text):
        for line in file_text.splitlines():
            if key_name.lower() in line.lower() and "=" in line:
                return line.split("=")[1].strip()
        raise RuntimeError(f"Could not file {key_name} in file text:\n{file_text}")

    key, secret = None, None
    if "AWS_ACCESS_KEY_ID" in os.environ and "AWS_SECRET_ACCESS_KEY" in os.environ:
        logging.info("Found env vars: 'AWS_ACCESS_KEY_ID' and 'AWS_SECRET_ACCESS_KEY'")
        key = os.environ["AWS_ACCESS_KEY_ID"]
        secret = os.environ["AWS_SECRET_ACCESS_KEY"]
    else:
        logging.info(
            f"AWS_ACCESS_KEY_ID found: {'AWS_ACCESS_KEY_ID' in os.environ}, "
            f"AWS_SECRET_ACCESS_KEY found: {'AWS_SECRET_ACCESS_KEY' in os.environ}"
        )
        if io.file_exists("%USERPROFILE%/.aws/credentials"):
            cred_file = io.get_text_file_contents("%USERPROFILE%/.aws/credentials")
        elif io.file_exists("~/.aws/credentials"):
            cred_file = io.get_text_file_contents("~/.aws/credentials")
        else:
            raise RuntimeError("Could not find AWS creds in file or env variables.")
        key = _parse_key_config("AWS_ACCESS_KEY_ID", cred_file)
        secret = _parse_key_config("AWS_SECRET_ACCESS_KEY", cred_file)
        if update_env_vars:
            os.environ["AWS_ACCESS_KEY_ID"] = key
            os.environ["AWS_SECRET_ACCESS_KEY"] = secret
    return key, secret


def _add_aws_creds_config(hadoop_conf):
    """ Returns a new hadoop_conf dict with added metastore params """
    key, secret = _get_aws_creds()
    hadoop_conf = {
        "fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
        "fs.s3a.access.key": key,
        "fs.s3a.secret.key": secret,
        "fs.s3a.endpoint": f"s3.{os.environ.get('AWS_DEFAULT_REGION', 'us-east-2')}.amazonaws.com",
        "spark.jars": ",".join(SPARK_EXTRA_AWS_JARS),
        "com.amazonaws.services.s3.enableV4": "true",
    }
    os.environ["HADOOP_OPTS"] = (
        os.environ.get("HADOOP_OPTS", "")
        + " -Djava.net.preferIPv4Stack=true -Dcom.amazonaws.services.s3.enableV4=true"
    )
    return hadoop_conf


def _get_hadoop_conf():
    hadoop_conf = {
        "spark.executor.memory": SPARK_EXECUTOR_MEMORY,
        "spark.driver.memory": SPARK_DRIVER_MEMORY,
        "spark.sql.warehouse.dir": SPARK_WAREHOUSE_ROOT,
        "spark.logConf": "true",
        # suppress printing stage updates e.g. 'Stage 2=====>':
        "spark.ui.showConsoleProgress": "false",
        "spark.sql.hive.thriftServer.singleSession": "true",
        "log4j.logger.org.apache.spark.sql.hive.thriftserver": "DEBUG",
        "log4j.logger.org.apache.hive.service.server": "INFO",
    }
    hadoop_conf = _add_aws_creds_config(hadoop_conf)
    if METASTORE_TYPE.upper() == "MYSQL":
        hadoop_conf = _add_mysql_metastore_config(hadoop_conf)
    else:
        hadoop_conf = _add_derby_metastore_config(hadoop_conf)
    return hadoop_conf


spark = None
sc = None
thrift = None
_spark_container = None


@logged("starting spark container '{spark_image}'")
def _init_spark_container(spark_image=SPARK_IMAGE):
    global _spark_container

    if _spark_container:
        return _spark_container
    port_map = {
        "4040": "4040",  # App Web UI
        "7077": "7077",  # Standalone master driver
        "8080": "8080",  # Standalone-mode master Web UI
        "8081": "8081",  # Standalone-mode worker Web UI
        "10000": "10000",  # Thrift JDBC port for SQL queries
        "18080": "18080",  # History Server Web UI
    }
    _get_aws_creds(update_env_vars=True)
    env = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "BATCH_ID=SparkContainerTest"]
    if "AWS_ACCESS_KEY_ID" in os.environ:
        env.append(f"AWS_ACCESS_KEY_ID={os.environ['AWS_ACCESS_KEY_ID']}")
    if "AWS_SECRET_ACCESS_KEY" in os.environ:
        env.append(f"AWS_SECRET_ACCESS_KEY={os.environ['AWS_SECRET_ACCESS_KEY']}")
    docker_client = docker.from_env()  # WSL1
    # docker_client = docker.DockerClient(base_url="npipe:////./pipe/docker_wsl")  # WSL2
    try:
        old_container = docker_client.containers.get("spark_server")
        old_container.stop()
    except Exception as _:
        pass
    _spark_container = docker_client.containers.run(
        image=spark_image,
        name="spark_server",
        command=SPARK_IMAGE_CMD,
        detach=True,
        auto_remove=True,
        ports=port_map,
        environment=env,
        # stream=True,
    )
    start = time.time()
    for line in _spark_container.logs(stream=True):
        logging.info(line)
        time.sleep(0.5)
        if time.time() > start + 30:
            logging.info("Max timeout wait exceeded (30 seconds)")
            break
    return _spark_container


def _destroy_spark_container():
    global _spark_container

    if _spark_container:
        _spark_container.stop()
        _spark_container = None


@logged("initializing spark")
def _init_spark(dockerized=False):
    """ Return an initialized spark object """
    global spark, sc, thrift

    conf = SparkConf()
    hadoop_conf = _get_hadoop_conf()
    for fn in [conf.set]:
        # for fn in [conf.set, SparkContext.setSystemProperty, context.setSystemProperty]:
        for k, v in hadoop_conf.items():
            fn(k, v)
    if dockerized:
        container = _init_spark_container()
        # context = SparkContext(conf=conf)
        os.environ["PYSPARK_PYTHON"] = sys.executable
        with logged_block("connecting to spark container"):
            spark = (
                SparkSession.builder.config(conf=conf)
                .master(CONTAINER_ENDPOINT)
                .getOrCreate()
            )
    else:
        # context = SparkContext(conf=conf)
        hadoop_conf = _get_hadoop_conf()
        os.environ["PYSPARK_PYTHON"] = sys.executable
        with logged_block("creating spark session"):
            spark = (
                SparkSession.builder.config(conf=conf)
                .master("local")
                .appName("Python Spark")
                .enableHiveSupport()
                .getOrCreate()
            )
    spark.sparkContext.setLogLevel(SPARK_LOG_LEVEL)
    sc = spark.sparkContext
    _print_conf_debug(sc)
    for jar_path in SPARK_EXTRA_AWS_JARS:
        sc.addPyFile(jar_path)
    if USE_THRIFT_SERVER:
        with logged_block("starting Thrift server"):
            java_import(sc._gateway.jvm, "")
            spark_hive = sc._gateway.jvm.org.apache.spark.sql.hive
            thrift_class = spark_hive.thriftserver.HiveThriftServer2
            thrift = thrift_class.startWithContext(spark._jwrapped)
    else:
        thrift = None


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
        logging.debug(
            f"Using pandas to load spark table '{table_name}' from file '{file_path}'..."
        )
        df = get_pandas_df(file_path)
        create_spark_table(df, table_name, print_n_rows=print_n_rows)
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
        logging.warn(
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


# Create Dates table
def create_calendar_table(table_name, start_date, end_date):
    num_days = (end_date - start_date).days
    date_rows = [
        SparkRow(start_date + datetime.timedelta(days=n)) for n in range(0, num_days)
    ]
    df = spark.createDataFrame(date_rows)
    df = df.selectExpr("_1 AS calendar_date", "date_format(_1, 'yMMdd') AS YYYYMMDD")
    create_spark_table(df, table_name)


# Pandas functions
def pandas_read_csv_dir(csv_dir, usecols=None, dtype=None):
    if not pd:
        raise RuntimeError(
            "Could not execute pandas_read_csv_dir(): Pandas library was not loaded."
        )
    df_list = []
    for s3_path in io.list_s3_files(csv_dir):
        if "_SUCCESS" not in s3_path:
            if io.USE_SCRATCH_DIR:
                scratch_dir = io.get_scratch_dir()
                filename = os.path.basename(s3_path)
                csv_path = os.path.join(scratch_dir, filename)
                if os.path.exists(csv_path):
                    logging.info(
                        f"Skipping download of '{s3_path}'. File exists as: '{csv_path}' "
                        "(If you do not want to use this file, please delete "
                        "the file or unset the USE_SCRATCH_DIR environment variable.)"
                    )
                else:
                    logging.info(
                        f"Downloading S3 file '{s3_path}' to scratch dir: '{csv_path}'"
                    )
                io.download_s3_file(s3_path, csv_path)
            else:
                logging.info(f"Reading from S3 file: {s3_path}")
                csv_path = s3_path
            df = pd.read_csv(
                csv_path, index_col=None, header=0, usecols=usecols, dtype=dtype
            )
            df_list.append(df)
    logging.info(f"Concatenating datasets from: {csv_dir}")
    ret_val = pd.concat(df_list, axis=0, ignore_index=True)
    logging.info("Dataset concatenation was successful.")
    return ret_val


def get_pandas_from_spark_table(table_name):
    return spark.sql(f"SELECT * FROM {table_name}").toPandas()


def get_pandas_df(source_path, usecols=None):
    if ".xlsx" in source_path.lower():
        df = pandas_read_excel_sheet(source_path, usecols=usecols)
    else:
        try:
            df = pd.read_csv(source_path, low_memory=False, usecols=usecols)
        except Exception as ex:
            if "Error tokenizing data. C error" in str(ex):
                logging.warning(
                    f"Failed read_csv() using default 'c' engine. "
                    f"Retrying with engine='python'...\n{ex}"
                )
                df = pd.read_csv(source_path, usecols=usecols, engine="python")
            else:
                raise ex
    return df


def pandas_read_excel_sheet(sheet_path, usecols=None):
    """
    Expects path in form of '/path/to/file.xlsx/#sheet name'
    S3 paths are excepted.
    """
    filepath, sheetname = sheet_path.split("/#")
    df = pd.read_excel(filepath, sheetname=sheetname, usecols=usecols)
    return df


def print_pandas_mem_usage(
    df: pd.DataFrame, df_name, print_fn=logging.info, min_col_size_mb=500
):
    col_mem_usage = df.memory_usage(index=True, deep=True).sort_values(ascending=False)
    ttl_mem_usage = col_mem_usage.sum()
    col_mem_usage = col_mem_usage.nlargest(n=5)
    col_mem_usage = col_mem_usage[col_mem_usage > min_col_size_mb * 1024 * 1024]
    col_mem_usage = col_mem_usage.apply(bytes_to_string)
    msg = f"Dataframe '{df_name}' mem usage: {bytes_to_string(ttl_mem_usage)}"
    if col_mem_usage.size:
        col_usage_str = ", ".join(
            [
                f"{col}({'Index' if col == 'Index' else df[col].dtype}):{size}"
                for col, size in col_mem_usage.iteritems()
            ]
        )
        msg += f". Largest columns (over {min_col_size_mb}MB): {col_usage_str}"
    print_fn(msg)
    return msg


def start_server(dockerized=False):
    _init_spark(dockerized=dockerized)
    logging.info(
        "Spark server started. "
        "Monitor via http://localhost:4040 or http://127.0.0.1:4040"
    )
    with logged_block("serving spark requests"):
        while True:
            time.sleep(30)


def main():
    fire.Fire()


if __name__ == "__main__":
    main()
