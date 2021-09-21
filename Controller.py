'''
Object that encapsulates a USB-attached GRBL-based CNC controller.

Notes:
  * '$' command:
    - returns help
    - the '$' and enter are not echoed
    - '[0-132]=value' to save Grbl setting value
    - 'N[0-9]=line' to save startup block
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
'''

#### TODO implement buffer-aware streaming interface and separate realtime interface

import logging
from queue import Queue

from parse import parse
import serial

from grbl import RX_BUFFER_SIZE, REALTIME_COMMANDS, DOLLAR_COMMANDS, DOLLAR_VIEW_COMMANDS
from Receiver import Receiver


DEF_PORT = "/dev/ttyACM0"

DEF_BAUDRATE = 115200

DEF_SERIAL_TIMEOUT = 0.1    # serial port timeout (secs)

DEF_SERIAL_DELAY = 0.1      # inter-character TX delay (secs)

#DEF_STARTUP_CMDS = ["$H", "G21", "G90"]    # home, mm, absolute mode
DEF_STARTUP_CMDS = []


class Controller(Receiver):
    def __init__(self, port=DEF_PORT, baudrate=DEF_BAUDRATE, timeout=DEF_SERIAL_TIMEOUT, delay=DEF_SERIAL_DELAY):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.delay = delay

        self.flush = True
        self.maxPacketSize = 128
        self.ackQ = Queue()
        self.bufferedBytes = []

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

          Input packets
        """
        assert self.open, "Port not open"
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
            #### TODO should use error descriptions not codes -- map the error code somewhere
            try:
                errorCode = int(parse("error:{num}", packet)['num'])
            except Exception as ex:
                logging.error(f"Invalid error message '{packet}': {ex}")
            self.ackQ.put(True)
            return None
        elif packet.startswith("ALARM:"):
            #### FIXME
            #### TODO should use error descriptions not codes -- map the error code somewhere
            logging.error("Unimplemented ALARM handling")
            self.ackQ.put(True)
            return None

        if packet[0] == '<' and packet[-1] == '>':
            packetType = "Status"
        elif packet.startswith("[MSG:") and packet[-1] == ']':
            packetType = "Feedback"
        elif packet.startswith("[GC:") and packet[-1] == ']':
            packetType = "GCodeState"
        elif packet.startswith("[G") or packet.startswith("[TLO:") or packet.startswith("[PRB:"):
            packetType = "Parameter"
        elif packet.startswith("[VER:") and packet[-1] == ']':
            packetType = "Build"
        elif packet.startswith("[OPT:") and packet[-1] == ']':
            packetType = "Build"
        elif packet.startswith("[echo:") and packet[-1] == ']':
            packetType = "Echo"
        elif packet.startswith(">") and packet.endswith(":ok") == ']':
            packetType = "Startup"
        elif packet.startswith("$"):
            packetType = "Parameter"
        else:
            packetType = "Standard"
        result = {'data': str(packet), 'type': packetType}
        logging.debug(f"Received: {result}")
        return result

    #### FIXME
    def getAllInput(self):
        allInput = self.getInput()['data']
        while True:
            inLine = self.getInput(block=True, timeout=0.5)
            if not inLine:
                break
            allInput += f"\n{inLine['data']}"
        return allInput

    def sendOutput(self, data):
        """Send string (typically a single line) to the GRBL device's input buffer

          Remembers the number of bytes sent to the device and waits until there
           is enough space to buffer the full line before sending.
          Retires record of bytes sent when an ack is received from the device.
          (Both 'ok' and 'error' responses mean that the associated bytes in the
           buffer have been freed.)
          This makes the assumption that the ack corresponds to the oldest line
           size, so a lifo queue of line sizes can be used and the oldest entry
           is popped each time an ack is signalled from the device receive side.
        """
        assert self.open, "Controller port not open"
        while not self.ackQ.empty():
            self.ackQ.get()
            if len(self.bufferedBytes) > 0:
                self.bufferedBytes.pop(0)

        data = data.strip() + "\r\n"
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

    def sendRealtimeCommand(self, cmdName):
        """Send a realtime command to the controller.

         Realtime commands do not occupy buffer space in the controller.
        """
        assert cmdName in REALTIME_COMMANDS.keys(), f"Command '{cmdName}' not a valid realtime command"
        self.serial.write(bytes(REALTIME_COMMANDS[cmdName] + "\r\n"), encoding="utf-8")
        self.serial.flush()

    def sendDollarView(self, cmdName):
        """Send a realtime "dollar" command to the controller.

         Realtime commands do not occupy buffer space in the controller.
        """
        assert cmdName in DOLLAR_VIEW_COMMANDS, f"Command '{cmdName}' not a valid dollar command"
        self.serial.write(bytes('$' + DOLLAR_COMMANDS[cmdName] + "\r\n", encoding="utf-8"))
        self.serial.flush()

    def killAlarmLock(self):
        """????
        """
        #### FIXME
        pass

    def runHomingCycle(self):
        """????
        """
        #### FIXME
        pass

    def job(self, jogCmd):
        """????
        """
        #### FIXME
        pass

    def shutdown(self, blocking=True):
        """????
        """
        # poke controller to elicit a response to end wait for input
        self.sendOutput("")
        super().shutdown(blocking)


#
# TEST
#
if __name__ == '__main__':
    import time

    #### FIXME add real tests
    logging.basicConfig(level="INFO",
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    print("Start")
    ctlr = Controller()
    ctlr.start()
    print(f"Startup Message: {ctlr.getInput()['data']}")
    print(f"message: {ctlr.getInput()['data']}")
    print("")

    for dCmd in DOLLAR_VIEW_COMMANDS:
        print(f"{dCmd}:")
        ctlr.sendDollarView(dCmd)
        i = ctlr.getInput()
        while i:
            print(f"    {i['data']}, {i['type']}")
            i = ctlr.getInput(block=False, timeout=0.5)
        print("")

    print("Shutting down")
    ctlr.shutdown()
    assert ctlr.isShutdown(), "Not shutdown properly"
    print("Done")
