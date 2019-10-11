#!/bin/bash

# Echo this entire script to a logfile.txt
exec > >(tee -a $HOME/logfile.txt) 2>&1

ifconfig # prints full IP info
echo "Detecting 'eth1' interface..."
DETECTED_IP=$(ifconfig -a | grep -A2 eth1 | grep inet | awk '{print $2}' | sed 's#/.*##g' | grep "\.")
if [[ -z $DETECTED_IP ]]; then
    echo "Detecting 'eth0' interface ('eth1' not found)..."
    DETECTED_IP=$(ifconfig -a | grep -A2 eth0 | grep inet | awk '{print $2}' | sed 's#/.*##g' | grep "\." | head -1)
fi
DETECTED_HOSTNAME=$(hostname)
echo -e "\n\nDETECTED_IP=$DETECTED_IP\nDETECTED_HOSTNAME=$DETECTED_HOSTNAME\n\n"
# Note: newer OS versions us `ip` instead of `ifconfig`
echo -e "Current file contents:\n $(cat /etc/hosts)"
echo "$DETECTED_IP $DETECTED_HOSTNAME" >> /etc/hosts
echo -e "\n\n\nUpdated file contents:\n $(cat /etc/hosts)"

CMD="$@"
if [[ ! -z "$CMD" ]]; then
    echo "Running CMD from bootstrap args: $CMD"
else
    CMD="python3 bin/run.py"
    echo "No command provided in bootstrap script. Running default: $CMD"
fi

set +e
$CMD
RETURN_CODE=$?
set -e
echo -e "Bootstrap script completed.\nRETURN_CODE=$RETURN_CODE\nCMD=$CMD"

exit $RETURN_CODE
