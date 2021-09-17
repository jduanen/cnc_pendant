#!/bin/bash
#python -c "exec(\"import grbl\nif ${#} > 1: print(grbl.ERROR_CODES[${1}][1])\")"
NUM=${1:-0}
python -c "exec(\"from grbl import ERROR_CODES\nfrom pprint import pprint\nif int($#): print(ERROR_CODES[${NUM}][1])\nelse: pprint([d[1] for d in ERROR_CODES if d])\")"
