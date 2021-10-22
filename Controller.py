'''
Object that encapsulates a USB-attached GRBL-based CNC controller.

Notes:
  * Cycle Start, Feed Hold, and Reset realtime commands have corresponding HW buttons

  * types of packets that can be sent by the controller:
    - 'ok': command ack at end of execution
    - 'error:<code>': error of type <code> occurred
    - '<...>': angle brackets enclose status report data
    - 'Grbl <X.Xx> ['$' for help]': startup message version X.Xx
    - 'ALARM:<code>': alarm of type <code> occurred, controller is now in alarm state
    - '$<reg>=<val>': set register <reg> to value <val>
    - '$N<reg>=<val>': set register <reg> to value <val> ????
    - '[MSG: ... ]': feedback message given not in response to a query
    - '[GC: ... ]': message in response to a $G g-code state message query
    - '[HLP: ... ]': help message
    - '[G54:], [G55:], [G56:], [G57:], [G58:], [G59:], [G28:], [G30:], [G92:], [TLO:], and [PRB:]': messages with parameter data from $# query
    - '[VER: ... ]': version/build info from $I query
    - '[OPT: ... ]': compile time options from $I query
    - '[echo: ... ]': automated line echo from pre-parsed string prior to g-code parsing
    - '>G54G20:ok': open angle bracket indicates startup line execution

  * types of messages from Grbl
    - Response Message: in response to issuing a command/query
      * start with either 'ok' or 'error'
    - Push Message: provide feedback on what Grbl is doing
      * don't start with 'ok' or 'error'
      * start with '[', '<', '$', or a specific text string
      * can be enclosed in either '[]' or '<>' pairs

  * types of commands and their response messages
    - "dollar":
      * issued in IDLE state
      * expect either an 'error' or immediate response message(s), followed by a 'ok'
        - some commands (e.g., '$$', '$G', etc.) return more than one line
        - gather input until you get an 'ok'
      * sending these messages can be synchronous with getting a response
        - shouldn't have any queued messages -- maybe clean out inputs before sending
    - realtime:
      * issued at any time, with the machine in any in any state
      * no CR/LF required
      * do not return an 'ok' or an 'error' response
      * not part of streaming protocol
        - don't have to deal with planning buffer
      * return messages vary:
        - some (e.g., '?') return "<...>",
        - others (e.g., '$') "[...]",
        - and yet others (e.g., '!', '~') return no message
  * Streaming requires tracking Response Messages
    - Push Messages are not part of streaming protocol and are handled independently
'''

#### TODO implement buffer-aware streaming interface and separate realtime interface

import logging
from queue import Queue
import time

from parse import parse
import serial

from grbl import (RX_BUFFER_SIZE, REALTIME_COMMANDS, DOLLAR_COMMANDS,
                  alarmDescription, errorDescription)
from Receiver import Receiver


DEF_PORT = "/dev/ttyACM0"

DEF_BAUDRATE = 115200

DEF_SERIAL_TIMEOUT = 0.1    # serial port timeout (secs)

DEF_SERIAL_DELAY = 0.1      # inter-character TX delay (secs)

#DEF_STARTUP_CMDS = ["$H", "G21", "G90"]    # home, mm, absolute mode
DEF_STARTUP_CMDS = []

DEF_FEEDRATE = 500  # mm/min


class PacketTypes():
    STATUS = 0
    FEEDBACK = 1
    GCODE_STATE = 2
    PARAMETER = 3
    BUILD = 4
    ECHO = 5
    STARTUP = 6
    STANDARD = 7


class Controller(Receiver):
    """????

      N.B. The act of connecting to the USB port on the Controller resets Grbl.
        This means that the Controller is always reset when this type of object
        is instantiated.
    """
    def __init__(self, port=DEF_PORT, baudrate=DEF_BAUDRATE, timeout=DEF_SERIAL_TIMEOUT, delay=DEF_SERIAL_DELAY):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.delay = delay

        self.flush = True
        self.maxPacketSize = 128
        self.ackQ = Queue()
        self.bufferedBytes = []
        self.statusQ = Queue()

        self.serial = None
        try:
            # N.B. Defaults to 8-N-1, no (HW or SW) flow control
            self.serial = serial.Serial(port=port, baudrate=baudrate, timeout=self.timeout)
        except Exception as ex:
            logging.error(f"Failed to open serial port '{port}': {ex}")
        assert self.serial and self.serial.isOpen(), f"Serial port '{port}' not open"
        self.open = True
        logging.debug(f"Opened {port} at {baudrate}")

        super().__init__(name="Controller")

    def _receive(self):
        """Read a raw (unvalidated) input packet from the device, validate it,
            and return a tuple with the input values.

          ????
        """
        assert self.open, f"Serial port not open: {self.port}"
        packet = bytes([])
        prevVal = None
        while len(packet) < self.maxPacketSize:
            val = self.serial.read(1)
            packet += val
            if val == b'\n' and prevVal == b'\r':
                break
            prevVal = val
        if len(packet) >= self.maxPacketSize:
            logging.warning("Max sized packet -- might be more data")
        packet = packet.decode('utf-8')
        packet = packet.strip()
        if not packet:
            return None

        if packet == "ok":
            self.ackQ.put(True)
            return None
        elif packet.startswith("error:"):
            #### FIXME
            logging.error(f"Error: {errorDescription(packet)}")
            self.ackQ.put(True)
            return None
        elif packet.startswith("ALARM:"):
            #### FIXME
            logging.error(f"Alarm: {alarmDescription(packet)}")
            self.ackQ.put(True)
            return None

        if packet[0] == '<' and packet[-1] == '>':
            packetType = PacketTypes.STATUS
        elif packet.startswith("[MSG:") and packet[-1] == ']':
            packetType = PacketTypes.FEEDBACK
        elif packet.startswith("[GC:") and packet[-1] == ']':
            packetType = PacketTypes.GCODE_STATE
        elif packet.startswith("[G") or packet.startswith("[TLO:") or packet.startswith("[PRB:"):
            packetType = PacketTypes.PARAMETER
        elif packet.startswith("[VER:") and packet[-1] == ']':
            packetType = PacketTypes.BUILD
        elif packet.startswith("[OPT:") and packet[-1] == ']':
            packetType = PacketTypes.BUILD
        elif packet.startswith("[echo:") and packet[-1] == ']':
            packetType = PacketTypes.ECHO
        elif packet.startswith(">") and packet.endswith(":ok") == ']':
            packetType = PacketTypes.STARTUP
        elif packet.startswith("$"):
            packetType = PacketTypes.PARAMETER
        else:
            packetType = PacketTypes.STANDARD
        result = {'data': str(packet), 'type': packetType}
        return result

    def _flushInput(self):
        #### FIXME
        pass

    def _sendCmd(self, cmd):
        """Send a single line command to the controller

          N.B. This does not consider the receive buffer behavior

          Inputs:
            cmd: ????
        """
        #### TODO validate the command input
        self.serial.write(bytes(cmd + "\r\n", encoding="utf-8"))
        self.serial.flush()

    def streamCmd(self, cmd):
        """Send string as a single line to the GRBL device's input buffer.

          Remembers the number of bytes sent to the device and waits until there
           is enough space to buffer the full line before sending.
          Retires record of bytes sent when an ack is received from the device.
          (Both 'ok' and 'error' responses mean that the associated bytes in the
           buffer have been freed.)
          This makes the assumption that the ack corresponds to the oldest line
           size, so a lifo queue of line sizes can be used and the oldest entry
           is popped each time an ack is signalled from the device receive side.

          Inputs:
            cmd: ????
        """
        assert self.open, "Controller port not open"
        while not self.ackQ.empty():
            self.ackQ.get()
            if len(self.bufferedBytes) > 0:
                self.bufferedBytes.pop(0)

        data = cmd.strip() + "\r\n"
        numBytes = len(data)
        while numBytes > (RX_BUFFER_SIZE - sum(self.bufferedBytes)):
            self.ackQ.get(block=True)
            if len(self.bufferedBytes) > 0:
                self.bufferedBytes.pop(0)

        self.serial.write(bytes(data, encoding='utf-8'))
        if self.flush:
            self.serial.flush()
        self.bufferedBytes.append(numBytes)
        logging.debug(f"Wrote: {data}")

    def _getAllInputs(self):
        """????
        """
        allInput = self.getInput()['data']
        if allInput:
            while True:
                inLine = self.getInput(block=False, timeout=0.5)
                if not inLine:
                    break
                allInput += f"\n{inLine['data']}"
        return allInput

    def receiver(self):
        """Override base function that wraps code that reads from a comm link
             and queues up the input.

          This puts the status responses from the controller into the statusQ,
           and all normal responses in the standard inputQ.

          Loops until told to shutdown by the 'receiving' event.
          Puts a final None value on the inputQ and indicates that its the input
           thread is done.
        """
        while self.receiving.isSet():
            inputs = self._receive()
            if inputs and 'data' in inputs and inputs['data']:
                isStatus = inputs['type'] == PacketTypes.STATUS
                q = self.statusQ if isStatus else self.inputQ
                qName = "Status" if isStatus else "Input"
                try: 
                    logging.debug(f"Controller Inputs: {inputs}")
                    q.put_nowait(inputs)
                except Exception as ex:
                    logging.error(f"{qName} queue full, discarding input and shutting down: {ex}")
                    self.receiving.clear()
        self.inputQ.put(None)
        self.closed = True

    def getStatus(self, block=True, timeout=None):
        """Return input from the status queue.

          Can optionally be a blocking call, with an optional timeout

          Returns: next value from status queue, or None
        """
        statusVal = None
        if block:
            statusVal = self.statusQ.get()
        else:
            try:
                statusVal = self.statusQ.get(block=True, timeout=timeout)
            except:
                logging.debug("No status, blocking get() timed out")
        return statusVal['data']

    def realtimeCommand(self, cmdName):
        """Send a realtime command to the controller and return the resulting
          status information.

         Realtime commands do not occupy buffer space in the controller.
        """
        assert cmdName in REALTIME_COMMANDS.keys(), f"Command '{cmdName}' not a valid realtime command"
        self._sendCmd(chr(REALTIME_COMMANDS[cmdName]))

    def dollarCommand(self, cmdName):
        """Send a realtime "dollar" command to the controller.

         Realtime commands do not occupy buffer space in the controller.
        """
        self._sendCmd(f"${DOLLAR_COMMANDS[cmdName]}")
        return self._getAllInputs()

    def killAlarmLock(self):
        """Send realtime command to clear alarm lock.
        """
        self._sendCmd("$X")
        res = self.getInput()
        return res['data'] if res else None

    def runHomingCycle(self):
        """Send realtime command to start homing cycle.
        """
        self._sendCmd("$H")
        #### TODO deal with Response message(s), if any

    def jogIncrementalAxis(self, axis, distance, feedrate=DEF_FEEDRATE):
        """Send realtime command to jog the spindle by given increment(s) along the given axis.

          Inputs:
            axis: ?
            distance: ?
            feedrate: int number of millimeters per minute to move the spindle along each axis
        """
        #### FIXME make work with ABC axes
        #### TODO validate args
        assert axis in "XYZ", f"Invalid axis: {axis}, must be 'X', 'Y', or 'Z'"
        assert isinstance(distance, float), f"Invalid distance: {distance}, must be a float value"
        jogCmd = f"$J=G21 G91 {axis}{distance} F{feedrate}"
        self._sendCmd(jogCmd)
        print("JOG: ", jogCmd)  #### TMP TMP TMP

    def jogIncremental(self, x=None, y=None, z=None, feedrate=DEF_FEEDRATE):
        """Send realtime command to jog the spindle by given increment(s).

          Inputs:
            x: float that indicates the number of millimeters to move the spindle in the X axis
            y: float that indicates the number of millimeters to move the spindle in the Y axis
            z: float that indicates the number of millimeters to move the spindle in the Z axis
            feedrate: int number of millimeters per minute to move the spindle along each axis
        """
        #### TODO validate args
        assert x or y or z, "Must provide at least one axis"
        jogCmd = f"G21 G91 "
        jogCmd += f"X{x} " if x else ""
        jogCmd += f"Y{y} " if y else ""
        jogCmd += f"Z{z} " if z else ""
        self._sendCmd(f"$J={jogCmd}F{feedrate}")
        print(f"$J={jogCmd}F{feedrate}")

    def shutdown(self, blocking=True):
        """????
        """
        # poke controller to elicit both a message and status response to end wait for input
        self._sendCmd("?")
        self._sendCmd("$")
        super().shutdown(blocking)


#
# TEST
#
if __name__ == '__main__':
    import time

    def track(c):
        status = None
        newStatus = c.getStatus()
        print(newStatus)
        while newStatus != status:
            status = newStatus
            c.realtimeCommand("STATUS")
            newStatus = c.getStatus()
            print(newStatus)
            time.sleep(0.25)
        print("")

    def _getStatus(c):
        c.realtimeCommand("STATUS")
        return c.getStatus()

    def jogTrack(c):
        status = _getStatus(c)
        while not status.startswith("<Jog"):
            status = _getStatus(c)
        while status.startswith("<Jog"):
            status = _getStatus(c)
            print(status)
            time.sleep(0.25)
        print("")

    #### FIXME add real tests
    logging.basicConfig(level="INFO",
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    print("Start")
    ctlr = Controller()
    ctlr.start()
    print(f"Startup Message #1: {ctlr.getInput()['data']}")
    print(f"Startup Message #2: {ctlr.getInput()['data']}")
    print("")
 
    for dCmd in DOLLAR_COMMANDS:
        print(f"{dCmd}:")
        responses = ctlr.dollarCommand(dCmd)
        if not responses:
            logging.error(f"No response from {dCmd} dollar command")
        else:
            print("    " + responses.replace("\n", "\n    ") + "\n")

    if True:
        print("kill alarm: ")
        response = ctlr.killAlarmLock()
        if not response:
            logging.error(f"No response from kill alarm command")
        else:
            print("    " + response + "\n")

        if True:
            #### TMP TMP TMP
            print("start machine (really spindle)")
            ctlr.streamCmd("M3")
            print("spindle started")
            time.sleep(5)

        if False:
            print("home the machine")
            ctlr.runHomingCycle()
            print("hit return when homing done")
            input()

    if False:
        print("Jog X=10")
        ctlr.jogIncremental(x=10, feedrate=500)
        jogTrack(ctlr)

        print("Jog X=-10, Y=10")
        ctlr.jogIncremental(x=-10, y=10, feedrate=500)
        jogTrack(ctlr)

        print("Jog X=10, Y=-10, Z=-10")
        ctlr.jogIncremental(x=10, y=-10, z=-10, feedrate=500)
        jogTrack(ctlr)

    print("turn off the spindle")
    ctlr.streamCmd("M5")
    print("    spindle off")

    print("reset the machine")
    ctlr.realtimeCommand("RESET")
    response = ctlr._getAllInputs()
    if not response:
        logging.error(f"No response from reset command")
    else:
        print("    " + response + "\n")

    print("Shutting down")
    ctlr.shutdown()
    assert ctlr.isShutdown(), "Not shutdown properly"
    print("Done")
