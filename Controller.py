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

import logging

import serial

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
        #### TODO handle commands in chevrons '<...>' or ????
        #### TODO signal when 'ok' or 'error' received
        return {'data': str(packet)}  #### TODO add metadata

    def sendOutput(self, data):
        """????
        """
        assert self.open, "Port not open"
        numBytes = len(data)
        if numBytes <= (Controller.RX_BUFFER_SIZE - self.bufferedBytes):
            self.serial.write(bytes(data, encoding='utf8'))
            if self.flush:
                self.serial.flush()
        else:
            logging.info("Controller Rx buffer full, waiting...")
            ????
            logging.info("done")

        logging.debug(f"Write to {self.port}: {data}")


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

