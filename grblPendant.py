#!/usr/bin/env python3
'''
Application that connects a XHC WHB04B-4 pendant to a grbl controller

Button Interpretation:
  * Reset: ????
  * Stop: stop everything and leave in position
  * Feed+/-: adjust feed rate while program is running
  * Spindle+/-: adjust spindle speed while program is running
  * M-Home: stop and home all three axes in machine coordinate space
  * Safe-Z: retract spindle to top of Z axis travel (home Z axis only)
  * W-Home: stop and home all three axes in workpiece coordinate space
  * S-on/off: toggle spindle on/off
  * Probe-Z: run probing cycle
  * Continuous: set into continuous movement mode
    - selected axis will move in direction of jog wheel movement (i.e., cw or ccw)
    - movement will stop whenever wheel movement stops
    - movement is done at the rate given by the increment knob setting
      * i.e., a percentage of max movement rate
    - movement is independent of speed at which the jog wheel is rotated
  * Step: set into step movement mode
    - selected axis will move in direction of jog wheel movement
    - movement is in increments given by the increment knob setting
==> I don't know what the "Lead" setting means, will disable for now
    I think it means that you pull the spindle around by hand and it follows
  * Macro-[1-11]: defined by yaml in button config file
'''

import argparse
import json
import logging
import os
import signal
import sys
import time
import yaml
from yaml import Loader

from Controller import Controller
from Host import Host
from Pendant import Pendant
from Processor import Processor


DEFAULTS = {
    'logLevel': "INFO",  #"DEBUG"  #"WARNING"
    'macroPath': "./whb04b.yml"
}


def run(options):
    """????
    """
    macros = {}
    with open(options.macroPath, "r") as f:
        macros = yaml.load(f, Loader=Loader)
    print("Macros:")
    json.dump(macros, sys.stdout, indent=4, sort_keys=True)
    print("")

    '''
    interrupted = False
    def handler(signum, frame):
        logging.debug(f"Caught signal: {signum}")
        interrupted = True
        p.shutdown()

    #### TODO do graceful shutdown on signal
    for s in (): #### ('TERM', 'HUP', 'INT'):
        sig = getattr(signal, 'SIG'+s)
        signal.signal(sig, handler)
    '''
    pend = Pendant()
    ctlr = Controller()
    host = Host()
    proc = Processor(pend, ctlr, host, macros)
    print("PROC START")
    proc.start()
    print("PROC DONE")
    while True:
        time.sleep(1000)
    print("DONE DONE")


def getOpts():
    usage = f"Usage: {sys.argv[0]} [-v] [-L <logLevel>] [-l <logFile>] " + \
      "[-m <macroPath>]"
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-L", "--logLevel", action="store", type=str,
        default=DEFAULTS['logLevel'],
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level")
    ap.add_argument(
        "-l", "--logFile", action="store", type=str,
        help="Path to location of logfile (create it if it doesn't exist)")
    ap.add_argument(
        "-m", "--macroPath", action="store", type=str, default=DEFAULTS['macroPath'],
        help="Path to YAML file containing macro key definitions")
    ap.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="Enable printing of debug info")
    opts = ap.parse_args()

    if opts.logFile:
        logging.basicConfig(filename=opts.logFile,
                            format='%(asctime)s %(levelname)-8s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S',
                            level=opts.logLevel)
    else:
        logging.basicConfig(level=opts.logLevel,
                            format='%(asctime)s %(levelname)-8s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S')
    if not os.path.exists(opts.macroPath):
        logging.error(f"Macro key definitions file not found: {opts.macroPath}")
        sys.exit(1)

    if opts.verbose:
        print(f"    Macro definitions file: {opts.macroPath}")
    return opts


if __name__ == '__main__':
    opts = getOpts()
    r = run(opts)
    sys.exit(r)




