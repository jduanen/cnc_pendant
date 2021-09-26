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

# keycap name to key code map
KEYNAMES_MAP = {
    "Reset": 0x01,
    "Stop": 0x02,
    "StartPause": 0x03,
    "Macro-1": 0x04,
    "Macro-2": 0x05,
    "Macro-3": 0x06,
    "Macro-4": 0x07,
    "Macro-5": 0x08,
    "Macro-6": 0x09,
    "Macro-7": 0x0a,
    "Macro-8": 0x0b,
    "Fn": 0x0c,
    "Macro-9": 0x0d,
    "Macro-10": 0x10,
    "Feed+": 0x04,
    "Feed-": 0x05,
    "Spindle+": 0x06,
    "Spindle-": 0x07,
    "M-Home": 0x08,
    "Safe-Z": 0x09,
    "W-Home": 0x0a,
    "S-on/off": 0x0b,
    "Probe-Z": 0x0d,
    "Continuous": 0x0e,
    "Step": 0x0f,
}

KEYMAP = (
    None,
    "Reset",
    "Stop",
    "StartPause",
    "Macro-1",
    "Macro-2",
    "Macro-3",
    "Macro-4",
    "Macro-5",
    "Macro-6",
    "Macro-7",
    "Macro-8",
    "Fn",
    "Macro-9",
    "Continuous",
    "Step",
    "Macro-10"
)

FN_KEYMAP = (
    None,
    "PendantReset",     # N.B. my definition
    "ApplicationExit",  # N.B. my definition
    "StartPause",
    "Feed+",
    "Feed-",
    "Spindle+",
    "Spindle-",
    "M-Home",
    "Safe-Z",
    "W-Home",
    "S-on/off",
    None,
    "Probe-Z",
    None,
    "Continuous",
    "Step"
)

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


class AxisMode():
    OFF = 0
    XYZ = 1
    ABC = 2


class MotionMode():
    CONT = 0x00  # Continuous -- 'CON:<xxx>%'
    STEP = 0x01  # Step -- 'STP: <x.xxxx>'
    MPG = 0x02   # Manual Pulse Generator -- Not implemented
    PCT = 0x03   # Percent -- Not implemented


class CoordinateSpace():
    #### FIXME figure out which of these is correct
    MACHINE = 0    # aka Absolute Positioning
    WORKPIECE = 1  # aka Relative Positioning


class Pendant(Receiver):
    """Object that encapsulates the XHC WHB04B-4 pendant's USB receiver
    """
    DEF_MOTION_MODE = MotionMode.STEP

    VENDOR_ID = 0x10ce
    PRODUCT_ID = 0xeb93

    NULL_INPUT_PACKET = bytes([0x06, 0, 0, 0, 0, 0, 0, 0])

    MODE_MAP = {
        KEYNAMES_MAP['Continuous']: MotionMode.CONT,
        KEYNAMES_MAP['Step']: MotionMode.STEP
    }

    INCR = {
        MotionMode.STEP: {
            0x00: None,
            0x0d: 0.001,
            0x0e: 0.01,
            0x0f: 0.1,
            0x10: 1.0,
            0x1a: 5.0,
            0x1b: 10.0,
            0x9b: "Lead"
        },
        MotionMode.CONT: {
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

          The flags byte contains four fields:
            * relativeCoordinates[7]: set means use 'X1' (Workpiece), clear use 'X' (Machine)
            * reset[6]: display "RESET" if set, motionMode otherwise
            * unknown[5:2]: ?
            * motionMode[1:0]: motionMode

          Inputs:
            motionMode: ?
            coordinateSpace: ?
            coordinate1: ?
            coordinate2: ?
            coordinate3: ?
            feedrate: ?
            spindleSpeed: ?
            reset: ?
        """
        #### TODO validate inputs
        HEADER = 0xfdfe
        seed = 0xfe #0x12  #### FIXME figure this out
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

    def __init__(self, motionMode=DEF_MOTION_MODE):
        """Connect to the USB RF dongle and issue command to bring the pendant
            out of reset.

          Inputs:
            motionMode: ????
        """
        self.deviceInfo = hid.enumerate(Pendant.VENDOR_ID, Pendant.PRODUCT_ID)
        if len(self.deviceInfo) > 1:
            logging.warning("More than one XHC pendant receiver found")
        # N.B. use the first unit if there are more than one
        self.device = hid.Device(path=self.deviceInfo[0]['path'])
        if self.device.manufacturer != 'KTURT.LTD':
            raise Exception(f"Invalid pendent receiver device: {self.device.manufacturer}")
        super().__init__(name="Pendant")
        self.reset(motionMode)

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
        """(Blocking) read a raw (unvalidated) input packet from the device,
            validate it, and return a tuple with the input values.

          Input packets should all be eight bytes in length, anything
           less than that is not a valid input packet.

          The last byte of the input packet is a checksum -- but it's unclear
           how it works; have to fix this and validate packets.

          Returns: input packet represented as a dict with a 'data' key whose
                    whose value consists of a dict with the keys found in
                    INPUT_FIELDS, and each value is a signed int
        """
        while True:
            inputPacket = self._rawInputPacket()
            if inputPacket:
                break
        if len(inputPacket) != 8:
            logging.warning(f"Invalid packet: {[hex(x) for x in inputPacket] if inputPacket else 'None'}")
        ins = dict(zip(INPUT_FIELDS, struct.unpack("BBBBBBbB", inputPacket)))
        assert ins['hdr'] == 0x04, f"Invalid input packet header {ins['hdr']}"
        #### TODO figure out how their checksum works and validate input packets
        return {'data': ins, 'type': "input"}

    def reset(self, motionMode=DEF_MOTION_MODE):
        """????

          N.B. The coordinate display values are retained across power cycle
               events, and stay until updated by inputs from the Controller.
        """
        #### FIXME clean this up
        self.sendOutput(Pendant._makeDisplayCommand(motionMode=motionMode, reset=1))
        self.sendOutput(Pendant._makeDisplayCommand(motionMode=motionMode, reset=0))
        logging.debug("Pendant Reset")

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

    def updateDisplay(self, motionMode, coordinateSpace, coordinates, feedrate, spindleSpeed):
        """????
        """
        assert 0 <= motionMode <= 3, f"Invalid motionMode: {motionMode}"
        assert coordinateSpace == 0 or coordinateSpace == 1, f"Invalid coordinateSpace {coordinateSpace}"
        assert len(coordinates) == 3 and all([isinstance(c, float) for c in coordinates]), f"Invalid coordinates: {coordinates}"
        assert isinstance(feedrate, int) & feedrate >= 0, f"Invalid feedrate: {feedrate}"
        assert isinstance(spindleSpeed, int) and spindleSpeed >= 0, f"Invalid spindleSpeed: {spindleSpeed}"
        self.sendOutput(Pendant._makeDisplayCommand(motionMode,
                                                    coordinateSpace,
                                                    *coordinates,
                                                    feedrate,
                                                    spindleSpeed,
                                                    0))


#
# TEST
#
if __name__ == '__main__':
    import time

    # N.B. hit "stop" to end test
    #### FIXME add real tests
    logging.basicConfig(level="DEBUG",
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    print("Start")
    p = Pendant()
    p.start()
    """
    p.sendOutput(Pendant._makeDisplayCommand(reset=0))
    p.sendOutput(Pendant._makeDisplayCommand(reset=1))
    p.sendOutput(Pendant._makeDisplayCommand(reset=0))
    p.sendOutput(Pendant._makeDisplayCommand(coordinate1=1.0, motionMode=3, feedrate=110))
    p.sendOutput(Pendant._makeDisplayCommand(coordinate1=2.0, motionMode=3))
    p.sendOutput(Pendant._makeDisplayCommand(motionMode=3))
    p.sendOutput(Pendant._makeDisplayCommand(motionMode=1))
    p.sendOutput(Pendant._makeDisplayCommand(motionMode=3))
    p.sendOutput(Pendant._makeDisplayCommand(motionMode=1))
    """
    x = 0.0
    m = 0
    while True:
        ins = p.getInput()['data']
        print("Input:", ins)
        if ins['key1'] == 2 and ins['key2'] == 0:
            break
        if ins['key1'] == 4 and ins['key2'] == 0:
            print("===> 0")
            p.sendOutput(Pendant._makeDisplayCommand(motionMode=0))
        if ins['key1'] == 5 and ins['key2'] == 0:
            print("===> 1")
            p.sendOutput(Pendant._makeDisplayCommand(motionMode=1))
        if ins['key1'] == 6 and ins['key2'] == 0:
            m = 0
            print(f"===>RRRR: {m}")
            p.reset(m)
        if ins['key1'] == 12 and ins['key2'] == 6:
            m = 1
            print(f"===>RRRR: {m}")
            p.reset(m)
        if ins['key1'] == 7 and ins['key2'] == 0:
            m = 2
            print(f"===>RRRR: {m}")
            p.reset(m)
        if ins['key1'] == 12 and ins['key2'] == 7:
            m = 3
            print(f"===>RRRR: {m}")
            p.reset(m)
        x += 0.1
        p.sendOutput(Pendant._makeDisplayCommand(coordinate1=x, feedrate=int(x*10)))
    print("Shutting down")
    p.shutdown()
    assert p.isShutdown(), "Not shutdown properly"
    print("Done")

