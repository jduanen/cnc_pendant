#!/bin/bash
# Tool to forcably kill the grblPendant application
# 
PROG="grblPendant.py"
PROG_PID=$(ps -ef | grep ${PROG} | grep -v grep | awk '{print $2}')
if [[ "" !=  "${PROG_PID}" ]]; then
  echo "Killing ${PROG}: ${PROG_PID}"
  kill -9 ${PROG_PID}
fi
