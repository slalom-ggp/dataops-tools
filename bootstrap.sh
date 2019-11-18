#!/bin/bash

# Echo this entire script to a logfile.txt
exec > >(tee -a $HOME/logfile.txt) 2>&1

DEFAULT_CMD="bash"

set -e  # Fail script on error
CMD="$@"  # Set command to whatever args were sent to the bootstrap script
if [[ -z "$CMD" ]]; then
    echo "No command provided in bootstrap script. Using default command: $DEFAULT_CMD"
    CMD=$DEFAULT_CMD
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
        echo "Starting MySQL server as metastore..."
        # ps -a | grep mysql
        echo "MySQL process ID is $(cat /var/run/mysqld/mysqld.pid)"
        # sudo kill $(cat /var/run/mysqld/mysqld.pid)

        echo "SET PASSWORD FOR 'root'@'localhost' = PASSWORD('root');\n" > /home/mysql-init.sql
        echo "USE mysql;" >> /home/mysql-init.sql
        echo "UPDATE user SET authentication_string=PASSWORD('root') WHERE user='root';" >> /home/mysql-init.sql
        echo "UPDATE user SET plugin='mysql_native_password' WHERE user='root';" >> /home/mysql-init.sql
        echo "SET PASSWORD FOR 'root'@'localhost' = PASSWORD('root');\n" >> /home/mysql-init.sql
        echo "FLUSH privileges;" >> /home/mysql-init.sql
        # echo "MySQL Config File:"
        # cat /home/mysql-init.sql

        service mysql start &
        echo "Sleeping 10 seconds..."
        sleep 10
        echo "MySQL process ID is $(cat /var/run/mysqld/mysqld.pid)"
        cat /home/mysql-init.sql | mysql -uroot mysql
        echo "MySQL process ID is $(cat /var/run/mysqld/mysqld.pid)"
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
