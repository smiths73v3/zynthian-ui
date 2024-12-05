#!/bin/bash

# Check if RBPI_VERSION_NUMBER is set
if [ -z "$RBPI_VERSION_NUMBER" ]
then
  echo "Error: RBPI_VERSION_NUMBER is not set."
  exit 0
fi

# Check if RBPI_VERSION_NUMBER equals 5
if [ "$RBPI_VERSION_NUMBER" -ne 5 ]
then
  echo "Not installing zynaudio8x for < RPi5"
  exit 0
fi

# Check if new kernel installed
if [ -f /tmp/kernel_ver ]
then
  KERNEL=`cat /tmp/kernel_ver`
else
  KERNEL=`uname -r`
fi

echo "Installing zynaudio8x"

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

pushd $DIR
	make KERNEL=$KERNEL && make install
	success=$?
popd
exit $success

