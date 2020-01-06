#!/bin/bash

# Echo this entire script to a logfile.txt
exec > >(tee -a $HOME/logfile.txt) 2>&1

DEFAULT_CMD="bash"

start_mysql()
{
    echo "Starting MySQL server as metastore (service mysql start)..."
    service mysql start
    if [[ ! -f "/var/lib/mysql/mysql-init.sql" ]]; then
        echo "Creating MySQL config script (/var/lib/mysql/mysql-init.sql)..."
        echo "SET PASSWORD FOR 'root'@'localhost' = PASSWORD('root');\n" > /var/lib/mysql/mysql-init.sql
        echo "USE mysql;" >> /var/lib/mysql/mysql-init.sql
        echo "UPDATE user SET authentication_string=PASSWORD('root') WHERE user='root';" >> /var/lib/mysql/mysql-init.sql
        echo "UPDATE user SET plugin='mysql_native_password' WHERE user='root';" >> /var/lib/mysql/mysql-init.sql
        echo "SET PASSWORD FOR 'root'@'localhost' = PASSWORD('root');\n" >> /var/lib/mysql/mysql-init.sql
        echo "FLUSH privileges;" >> /var/lib/mysql/mysql-init.sql
        # echo "MySQL Config File:"
        # cat /var/lib/mysql/mysql-init.sql
        echo "Running MySQL init script (/var/lib/mysql/mysql-init.sql)..."
        cat /var/lib/mysql/mysql-init.sql | mysql -uroot mysql
    fi
    echo "MySQL process ID is $(cat /var/run/mysqld/mysqld.pid)"
}

start_spark()
{
    mkdir -p $SPARK_WAREHOUSE_DIR
    python3 -m slalom.dataops.sparkutils start_server --daemon
}

set -e  # Fail script on error
CMD="$@"  # Set command to whatever args were sent to the bootstrap script
if [[ -z "$CMD" ]]; then
    echo "No command provided in bootstrap script. Using default command: $DEFAULT_CMD"
    CMD=$DEFAULT_CMD
elif [[ "$1" == "dbt-spark" ]]; then
    shift;
    CMD="dbt-spark $@";
    echo "Parsed DBT-Spark command: $CMD";
    start_mysql;
    start_spark;
    echo "Running DBT-Spark command: $CMD"
else
    echo "Attempting to parse and direct '$1' command '$CMD'..."
    if [[ "$1" == "docker" ]]; then  # alias for dockerutils
        MODULE_NAME="dockerutils"
        shift;
    elif [[ "$1" == "spark" ]]; then  # alias for sparkutils
        MODULE_NAME="sparkutils"
        shift;
    else
        MODULE_NAME=$1
        shift;
    fi
    if [[ "$MODULE_NAME" == "sparkutils" && "$METASTORE_TYPE" == "MySQL" ]]; then
        start_mysql;
    fi

    CMD="python3 -m slalom.dataops.$MODULE_NAME $@"
    echo "Running CMD from bootstrap args: $CMD"
fi

set +e  # Ignore errors (so we can clean up afterwards)
$CMD
RETURN_CODE=$?  # Capture the return code so we can print it
set -e  # Re-enable failure on error
echo -e "Bootstrap script completed.\nRETURN_CODE=$RETURN_CODE\nCMD=$CMD"

exit $RETURN_CODE  # Return the error code (zero if successful)
