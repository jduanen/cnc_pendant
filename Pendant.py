'''
Object that encapsulates the XHC WHB04B-4 pendant's USB receiver

Notes:
  * I haven't seen "MPG", "F: ?", or "S: ?" displays yet, keep working on it
    - looks like this unit doesn't generate these displays.

'''

#### TODO document interfaces
#### TODO add testing

import logging
import struct

import hid

from Receiver import Receiver


INPUT_FIELDS = ("hdr", "seed", "key1", "key2", "incr", "axis", "jog", "chksm")

# keycap name to key code
KEYNAMES = {
    "Reset": 0x01,
    "Stop": 0x02,
    "StartPause": 0x03,
    "Feed+": 0x04,
    "Feed-": 0x05,
    "Spindle+": 0x06,
    "Spindle-": 0x07,
    "M-Home": 0x08,
    "Safe-Z": 0x09,
    "W-Home": 0x0a,
    "S-on/off": 0x0b,
    "Fn": 0x0c,
    "Probe-Z": 0x0d,
    "Continuous": 0x0e,
    "Step": 0x0f,
    "Macro-1": 0x04,
    "Macro-2": 0x05,
    "Macro-3": 0x06,
    "Macro-4": 0x07,
    "Macro-5": 0x08,
    "Macro-6": 0x09,
    "Macro-7": 0x0a,
    "Macro-8": 0x0b,
    "Macro-9": 0x0d,
    "Macro-10": 0x10,
}

KEYMAP = {
    0x00: [
        None,
        "Reset",
        "Stop",
        "StartPause",
        "Feed+",
        "Feed-",
        "Spindle+",
        "Spindle-",
        "M-Home",
        "Safe-Z",
        "W-Home",
        "S-on/off",
        "Fn",
        "Probe-Z",
        "Continuous",
        "Step"
    ],
    0x0c: [
        None,
        None,
        None,
        None,
        "Macro-1",
        "Macro-2",
        "Macro-3",
        "Macro-4",
        "Macro-5",
        "Macro-6",
        "Macro-7",
        "Macro-8",
        None,
        "Macro-9",
        None,
        None,
        "Macro-10"
    ]
}

AXIS = {
    0x00: "Noop",
    0x06: "Off",
    0x11: "X",
    0x12: "Y",
    0x13: "Z",
    0x14: "A",
    0x15: "B",
    0x16: "C",
}

INCR = {
    'Step': {
        0x00: None,
        0x0d: 0.001,
        0x0e: 0.01,
        0x0f: 0.1,
        0x10: 1.0,
        0x1a: 5.0,
        0x1b: 10.0,
        0x9b: "Lead"
    },
    'Continuous': {
        0x00: None,
        0x0d: .02,
        0x0e: .05,
        0x0f: .10,
        0x10: .30,
        0x1a: .60,
        0x1b: 1.0,
        0x9b: "Lead"
    }
}


class MotionMode():
    CONT = 0x00
    STEP = 0x01
    MPG = 0x02
    PCT = 0x03


class CoordinateSpace():
    MACHINE = 0
    WORKPIECE = 1


class Pendant(Receiver):
    VENDOR_ID = 0x10ce
    PRODUCT_ID = 0xeb93

    NULL_INPUT_PACKET = bytes([0x06, 0, 0, 0, 0, 0, 0, 0])

    MODE_MAP = {
        KEYNAMES['Continuous']: MotionMode.CONT,
        KEYNAMES['Step']: MotionMode.STEP
    }

    @staticmethod
    def _makeDisplayCommand(motionMode=0,
                            coordinateSpace=0,
                            coordinate1=0,
                            coordinate2=0,
                            coordinate3=0,
                            feedrate=0,
                            spindleSpeed=0,
                            reset=0):
        """????

          If the axis knob is in the "Off" position, then the coordinate lines
           are not updated.
          ????
        """
        #### TODO validate inputs
        HEADER = 0xfdfe
        seed = 0x12  #### FIXME figure this out
        flags = ((coordinateSpace << 7) & 0x80) | ((reset << 6) & 0x40) | (motionMode & 0x03)
        fractSign = lambda v: (abs(int(v)), (((v < 0) << 15) | (int((str(v).split('.')[1] + "0000")[:4]) & 0x7fff))) if v else (0, 0)
        dispCmd = struct.pack("HBBHHHHHHHH",
                              HEADER,
                              seed,
                              flags,
                              *fractSign(coordinate1),
                              *fractSign(coordinate2),
                              *fractSign(coordinate3),
                              feedrate,
                              spindleSpeed)
        logging.debug(f"dispCmd: {[hex(x) for x in dispCmd]}")
        return dispCmd

    def __init__(self):
        self.motionMode = None

        self.deviceInfo = hid.enumerate(Pendant.VENDOR_ID, Pendant.PRODUCT_ID)
        if len(self.deviceInfo) > 1:
            logging.warning("More than one XHC pendant receiver found")
        # N.B. use the first unit if there are more than one
        self.device = hid.Device(path=self.deviceInfo[0]['path'])
        if self.device.manufacturer != 'KTURT.LTD':
            raise Exception(f"Invalid pendent receiver device: {self.device.manufacturer}")
        super().__init__(name="Pendant")
        self._reset()

    def _reset(self):
        """Issue command to bring pendant out of reset

         Set the RESET flag (leave other flags 0), then wait for motion mode
          button to be pressed (ignore other inputs), then clear RESET flag
          and set display to the current values.
         N.B. The coordinate display values are retained across power cycle
          events until updated by inputs from the Controller.
        """
        self.sendOutput(Pendant._makeDisplayCommand(reset=1))
        while True:
            inputVals = self._receive()['data']
            if inputVals and inputVals['key2'] == 0x00 and inputVals['key1'] in Pendant.MODE_MAP.keys():
                break
        self.sendOutput(Pendant._makeDisplayCommand(motionMode=Pendant.MODE_MAP[inputVals['key1']]))
        logging.info("Reset receiver")

    def _flushInput(self):
        inp = self._rawInputPacket()
        while inp and inp != Pendant.NULL_INPUT_PACKET:
            inp = self._rawInputPacket()
        logging.debug("Input flushed")

    def _rawInputPacket(self, timeout=1000):
        """Read the RF receiver device and return raw input packet.

          Returns: bytes object with all eight bytes of an input packet, or an
                    empty bytes object if read timed out without getting an
                    input packet
        """
        return self.device.read(8, timeout=timeout)

    def _receive(self):
        """Read a raw (unvalidated) input packet from the device, validate it,
            and return a tuple with the input values.

          Input packets should all be eight bytes in length, anything
           less than that is not a valid input packet.

          The last byte of the input packet is a checksum -- but it's unclear
           how it works; have to fix this and validate packets.

          Returns: tuple of signed ints (<key1>, <key2>, <increment>, <axis>, <jogDelta>)
        """
        inputs = {}
        inputPacket = self._rawInputPacket()
        if inputPacket:
            if len(inputPacket) == 8:
                ins = dict(zip(INPUT_FIELDS, struct.unpack("BBBBBBbB", inputPacket)))
                assert ins['hdr'] == 0x04, f"Invalid input packet header {ins['hdr']}"
                #### TODO figure out how their checksum works and validate input packets
            else:
                if len(inputPacket) != 0:
                    logging.warning(f"Invalid packet: {[hex(x) for x in inputPacket] if inputPacket else 'None'}")
            inputs['data'] = ins
        return inputs

    def sendOutput(self, data):
        HDR = bytes([0x06])
        dataPackets = [data[i:i+7] for i in range(0, len(data), 7)]
        dataPackets[-1] += bytes(7 - len(dataPackets[-1]))
        i = 0
        for dataPacket in dataPackets:
            dispPkt = HDR + dataPacket
            self.device.write(dispPkt)
            logging.debug(f"dispPkt[{i}]: {[hex(x) for x in dispPkt]}")
            i += 1
            #### TODO consider a delay here


#
# TEST
#
if __name__ == '__main__':
    #### FIXME add real tests
    print("Start")
    p = Pendant()
    p.start()
    while True:
        ins = p.getInput()['data']
        print("Input:", ins)
        if ins['key1'] == 2 and ins['key2'] == 0:
            break
    p.shutdown()
    print("Done")

