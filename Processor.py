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

from parse import parse

from Controller import Controller
from Host import Host
from Pendant import Pendant, KEYMAP, FN_KEYMAP, KEYNAMES_MAP, INCR


JOG_SPEED = 500  #### FIXME
MAX_SPEED = 1000  #### FIXME

MAX_NUM_MACROS = 9  # N.B. temporarily reserving one for exit command

STATUS_POLL_INTERVAL = 0.5


assert JOG_SPEED <= MAX_SPEED


#### TODO add another thread for "controllerStatus()" -- update display with information
#### TODO add a thread to issue status queries during jog -- maybe use the Controller thread and jog tracking?


class ControllerInput(threading.Thread):
    """????
      <gets inputs from controller and does something with them>
    """
    def __init__(self, runningEvent, controller):
        self.running = runningEvent
        self.ctlr = controller
        super().__init__()

    def run(self):
        logging.debug("Starting controllerInput thread")
        self.ctlr.start()
        while self.running.isSet():
            print("wait for ctlr input")
            inputs = self.ctlr.getInput()
            print("CIN:", inputs)
            #### TODO if type 7 or 1, reset the display
        logging.debug("Exited ControllerInput")


class ControllerStatus(threading.Thread):
    """????
      <gets status from controller and updates the pendant display>
    """
    def __init__(self, runningEvent, controller):
        self.running = runningEvent
        self.ctlr = controller
        super().__init__()

    def run(self):
        logging.debug("Starting controllerStatus thread")
        self.ctlr.start()
        while self.running.isSet():
            status = self.ctlr.getStatus()
            #### TODO update Pendant display
        logging.debug("Exited ControllerStatus")


class StatusPolling(threading.Thread):
    """????
    """
    def __init__(self, stopEvent, controller):
        self.stop = stopEvent
        self.ctlr = controller
        super().__init__()

    def run(self):
        logging.debug("Starting StatusPolling Thread")
        while not self.stop.wait(STATUS_POLL_INTERVAL):
            logging.debug("StatusPolling: Poll Status")
            self.ctlr.realtimeCommand("STATUS")


#### TODO make use of Event objects consistent with other modules
class Processor():
    """????
    """
    def __init__(self, pendant, controller, host, macros=[]):
        assert isinstance(pendant, Pendant), f"pendant is not an instance of Pendant: {type(pendant)}"
        self.pendant = pendant
        assert isinstance(controller, Controller), f"controller is not an instance of Controller: {type(controller)}"
        self.controller = controller

        self.spindleState = False
        self.stepMode = None  #### FIXME use startup default value

        def dollarViewClosure(cmdName):
            def closure():
                return controller.dollarView(cmdName)
            return closure

        #### TODO add more magic commands
        self.magicCommands = {
            'VIEW_SETTINGS': dollarViewClosure('VIEW_SETTINGS'),
            'VIEW_PARAMETERS': dollarViewClosure('VIEW_PARAMETERS'),
            'VIEW_PARSER': dollarViewClosure('VIEW_PARSER'),
            'VIEW_BUILD': dollarViewClosure('VIEW_BUILD'),
            'VIEW_STARTUPS': dollarViewClosure('VIEW_STARTUPS'),
            'HELP': dollarViewClosure('HELP')
        }

        assert isinstance(macros, list), f"Invalid macros -- must be list of dicts: {macros}"
        assert len(macros) < MAX_NUM_MACROS, f"Invalid macros -- too many definitions, must be less than {MAX_NUM_MACROS}"
        assert all(['commands' in m.keys() and 'description' in m.keys() for m in macros]), f"Invalid macros -- each definition must have 'commands' and 'description' keys"

        #### TODO convert all before and after fields to lists
        for m in macros:
            m.update((k, v.split()) for k, v in m.items() if k in ('before', 'after') and isinstance(v, str))
        self.macros = macros
        #### TODO validate magic commands in before and after fields
        #assert cmd in MAGIC_COMMANDS, f"Invalid magic command: {cmd}"

        #### TODO validate macros -- turn off motion and run through grbl to see if good

        self.p2cRunning = threading.Event()
        self.p2cRunning.set()
        self.p2cThread = threading.Thread(target=self.pendantInput, name="p2c")

        self.c2pRunning = threading.Event()
        self.c2pRunning.set()
        self.c2piThread = ControllerInput(self.c2pRunning, self.controller)
        self.c2psThread = ControllerStatus(self.c2pRunning, self.controller)

        self.statusStop = threading.Event()
        self.statusStop.clear()
        self.statusThread = StatusPolling(self.statusStop, self.controller)

        self.p2cThread.start()
        self.c2piThread.start()
        self.c2psThread.start()
        self.statusThread.start()

        #### TODO hook up the host

    def _executeMagic(self, commands):
        for cmd in commands:
            pass  #### FIXME

    def magicCommandNames(self):
        return list(self.magicCommands.keys())

    def shutdown(self):
        if self.statusStop.isSet():
            logging.warning("ControllerStatus thread not running")
        else:
            self.statusStop.set()
            logging.debug("Waiting for ControllerStatus thread to end")
            self.statusThread.join()
            logging.debug("ControllerStatus thread done")
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
            logging.debug("Waiting for C2P threads to end")
            self.c2piThread.join()
            self.c2psThread.join()
            logging.debug("C2P threads done")
        else:
            logging.warning("Controller to Pendant thread not running")

    def isAlive(self):
        """????
        """
        return self.p2cThread.is_alive()

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
                    logging.debug("Reset and unlock GRBL")
                    self.controller.realtimeCommand("RESET")
                    self.controller.killAlarmLock()
                elif key == "Stop":
                    logging.debug("Stop: feed hold")
                    self.controller.realtimeCommand("FEED_HOLD")
                elif key == "StartPause":
                    logging.debug("StartPause: cycle start")
                    self.controller.realtimeCommand("CYCLE_START")
                elif key.startswith("Feed"):
                    #### FIXME select 100/10/1 increment based on feed switch setting
                    if key == "Feed+":
                        logging.debug("Feed+: TBD")
                    elif key == "Feed-":
                        logging.debug("Feed-: TBD")
                elif key.startswith("Spindle"):
                    #### FIXME select 100/10/1 increment based on feed switch setting
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
                    if self.spindleState:
                        logging.debug(f"Spindle: off")
                        self.spindleState = False
                        self.controller.streamCmd("M5")
                    else:
                        logging.debug(f"Spindle: on")
                        self.spindleState = True
                        self.controller.streamCmd("M3")
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
                    self.p2cRunning.clear()
                    break
                elif key.startswith("Macro-"):
                    res = parse("Macro-{num:d}", key)
                    if res:
                        num = res['num'] - 1
                        if num >= len(self.macros):
                            logging.error(f"Undefined macro #{num}")
                        else:
                            logging.debug(f"Macro #{num}: {self.macros[num]['description']}")
                            magic = self.macros[num]['before'] if 'before' in self.macros[num] else []
                            res = self._executeMagic(magic)
                            logging.info(f"Before Magic Commands: {magic}\n{res}")
                            if self.macros[num]['commands']:
                                self.controller.streamCmd(self.macros[num]['commands'])
                            magic = self.macros[num]['after'] if 'after' in self.macros[num] else []
                            res = self._executeMagic(magic)
                            logging.info(f"After Magic Commands: {magic}\n{res}")
                    else:
                        logging.error(f"Failed to parse Macro number: {key}")
                else:
                    logging.warning(f"Unimplemented Key: {key}")
####                self.controller.realtimeCommand("STATUS")

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
    proc = Processor(p, c, h)
    print("RUN")
    while proc.isAlive():
        print("running...")
        time.sleep(10)
    print("SHUTTING DOWN")
    proc.shutdown()
    print("DONE")
    sys.exit(0)
