'''
Object that encapsulates the logic for handling communications between a
 USB-attached pendant and a USB-attached GRBL-based CNC controller.

Fires up a pair of threads -- one for taking input from the pendant, updating
 the local state, and sending (G-Code) commands to the grbl controller, and
 another for taking input from the controller, updating local state, and
 sending display commands to the pendant.
'''

import logging
import threading

from Controller import Controller
from Host import Host
from Pendant import Pendant, KEYMAP, INCR


JOG_SPEED = 500  #### FIXME
MAX_SPEED = 1000  #### FIXME


assert JOG_SPEED <= MAX_SPEED


class Processor():
    def __init__(self, pendant, controller, host, macros={}):
        assert isinstance(pendant, Pendant), f"pendant is not an instance of Pendant: {type(pendant)}"
        self.pendant = pendant
        assert isinstance(controller, Controller), f"controller is not an instance of Controller: {type(controller)}"
        self.controller = controller

        self.macros = macros
        #### FIXME validate macros

        self.stepMode = None  #### FIXME deal with startup default value

        self.p2cRunning = None
        self.p2cThread = threading.Thread(target=self.pendantInput, name="p2c")
#        self.p2cThread.daemon = True

        self.c2pRunning = None
        self.c2pThread = threading.Thread(target=self.controllerInput, name="c2p")
#        self.c2pThread.daemon = True

        #### TODO hook up the host

    def start(self):
        self.p2cRunning = True
        self.p2cThread.start()
        self.c2pRunning = True
        self.c2pThread.start()

    def shutdown(self):
        if self.p2cRunning:
            self.p2cRunning = False
            logging.debug("Waiting for P2C thread to end")
            self.p2cThread.join()
        else:
            logging.warning("Pendant to Controller thread not running")
        if self.c2pRunning:
            self.c2pRunning = False
            logging.debug("Waiting for C2P thread to end")
            self.c2pThread.join()
        else:
            logging.warning("Controller to Pendant thread not running")

    def pendantInput(self):
        self.pendant.start()
        while self.p2cRunning:
            inputs = self.pendant.getInput()
            print("PIN:", inputs)
            try:
                print("K:", inputs['key2'], inputs['key1'])
                key = KEYMAP[inputs['key2']][inputs['key1']]
            except IndexError:
                key = None
            if key:
                if key == "Reset":
                    logging.debug("Reset: TBD")
                elif key == "Stop":
                    logging.debug("Stop: TBD")
                elif key == "StartPause":
                    logging.debug("StartPause: TBD")
                elif key.startswith("Feed"):
                    if key == "Feed+":
                        logging.debug("Feed+: TBD")
                    elif key == "Feed-":
                        logging.debug("Feed-: TBD")
                elif key.startswith("Spindle"):
                    if key == "Spindle+":
                        logging.debug("Spindle+: TBD")
                    if key == "Spindle-":
                        logging.debug("Spindle-: TBD")
                elif key == "M-Home":
                    logging.debug("M-Home: TBD")
                elif key == "Safe-Z":
                    logging.debug("Save-Z: TBD")
                elif key == "W-Home":
                    logging.debug("W-Home: TBD")
                elif key == "S-on/off":
                    logging.debug("S-on/off: TBD")
                elif key == "Fn":
                    logging.debug("Fn: TBD")
                elif key == "Probe-Z":
                    logging.debug("Probe-Z: TBD")
                elif key == "Continuous":
                    self.stepMode = False
                    logging.debug("Continuous: TBD")
                elif key == "Step":
                    self.stepMode = True
                    logging.debug("Step: TBD")
                elif key.startswith("Macro-"):
                    #### FIXME lookup commands to emit in self.macros json
                    logging.debug(f"{key}: TBD")
                else:
                    logging.warning(f"Unimplemented Key: {key}")

            if inputs['jog']:
                incr = INCR['Step' if self.stepMode else 'Continuous'][inputs['incr']]
                assert incr, "Got Jog command, but Incr is Off"
                if self.stepMode:
                    distance = inputs['jog'] * incr
                    speed = JOG_SPEED
                else:
                    distance = 1  #### FIXME
                    speed = MAX_SPEED * incr * (1 if inputs['jog'] > 0 else -1)
                logging.debug(f"Jog {distance} @ {speed}")
        logging.debug("Exit PendantInput")

    def controllerInput(self):
        self.controller.start()
        while self.c2pRunning:
            inputs = self.controller.getInput()
            print("CIN:", inputs)
        logging.debug("Exit ControllerInput")


#
# TEST
#
if __name__ == '__main__':
    import sys
    import time

    print("START")
    p = Pendant()
    print("p")
    c = Controller()
    print("c")
    h = Host()
    print("h")
    proc = Processor(p, c, h)
    print("RUN")
    time.sleep(30)
    proc.shutdown()
    print("DONE")
    sys.exit(0)
