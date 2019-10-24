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
    if [[ "$1" -eq "docker" ]]; then  # alias for dockerutils
        MODULE_NAME="dockerutils"
        shift;
    elif [[ "$1" -eq "spark" ]]; then  # alias for sparkutils
        MODULE_NAME="sparkutils"
        shift;
    else
        MODULE_NAME=$1
        shift;
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
