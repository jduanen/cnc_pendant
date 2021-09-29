#!/bin/bash
# Tool to force grblPendant application to reload the macro definitions file
# 
PROG="grblPendant.py"
PROG_PID=$(ps -ef | grep ${PROG} | grep -v grep | awk '{print $2}')
#kill -s USR1 $(ps -ef | grep ${PROG} | grep -v grep | awk '{print $2}')
if [[ "" !=  "${PROG_PID}" ]]; then
  echo "Reloading Macros for ${PROG}: ${PROG_PID}"
  kill -s USR1 ${PROG_PID}
fi
