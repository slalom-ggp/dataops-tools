#!/bin/bash

# Echo this entire script to a logfile.txt
exec > >(tee -a $HOME/logfile.txt) 2>&1

DEFAULT_CMD="python3 bin/run.py"

if [[ ! -z "$DETECT_HOSTNAME" ]]; then  # Set env var in order to initialize hostname
    echo "Initializing hostname (needed for ECS)..."
    echo "Detecting 'eth1' interface..."
    DETECTED_IP=$(ifconfig -a | grep -A2 eth1 | grep inet | awk '{print $2}' | sed 's#/.*##g' | grep "\.")
    if [[ -z $DETECTED_IP ]]; then
        echo "Detecting 'eth0' interface ('eth1' not found)..."
        DETECTED_IP=$(ifconfig -a | grep -A2 eth0 | grep inet | awk '{print $2}' | sed 's#/.*##g' | grep "\." | head -1)
    fi
    DETECTED_HOSTNAME=$(hostname)
    echo -e "\n\nDETECTED_IP=$DETECTED_IP\nDETECTED_HOSTNAME=$DETECTED_HOSTNAME\n\n"
    # NOTE: newer OS versions use `ip` instead of `ifconfig`
    echo -e "Current file contents:\n $(cat /etc/hosts)"
    echo "$DETECTED_IP $DETECTED_HOSTNAME" >> /etc/hosts
    echo -e "\n\n\nUpdated file contents:\n $(cat /etc/hosts)"
fi

if [[ ! -z "$PROJECT_GIT_URL" ]]; then
    echo "Cloning project from git ($PROJECT_GIT_URL)..."
    git clone $PROJECT_GIT_URL project
    cd project
    if [[ ! -z "$PROJECT_COMMIT" ]]; then
        echo "Checking out the project commit: $PROJECT_COMMIT"
        git checkout $PROJECT_COMMIT
    elif [[ ! -z "$PROJECT_BRANCH" ]]; then
        echo "Checking out the project commit: $PROJECT_BRANCH"
        git checkout $PROJECT_BRANCH
    fi
fi

set -e  # Fail script on error
CMD="$@"  # Set command to whatever args were sent to the bootstrap script
if [[ ! -z "$CMD" ]]; then
    echo "Running CMD from bootstrap args: $CMD"
else
    echo "No command provided in bootstrap script. Using default command: $DEFAULT_CMD"
    CMD=$DEFAULT_CMD
fi

set +e  # Ignore errors (so we can clean up afterwards)
$CMD
RETURN_CODE=$?  # Capture the return code so we can print it
set -e  # Re-enable failure on error
echo -e "Bootstrap script completed.\nRETURN_CODE=$RETURN_CODE\nCMD=$CMD"

exit $RETURN_CODE  # Return the error code (zero if successful)
