'''
Object that encapsulates the XHC WHB04B-4 pendant's USB receiver

#### TODO move this to the README.md file
Reset:
  * Pendant comes out of power-up in RESET mode
    - it remembers the last coordinate line values it was given and displays "RESET"
      * remains in this state until overwritten
    - comes up with selected axis as given by axis knob
      * could have changed during power down
  * can change coordinate lines on the display while in reset mode
  * reset sequence on power-up
    - set RESET flag
    - wait for motion mode button to be pressed
      * ignore all other inputs
    - clear RESET flag
  * the pendant remains in the previous coordinate space at startup
    - must get the current coordinates and space from the Controller and update the display on reset
  * pendant emits current state of knobs (and buttons/jog wheel) on power-up
    - not doing anything with it right now
  * sometimes emits a null data packet -- i.e., all zeros (key1, key2, incr, axis, jog)
    - sometimes first thing after powerup is a null packet
    - pendant looks like it continues emitting packets until it is reset

Display:
  * pendant automatically displays the value of the axis knob with an asterix next to a coordinate line
    - host is not able to set the selection marker
  * top display line is the status line RF bars icon, battery level icon, and mode word
    - mode word starts as "RESET" until motion mode button is selected
  * after motion mode is selected, the mode word becomes either "CONT" or "STP"
    - the value following the mode word dependent on the mode
      * for "STP" the value is a floating point number
      * for "CONT" the value is a percentage
  * the display format is specific to the motion mode
    - e.g., "STP: 1.0", "CONT: 30%"
    - both MPG and PCT motion modes display "XX%", where 'XX' is given by the incr knob setting
  * if axis knob is in "off" state, can't update the display
    - don't send display packets if that's the case -- drop commands and log warnings
    - if power on with axis "off", emits axis off (0x06) and state of incr knob
      * could suppress this in this object
    - doesn't automatically update the display if axis is Off
  * the display automatically updates CONT/STEP mode values based on knob positions
  * the coordinate lines diplay the current machine position
    - X, Y, Z or A, B, C coordinates if in Machine coordinate system
    - X1, Y1, Z1 or A1, B1, C1 coordinates if in Work coordinate system
  * the currently selected coordinate (i.e., the one where motion will occur) is (automatically) indicated on the display with an asterix

Input:
  * this object emits the (lightly parsed) basic events from the pendent
    - puts them into an internal queue, provide method to pull from this input queue
    - the action logic (e.g., in the main code body) will pull from this queue via methods
    - an input thread handles device events, does the pre-processing, and queues the output
  * outputs from the pendant include: key1, key2, axis, incr, and jog
    - any number of these can be null in a packet
    - there's also a header, seed, and checksum in each packet
      * these values are not currently being used by this code
      * the header is checked but the checksum is currently not
      * have to figure out what the seed does and how the checksum works
  * button-down events have a key value, then button up events are signified by 0x0 value
    - e.g., pressing a single key results in reports with key1=0x??, then key1=0x00 when it is released
    - e.g., button down will give the keyName, button up returns 'Noop'
  * key1 is the first key pressed, key2 is the second key pressed while key1 is held
    - this means any key can be a modifier -- but only "Fn" is so marked
  * key values are between 0x00 (nothing pressed) and 0x10
    - 0x01 starts in upper left ("Reset") and raster left-right, top-down
    - "Continuous" = 0x0e, "Step" = 0x0f, last key is "Macro-10" = 0x10
  * when the axis knob is in the "off" position, no jog deltas are sent
    - in this case, axis == 0x06 and jog == 0x00 (there's not axis to apply the jog to)
  * all button and knob values are small integers -- except incr "Lead" == 155
  * the pendent emits NOP packets when the axis knob is not set to "Off" and the jog wheel is not moving
    - the pendent continuously sends a jog value of 0
  * the input tuple contains the (possibly empty) name of a pressed key, the current setting of the axis knob,
     the current setting of the increment knob, and the jog wheel delta
  * if no key was pressed, then the key name will be None.
  * if the axis knob is set to "Off" a None is given for the axis value,
     otherwise, the axis character is given as a string -- e.g, "X", or "A".
  * the increment knob returns either a float (that corresponds to the increment to be moved by with each
     click of the jog wheel when in "STEP" mode) or an integer (that corresponds to the percentage of the
     maximum speed at which it can move).
  * reports current axis and incr knob settings
    - axis: 0x06="off"
    - incr: 0x0e=0.001/2%, 0x0d=0.02/5% ...

* N.B.
  - always have to click motion mode button after power-on of pendant
    * i.e., either "Continuous" or "Step"
  - need to interogate the Controller to get the current values for the Coordinate
* the -4 pendant only has four values (0x11-0x14), other two values for the -6
* this application should interpret the final three positions of the incr knob as: 10, 50, 100?

===============================================================
==> I haven't seen "MPG", "F: ?", or "S: ?" displays yet, keep working on it
    Looks like this unit doesn't generate these displays.
'''

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
        self.reset()

    def flushInput(self):
        inp = self._rawInputPacket()
        while inp and inp != Pendant.NULL_INPUT_PACKET:
            inp = self._rawInputPacket()
        logging.debug("Input flushed")

    def reset(self):
        """Issue command to bring pendant out of reset

         Set the RESET flag (leave other flags 0), then wait for motion mode
          button to be pressed (ignore other inputs), then clear RESET flag
          and set display to the current values.
         N.B. The coordinate display values are retained across power cycle
          events until updated by inputs from the Controller.
        """
        self.sendOutput(Pendant._makeDisplayCommand(reset=1))
        inputVals = self._receive()
        while inputVals and inputVals['key2'] == 0x00 and inputVals['key1'] in Pendant.MODE_MAP.keys():
            inputVals = self._receive()
        self.sendOutput(Pendant._makeDisplayCommand(motionMode=Pendant.MODE_MAP[inputVals['key1']]))
        logging.info("Reset receiver")

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
                inputs = dict(zip(INPUT_FIELDS, struct.unpack("BBBBBBbB", inputPacket)))
                assert inputs['hdr'] == 0x04, f"Invalid input packet header {inputs['hdr']}"
                #### TODO figure out how their checksum works and validate input packets
            else:
                if len(inputPacket) != 0:
                    logging.warning(f"Invalid packet: {[hex(x) for x in inputPacket] if inputPacket else 'None'}")
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
    print("Start")
    p = Pendant()
    print("A")
    p.start()
    print("B")
    inp = True
    while inp:
        print("C")
        inp = p.getInput()
        print("INPUT: ", inp)
    p.shutdown()
    print("Done")

