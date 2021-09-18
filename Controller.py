'''
Object that encapsulates a USB-attached GRBL-based CNC controller.

Notes:
  * '$' command:
    - returns help
    - the '$' and enter are not echoed
    - '[0-132]=value' to save Grbl setting value
    - 'N[0-9]=line' to save startup block
  * Cycle Start, Feed Hold, and Reset realtime commands have corresponding HW buttons
'''

#### TODO implement buffer-aware streaming interface and separate realtime interface

import logging
from queue import Queue

from parse import parse
import serial

from grbl import RX_BUFFER_SIZE, REALTIME_COMMANDS, DOLLAR_COMMANDS
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
            try:
                errorCode = int(parse("error:{num}", packet)['num'])
            except Exception as ex:
                logging.error(f"Invalid error message '{packet}': {ex}")
            self.ackQ.put(True)
            return None

        print("P", packet, len(packet))
        if packet[0] == '<' and packet[-1] == '>':
            packetType = "Status"
        elif packet.startswith("[MSG:") and packet[-1] == ']':
            packetType = "Feedback"
        elif packet.startswith("[GC:") and packet[-1] == ']':
            packetType = "GCodeState"
        elif packet.startswith("[G") or packet.startswith("[TL0:") or packet.startswith("[PRB:"):
            packetType = "Parameter"
        elif packet.startswith("[VER:") and packet[-1] == ']':
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
        assert self.open, "Port not open"
        while not self.ackQ.empty():
            self.ackQ.get()
            self.bufferedBytes.pop(0)

        data = data.strip() + "\r\n"
        numBytes = len(data)
        while numBytes > (RX_BUFFER_SIZE - sum(self.bufferedBytes)):
            self.ackQ.get(block=True)
            self.bufferedBytes.pop(0)

        self.serial.write(bytes(data, encoding='utf8'))
        if self.flush:
            self.serial.flush()
        self.bufferedBytes.append(numBytes)
        logging.debug(f"Wrote: {data}")

    def sendRealtimeOutput(self, cmdName):
        """Send a realtime command to the controller.

         Realtime commands do not occupy buffer space in the controller.
        """
        assert cmdName in REALTIME_COMMANDS.keys(), f"Command '{cmdName}' not a valid realtime command"
        self.serial.write(bytes([REALTIME_COMMANDS[cmdName], ord('\r'), ord('\n')]))
        self.serial.flush()

    def sendDollarOutput(self, cmdName):
        """Send a realtime "dollar" command to the controller.

         Realtime commands do not occupy buffer space in the controller.
        """
        assert cmdName in DOLLAR_COMMANDS.keys(), f"Command '{cmdName}' not a valid dollar command"
        self.serial.write(bytes([ord('$'), DOLLAR_COMMANDS[cmdName], ord('\r'), ord('\n')]))
        self.serial.flush()

    def sendJogOutput(self, unk):
        """????
        """
        pass


#
# TEST
#
if __name__ == '__main__':
    print("Start")
    ctlr = Controller()
    print(">", ctlr.getInput())
    ctlr.sendOutput("")
    print(">>", ctlr.getInput())

    ctlr.sendOutput("$?")
    print(">>>", ctlr.getInput())
    ctlr.sendOutput("$$")
    i = ctlr.getInput()
    print(">>>>", i)
    while i:
        i = ctlr.getInput()
        print(">>>>>", i)
    ctlr.shutdown()
    print("Done")

