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
from Pendant import Pendant, KEYMAP, FN_KEYMAP, KEYNAMES_MAP, INCR


JOG_SPEED = 500  #### FIXME
MAX_SPEED = 1000  #### FIXME


assert JOG_SPEED <= MAX_SPEED


#### TODO make use of Event objects consistent with other modules
class Processor():
    """????
    """
    def __init__(self, pendant, controller, host, exitEvent, macros={}):
        assert isinstance(pendant, Pendant), f"pendant is not an instance of Pendant: {type(pendant)}"
        self.pendant = pendant
        assert isinstance(controller, Controller), f"controller is not an instance of Controller: {type(controller)}"
        self.controller = controller
        self.exit = exitEvent

        self.macros = macros
        #### FIXME validate macros

        self.stepMode = None  #### FIXME deal with startup default value

        self.p2cRunning = threading.Event()
        self.p2cThread = threading.Thread(target=self.pendantInput, name="p2c")
#        self.p2cThread.daemon = True

        self.c2pRunning = threading.Event()
        self.c2pThread = threading.Thread(target=self.controllerInput, name="c2p")
#        self.c2pThread.daemon = True

        #### TODO hook up the host

        self.p2cRunning.set()
        self.p2cThread.start()
        self.c2pRunning.set()
        self.c2pThread.start()

    def shutdown(self):
        if self.p2cRunning.isSet():
            self.p2cRunning.clear()
            logging.debug("Waiting for P2C thread to end")
            self.p2cThread.join()
            logging.debug("P2C thread done")
        else:
            logging.warning("Pendant to Controller thread not running")
        if self.c2pRunning.isSet():
            self.c2pRunning.clear()
            logging.debug("Shutting down ControllerInput")
            self.controller.shutdown()
            assert self.controller.isShutdown(), "Controller not shut down"
            logging.debug("Waiting for C2P thread to end")
            self.c2pThread.join()
            logging.debug("C2P thread done")
        else:
            logging.warning("Controller to Pendant thread not running")

    def pendantInput(self):
        logging.debug("Starting pendantInput thread")
        self.pendant.start()
        while self.p2cRunning.isSet():
            inputs = self.pendant.getInput()
            if not inputs:
                continue
            inputs = inputs['data']
            logging.debug(f"PIN: {inputs}")
            key = KEYMAP[inputs['key1']] if inputs['key2'] == 0 else FN_KEYMAP[inputs['key2']] if inputs['key1'] == KEYNAMES_MAP['Fn'] else None
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
                    logging.debug("Fn")
                elif key == "Probe-Z":
                    logging.debug("Probe-Z: TBD")
                elif key == "Continuous":
                    self.stepMode = False
                    logging.debug("Continuous: TBD")
                elif key == "Step":
                    self.stepMode = True
                    logging.debug("Step: TBD")
                elif key.startswith("Macro-10"):
                    #### TMP TMP TMP hard-coded as shutdown key
                    logging.debug(f"{key}: SHUTDOWN")
                    self.exit.set()
                    self.p2cRunning.clear()
                    break
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
        self.pendant.shutdown()
        logging.debug("Exit PendantInput")

    def controllerInput(self):
        logging.debug("Starting controllerInput thread")
        self.controller.start()
        while self.c2pRunning.isSet():
            print("wait for ctlr input")
            inputs = self.controller.getInput()
            print("CIN:", inputs)
        logging.debug("Exited ControllerInput")


#
# TEST
#
if __name__ == '__main__':
    import sys
    import time

    #### FIXME add real tests
    logging.basicConfig(level="DEBUG",
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    print("START")
    p = Pendant()
    print("p")
    c = Controller()
    print("c")
    h = Host()
    print("h")
    exit = threading.Event()
    exit.clear()
    proc = Processor(p, c, h, exit)
    print("RUN")
    while not exit.isSet():
        print("running...")
        time.sleep(10)
    print("SHUTTING DOWN")
    proc.shutdown()
    print("DONE")
    sys.exit(0)
