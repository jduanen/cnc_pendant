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
import Pendant


JOG_SPEED = 500  #### FIXME
MAX_SPEED = 1000  #### FIXME

MAX_NUM_MACROS = 10

STATUS_POLL_INTERVAL = 0.5


assert JOG_SPEED <= MAX_SPEED

# N.B. This can be global as there's a single writer (PendantInput)
moveMode = Pendant.MotionMode.STEP

# N.B. This can be global as there's a single writer (PendantInput)
axisMode = None


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
    COORDINATE_SPACE_MAP = {
        'MPos': Pendant.CoordinateSpace.MACHINE,
        'WPos': Pendant.CoordinateSpace.WORKPIECE
    }

    def __init__(self, runningEvent, controller, pendant):
        self.running = runningEvent
        self.ctlr = controller
        self.pendant = pendant
        super().__init__()

        self.feedSpeed = 0
        self.spindleSpeed = 0

    def _parseStatus(self, status):
        status = status[1:-1].split('|')
        parts = {p.split(':')[0]: p.split(':')[1] for p in status[1:]}
        parsedStatus = {'state': status[0]}
        for name, part in parts.items():
            if name.endswith('Pos'):
                parsedStatus['coordinateSpace'] = ControllerStatus.COORDINATE_SPACE_MAP[name]
                parsedStatus['coordinates'] = list(map(float, part.split(',')))
            elif name == "Bf":
                parsedStatus['planBuffers'] = part.split(',')[0]
                parsedStatus['rxBuffers'] = part.split(',')[1]
            elif name == "Ln":
                parsedStatus['lineNumber'] = int(part)
            elif name == "FS":
                parsedStatus['feedSpeed'] = float(part.split(',')[0])
                parsedStatus['spindleSpeed'] = int(part.split(',')[1])
            elif name == "F":
                parsedStatus['feedSpeed'] = int(part)
            elif name == "WCO":
                #### TODO parse this further
                parsedStatus['workCoordinateOffset'] = part
            elif name == "A":
                #### TODO parse this further
                parsedStatus['accessoryState'] = part
            elif name == "Ov":
                #### TODO parse this further
                parsedStatus['overrides'] = part
            elif name == "Pn":
                #### TODO parse this further
                parsedStatus['pinStates'] = part
            else:
                logging.error(f"Unimplemented status field: {name}: {part}")
        return parsedStatus

    def run(self):
        global moveMode  # N.B. read-only in this thread
        global axisMode  # N.B. read-only in this thread

        logging.debug("Starting controllerStatus thread")
        self.ctlr.start()
        while self.running.isSet():
            status = self._parseStatus(self.ctlr.getStatus())
            logging.info(f"Status: {status}")
            self.pendant.updateDisplay(moveMode,
                                       status['coordinateSpace'],
                                       status['coordinates'] if axisMode == Pendant.AxisMode.XYZ else [0.0, 0.0, 0.0],
                                       status['feedSpeed'] if status['feedSpeed'] != self.feedSpeed else 0,
                                       status.get('spindleSpeed', 0))
            self.feedSpeed = status['feedSpeed']
            self.spindleSpeed = status.get('spindleSpeed', 0)
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
    def __init__(self, pendant, controller, host, macros={}):
        assert isinstance(pendant, Pendant.Pendant), f"pendant is not an instance of Pendant: {type(pendant)}"
        self.pendant = pendant
        assert isinstance(controller, Controller), f"controller is not an instance of Controller: {type(controller)}"
        self.controller = controller

        self.spindleState = False

        self.magicCommands = self._initMagic()
        self.macros = self._defineMacros(macros)

        self.p2cRunning = threading.Event()
        self.p2cRunning.set()
        self.p2cThread = threading.Thread(target=self.pendantInput, name="p2c")

        self.c2pRunning = threading.Event()
        self.c2pRunning.set()
        self.c2piThread = ControllerInput(self.c2pRunning, self.controller)
        self.c2psThread = ControllerStatus(self.c2pRunning, self.controller, self.pendant)

        self.statusStop = threading.Event()
        self.statusStop.clear()
        self.statusThread = StatusPolling(self.statusStop, self.controller)

        self.p2cThread.start()
        self.c2piThread.start()
        self.c2psThread.start()
        self.statusThread.start()

        #### TODO hook up the host

    def _executeMagic(self, commands):
        results = ""
        for cmd in commands:
            results += self.magicCommands[cmd]() + '\n'
        return results

    def _initMagic(self):
        def dumpState():
            state = f"Running threads: {threading.enumerate()}\n"
            state += f"Globals: moveMode={moveMode}, axisMode={axisMode}\n"
            #### TODO add more state info
            return state

        def commandClosure(cmdType, cmdName):
            def closure():
                if cmdType == "dollar":
                    cmd = self.controller.dollarCommand(cmdName)
                elif cmdType == "realtime":
                    cmd = self.controller.realtimeCommand(cmdName)
                return cmd
            return closure

        return {
            'VIEW_SETTINGS': commandClosure("dollar", "VIEW_SETTINGS"),
            'VIEW_PARAMETERS': commandClosure("dollar", "VIEW_PARAMETERS"),
            'VIEW_PARSER': commandClosure("dollar", "VIEW_PARSER"),
            'VIEW_BUILD': commandClosure("dollar", "VIEW_BUILD"),
            'VIEW_STARTUPS': commandClosure("dollar", "VIEW_STARTUPS"),
            'HELP': commandClosure("dollar", "HELP"),
            'KILL_ALARM': commandClosure("dollar", "KILL_ALARM"),
            'CYCLE_START': commandClosure("realtime", "CYCLE_START"),
            'FEED_HOLD': commandClosure("realtime", "FEED_HOLD"),
            'STATUS': commandClosure("realtime", "STATUS"),
            'RESET': commandClosure("realtime", "RESET"),
            'JOG_CANCEL': commandClosure("realtime", "JOG_CANCEL"),
            'DUMP_STATE': dumpState
        }

    def _defineMacros(self, macros):
        ##assert isinstance(macros, dict) and all([isinstance(k, int) and isinstance(v, dict) for k, v in dict.items()]), f"Invalid macros -- must be dict of dicts with integer keys and dict values: {macros}"
        ##assert all(['commands' in m.keys() and 'description' in m.keys() for m in macros]), f"Invalid macros -- each definition must have 'commands' and 'description' keys"
        '''
        for m in macros:
            m.update((k, v.split()) for k, v in m.items() if k in ('before', 'after') and isinstance(v, str))
        '''
        macroList = [None for _ in range(0, MAX_NUM_MACROS + 1)]
        for name, macro in macros.items():
            res = parse("Macro-{num:d}", name)
            if res:
                num = res['num']
            else:
                logging.warning(f"Invalid macro name '{name}': ignoring")
                continue
            if num <= 0 or num > MAX_NUM_MACROS:
                logging.warning(f"Invalid macro number '{num}': ignoring")
                continue
            #### TODO validate macro -- turn off motion and run through grbl to see if good
            #### TODO validate magic commands in before and after fields
            #assert cmd in MAGIC_COMMANDS, f"Invalid magic command: {cmd}"
            macro.update((k, v.split()) for k, v in macro.items() if k in ('before', 'after') and isinstance(v, str))
            macroList[num] = macro
        return macroList

    def defineMacros(self, macros):
        self.macros = self._defineMacros(macros)

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
        """????
        """
        global moveMode  # N.B. this thread is the single writer
        global axisMode  # N.B. this thread is the single writer

        logging.debug("Starting pendantInput thread")
        self.pendant.start()
        while self.p2cRunning.isSet():
            inputs = self.pendant.getInput()
            if not inputs:
                continue
            inputs = inputs['data']
            axisMode = Pendant.AxisMode.OFF if inputs['axis'] == 6 else Pendant.AxisMode.XYZ if inputs['axis'] < 20 else Pendant.AxisMode.ABC
            logging.info(f"PendantInput: {inputs}")
            key = Pendant.KEYMAP[inputs['key1']] if inputs['key2'] == 0 else Pendant.FN_KEYMAP[inputs['key2']] if inputs['key1'] == Pendant.KEYNAMES_MAP['Fn'] else None
            if key:
                if key == "Reset":
                    logging.debug("PI -- Reset and unlock GRBL")
                    self.controller.realtimeCommand("RESET")
                    self.controller.killAlarmLock()
                elif key == "Stop":
                    logging.debug("PI -- Stop: feed hold")
                    self.controller.realtimeCommand("FEED_HOLD")
                elif key == "StartPause":
                    logging.debug("PI -- StartPause: cycle start")
                    self.controller.realtimeCommand("CYCLE_START")
                elif key.startswith("Feed"):
                    #### FIXME select 100/10/1 increment based on feed switch setting
                    if key == "Feed+":
                        logging.debug("PI -- Feed+: TBD")
                    elif key == "Feed-":
                        logging.debug("PI -- Feed-: TBD")
                elif key.startswith("Spindle"):
                    #### FIXME select 100/10/1 increment based on feed switch setting
                    if key == "Spindle+":
                        logging.debug("PI -- Spindle+: TBD")
                    if key == "Spindle-":
                        logging.debug("PI -- Spindle-: TBD")
                elif key == "M-Home":
                    logging.debug("PI -- M-Home: TBD")
                elif key == "Safe-Z":
                    logging.debug("PI -- Save-Z: TBD")
                elif key == "W-Home":
                    logging.debug("PI -- W-Home: TBD")
                elif key == "S-on/off":
                    if self.spindleState:
                        logging.debug(f"PI -- Spindle: off")
                        self.spindleState = False
                        self.controller.streamCmd("M5")
                    else:
                        logging.debug(f"PI -- Spindle: on")
                        self.spindleState = True
                        self.controller.streamCmd("M3")
                elif key == "Fn":
                    logging.debug("PI -- Fn")
                elif key == "Probe-Z":
                    logging.debug("PI -- Probe-Z: TBD")
                elif key == "Continuous":
                    moveMode = Pendant.MotionMode.CONT
                    logging.debug(f"PI -- Continuous: set moveMode to {moveMode}")
                elif key == "Step":
                    moveMode = Pendant.MotionMode.STEP
                    logging.debug(f"PI -- Step: set moveMode to {moveMode}")
                elif key == "PendantReset":
                    # hard-coded as key to press after Pendant power-on
                    logging.debug("PI -- PendantReset: bring out of reset")
                    self.pendant.reset(moveMode)
                    break
                elif key == "ApplicationExit":
                    # hard-coded as application shutdown key
                    logging.debug("PI -- ApplicationExit: SHUTDOWN")
                    self.p2cRunning.clear()
                    break
                elif key.startswith("Macro-"):
                    res = parse("Macro-{num:d}", key)
                    if res:
                        num = res['num']
                        if not self.macros[num]:
                            logging.error(f"Undefined macro: Macro-{num}")
                        else:
                            logging.debug(f"PI -- Macro-{num}: {self.macros[num]['description']}")

                            magic = self.macros[num]['before'] if 'before' in self.macros[num] else []
                            logging.debug(f"PI -- Before Magic Commands: {magic}")
                            res = self._executeMagic(magic)
                            logging.info(res)

                            if self.macros[num]['commands']:
                                self.controller.streamCmd(self.macros[num]['commands'])

                            magic = self.macros[num]['after'] if 'after' in self.macros[num] else []
                            logging.debug(f"PI -- After Magic Commands: {magic}")
                            res = self._executeMagic(magic)
                            logging.info(res)
                    else:
                        logging.error(f"Failed to parse Macro number: {key}")
                else:
                    logging.warning(f"Unimplemented Key: {key}")

            if inputs['jog']:
                if axisMode == Pendant.AxisMode.XYZ:
                    incr = Pendant.Pendant.INCR[moveMode][inputs['incr']]
                    if incr:
                        if moveMode == Pendant.MotionMode.STEP:
                            distance = inputs['jog'] * incr
                            speed = JOG_SPEED
                        elif moveMode == Pendant.MotionMode.CONT:
                            distance = 1  #### FIXME
                            speed = MAX_SPEED * incr * (1 if inputs['jog'] > 0 else -1)
                        axis = Pendant.AXIS[inputs['axis']]
                        logging.debug(f"PI -- Jog: $J={axis}{distance} F{speed}")
                        self.controller.jogIncrementalAxis(axis, distance, speed)
                elif axisMode == Pendant.AxisMode.ABC:
                    logging.error("TBD")
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
    p = Pendant.Pendant()
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
