'''
Library containing definitions relevent to GRBL-based controllers

* List of Supported G-Codes in Grbl v1.1:
  - Non-Modal Commands:
    * G4: dwell for given period (X, U, or P)
    * G10 L2 P?: change G5? work coordinate system origin setting
    * G10 L20 P?: calculated G5? work coordinate system origin
    * G28: return to home -- machine zero (aka machine reference point)
    * G30: return to secondary home position -- machine zero
    * G28.1: change pre-defined machine home position
    * G30.1: change pre-defined secondary machine home position
    * G53: machine coordinate system (MCS), reference machine zero rather than program zero
    * G92: position register, programming of vector from part zero to tool tip
    * G92.1: clear position register
  - Motion Modes:
    * G0: rapid positioning, one to three axis moves
    * G1: linear interpolation between start and end points
    * G2: clockwise circular interpolation
    * G3: counter-clockwise circular interpolation
    * G38.2: probe toward workpiece, stop on contact, signal if failure
    * G38.3: probe toward workpiece, stop on contact
    * G38.4: probe away from workpiece, stop on loss of contact, signal if failure
    * G38.5: probe away from workpiece, stop on loss of contact
    * G80: cancel canned cycle
  - Feed Rate Modes:
    * G93: feedrate per minute
    * G94: fixed cycle, simple cycle, for roughing
  - Unit Modes:
    * G20: inches mode
    * G21: mm mode
  - Distance Modes:
    * G90: absolute mode
    * G91: incremental mode
  - Arc IJK Distance Modes:
    * G91.1: incremental IJK arc mode
  - Plane Select Modes:
    * G17: select XY plane
    * G18: select ZX plane
    * G19: select YZ plane
  - Tool Length Offset Modes:
    * G43.1: dynamic tool length offset
    * G49: tool length offset compensation cancel -- cancels G43 or G44
  - Cutter Compensation Modes:
    * G40: tool radius compensation off -- cancels G41 or G42
  - Coordinate System Modes:
    * G54: Work Coordinate System (WCS) #0
    * G55: Work Coordinate System (WCS) #1
    * G56: Work Coordinate System (WCS) #2
    * G57: Work Coordinate System (WCS) #3
    * G58: Work Coordinate System (WCS) #4
    * G59: Work Coordinate System (WCS) #5
  - Control Modes:
    * G61: exact stop check, modal, can be cancelled with G64
  - Program Flow:
    * M0: pause running program,resumes when resume button pressed 
    * M1: pause running program if stop switch is on, resumes when resume button pressed
    * M2: end the program, restart with Cycle Start command
    * M30*: exchange pallet shuttles and end the program, restart with Cycle Start command
  - Spindle Control:
    * M3: start spindle clockwise
    * M4: start spindle counter-clockwise
    * M5: stop spindle
  - Coolant Control:
    * M7*: turn on mist coolant
    * M8: turn on flood cooland
    * M9: turn off both flood and mist coolant
  - Valid Non-Command Words:
    * F: feed rate, in defined units
    * I: define arc center in X axis for G02 or G03 arc commands
    * J: define arc center in Y axis for G02 or G03 arc commands
    * K: define arc center in Z axis for G02 or G03 arc commands
    * L: fixed cycle loop count; register to edit using G10
    * N: line/block number in program; system parameter to change using G10
    * P: parameter address
    * R: size of arc radius, or retract height
    * S: spindle or surface speed, depending on mode (G97 or G96, respectively)
    * T: tool selection
    * X: absolute or incremental position of X axis
    * Y: absolute or incremental position of Y axis
    * Z: absolute or incremental position of Z axis

* Grbl v1.1 "Dollar" Commands
  - '$$': view settings
  - '$<num>=<val>': set setting number <num> to <val>
  - '$#': view gcode parameters
    * offset values for G5? work coordinates, G28/G30 pre-defined positions, G92 coordinate offset, tool length offsets, and probing
    * persistent -- written to EEPROM when changed
    * responds with e.g.,
      - [G54:4.000,0.000,0.000]
      ...
      - [G59:0.000,0.000,0.000]
      - [G28:1.000,2.000,0.000]
      - [G30:4.000,6.000,0.000]
      - [G92:0.000,0.000,0.000]
      - [TLO:0.000] # tool length offset for default z-axis
      - [PRB:0.000,0.000,0.000:?] # coordinates of last probe cycle, ':1' ending means success, ':0' means failure
  - '$G': view gcode parser state
    * shows modal state, organized by modal groups (modal group, member words) '*' is power-on default
      - Motion Mode: G0*, G1, G2, G3, G38.2, G38.3, G38.4, G38.5, G80
      - Coordinate System Select: G54*, G55, G56, G57, G58, G59
      - Plane Select: G17*, G18, G19
      - 
    * e.g., [GC:G0 G54 G17 G21 G90 G94 M0 M5 M9 T0 S0.0 F500.0]
  - '$I': view build info
    * can be (persistently) modified with '$I=<str>' command
  - '$N<num>': view startup blocks
    * can be (persistently) modified with '$N<num>=<str>' command
  - '$C': toggles check g-code mode on/off
    * process all given g-code, but don't move motors
    * automatically does soft-reset ('^X') when toggled off
  - '$X': kill alarm lock
    * comes up in this state if homing is enabled
    * shouldn't be used as machine doesn't know its position
      - should only use G91 and make short moves
      - do homing cycle asap
    * does not execute startup lines
  - '$H': run homing cycle
    * set G28 or G30 for post-homing start position
      - e.g., manually jog and then use G28.1/G30.1 to save current position
        * then G28/G30 to go there
  - '$J=<cmds>': jog
    * can queue multiple commands in planning buffer
      - queued commands are canceled with feed-hold command ('!')
    * returns 'ok' ack line once command is queued
      - returns 'error' if not valid or exceeds soft-limit
    * jog commands do not change g-code parser state
    * feed rate is interpreted in G94 units per minute
    * must provide one or more axes (i.e., 'X', 'Y', or 'Z') and feed rate ('F')
    * optional: G20 (inch), G21 (mm), G90 (absolute), G91 (incremental), G53 (machine coordinates)
    * example commands: $J=X10.0 Y-1.5 F500
  - '$RST=<char>': restore Grbl settings and data to default values
    * <char> = '$': erase and restore "dollar" ('$$') settings to defaults
    * <char> = '#': erase and zero all G54-G59 work coordinate offsets and G28/G30 positions in EEPROM
      - easy way of clearing coordinate settings
    * <char> = '$': erase and restore all EEPROM settings to defaults
      - includes '$$' and '$#' settings, '$N' startup lines, and '$I' build info string
  - '$SLP': enable sleep mode
    * shut down spindle, coolant, and stepper enable pins
    * block all commands
    * exited by soft-reset or power-cycle
    * part machine in safe location before calling this

* Grbl v1.1 Realtime Commands
  - characteristics
    * execute in O(10)msec
    * single character commands that can be sent at any time
      - no CR/LF required
    * not considered part of the streaming protocol -- independent
      - not queued, executed sequentially
    * tied to corrensponding input pins/buttons
  - '$': help
    * returns list of available commands
      - '[HLP:$$ $# $G $I $N $x=val $Nx=line $J=line $SLP $C $X $H ~ ! ? ctrl-x]'
  - '^X' (0x18): soft-reset
    * halts and resets Grbl without power cycle
    * throws alarm if in motion as position might be lost
      - if not in motion, retains position and don't have to rehome
  - '?': status report query
    * returns runtime data in a status report message
    * doesn't respond during homing cycle or in alarm state
  - '~': cycle start/resume
    * resumes after feed hold and M0 program pauses
      - otherwise ignored 
  - '!': feed hold
    * puts Grbl into suspend/HOLD state
      - if in motion, decelerates and stops
    * works when in IDLE, RUN, or JOG state
      - ignored otherwise
    * does not disable spindle or coolant, only stops motion
  - 0x84: safety door
  - 0x85: jog cancel
    * ignored if not in JOG state
  - 0x90-0x94: feed rate overrides
    * immediately change feed rate
      - doesn't alter rapid rates -- e.g., G0, G28, G30, or jog motions
    * can't be greater than 200%
    * 0x90: 100% of programmed rate
    * 0x91: increase 10%
    * 0x92: decrease 10%
    * 0x93: increase 1%
    * 0x94: decrease 1%
  - 0x95-0x97: rapid overrides
    * immediately change rapid rate
      - only affects rapid rates -- i.e., G0, G28, and G30
    * 0x95: set to 100% (full) rapid rate
    * 0x96: set to 50% of rapid rate
    * 0x97: set to 25% of rapid rate
  - 0x99-0x9D: spindle speed overrides
    * immediately change spindle speed
      - works even if spindle is not enabled at the time
    * can't be greater than 200%
    * 0x99: set to 100% (full) programmed spindle speed
    * 0x9A: increase spindle speed by 10%
    * 0x9B: decrease spindle speed by 10%
    * 0x9C: increase spindle speed by 1%
    * 0x9D: decrease spindle speed by 1%
  - 0x9E: toggle spindle stop
    * only works if machine is in HOLD mode
      - works even if spindle is not enabled at the time
      - ignored if in motion
    * after cycle start spindle state will be restored after 4 secs
    * can change override speed values while the spindle is stopped
  - 0xA0: toggle flood coolant
    * toggles flood coolant on/off
    * can be done any time in IDLE, RUN, or HOLD states
      - ignored otherwise
    * acts like M8/M9, but can be done while running
  - 0xA1: toggle mist coolant
    * toggles mist coolant on/off
      - must be enabled at compile-time, disabled by default
    * can be done any time in IDLE, RUN, or HOLD states
      - ignored otherwise
    * acts like M7/M9, but can be done while running

* Grbl Build Options
  - default enabled
    * V: Variable Spindle -- No, don't have on my X-Carve
    * M: Mist Collant (M7) -- Yes, I'll use as vacuum control
    * C: CoreXY -- ?
    * P: Parking Motion -- ?
    * Z: Homing Force Origin -- ?
    * H: Homing Single Axis Commands -- ?
    * T: Two limit sitches on axis -- Yes
    * A: Allow feed rate overrides in probe cycles -- Yes
    * D: Use spindle direction as enable pin -- ?
    * 0: Spindle enable off when speed is zero -- ?
    * S: Software limit pin debouncing -- ?
    * R: Parking override control -- ?
    * +: Safety door input pin -- No, don't have on my X-Carve
    * 2: Dual axis motors -- ?
  - default disabled
    * *: Resore all EEPROM command -- ?
    * $: Restore EEPROM '$' settings command -- ?
    * #: Resore EEPROM parameter data command -- ?
    * I: Build info write user string command -- ?
    * E: Force sync upon EEPROM write -- ?
    * L: Homing initialization auto-lock -- ?

* Grbl CLI
  - 'ok': command ack at end of execution
  - 'error:<code>': error of type <code> occurred
  - '<...>': enclose status report data
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
    * this is a config.h option
  - '>G54G20:ok': open angle bracket indicates startup line execution
    * 'ok' means it executed correctly -- no new line required
'''

    

from collections import namedtuple
from parse import parse


GRBL_VERSION = "1.1hJDN-0"

GRBL_PROMPT = f"Grbl {GRBL_VERSION} ['$' for help]"

RX_BUFFER_SIZE = 128

# List of supported G-Codes in V1.1
# N.B. M30 and M7 ????
GCODES = {
    'NON_MODAL_CMDS': ["G4", "G10L2", "G10L20", "G28", "G30", "G28.1", "G30.1",
                       "G53", "G92", "G92.1"],
    'MOTION_MODES': ["G0", "G1", "G2", "G3", "G38.2", "G38.3", "G38.4",
                     "G38.5", "G80"],
    'FEED_MODES': (["G93", "G94"]),
    'UNIT_MODES': (["G20", "G21"]),
    'DISTANCE_MODES': ["G90", "G91"],
    'ARC_MODES': ["G91.1"],
    'PLANE_MODES': ["G17", "G18", "G19"],
    'TOOL_LENGTH_MODES': ["G43.1", "G49"],
    'CUTTER_MODES': ["G40"],
    'COORDINATE_MODES': ["G54", "G55", "G56", "G57", "G58", "G59"],
    'CONTROL_MODES': ["G61"],
    'PROGRAM_FLOW': ["M0", "M1", "M2", "M30"],
    'COOLANT_CONTROL': ["M7", "M8", "M9"],
    'SPINDLE_CONTROL': ["M3", "M4", "M5"],
    'NON_CMD_WORDS': ["F", "I", "J", "K", "L", "N", "P", "R", "S", "T", "X",
                      "Y", "Z"]
}

ALL_GCODES = [item for sublist in GCODES.values() for item in sublist]

ALARM_CODES = [
    None,
    ("Hard limit",
     "Hard limit has been triggered. Machine position is likely lost due to sudden halt. Re-homing is highly recommended."),
    ("Soft limit",
     "Soft limit alarm. G-code motion target exceeds machine travel. Machine position retained. Alarm may be safely unlocked."),
    ("Abort during cycle",
     "Reset while in motion. Machine position is likely lost due to sudden halt. Re-homing is highly recommended."),
    ("Probe fail",
     "Probe fail. Probe is not in the expected initial state before starting probe cycle when G38.2 and G38.3 is not triggered and G38.4 and G38.5 is triggered."),
    ("Probe fail",
     "Probe fail. Probe did not contact the workpiece within the programmed travel for G38.2 and G38.4."),
    ("Homing fail",
     "Homing fail. The active homing cycle was reset."),
    ("Homing fail",
     "Homing fail. Safety door was opened during homing cycle."),
    ("Homing fail",
     "Homing fail. Pull off travel failed to clear limit switch. Try increasing pull-off setting or check wiring."),
    ("Homing fail",
     "Homing fail. Could not find limit switch within search distances. Try increasing max travel, decreasing pull-off distance, or check wiring."),
    ("Homing fail",
     "Homing fail. Second dual axis limit switch failed to trigger within configured search distance after first. Try increasing trigger fail distance or check wiring.")
]

ERROR_CODES = [
  None,
  ("Expected command letter",
   "G-code words consist of a letter and a value. Letter was not found."),
  ("Bad number format",
   "Missing the expected G-code word value or numeric value format is not valid."),
  ("Invalid statement",
   "Grbl '$' system command was not recognized or supported."),
  ("Value < 0",
   "Negative value received for an expected positive value."),
  ("Setting disabled",
   "Homing cycle failure. Homing is not enabled via settings."),
  ("Value < 3 usec",
   "Minimum step pulse time must be greater than 3usec."),
  ("EEPROM read fail. Using defaults",
   "An EEPROM read failed. Auto-restoring affected EEPROM to default values."),
  ("Not idle",
   "Grbl '$' command cannot be used unless Grbl is IDLE. Ensures smooth operation during a job."),
  ("G-code lock",
   "G-code commands are locked out during alarm or jog state."),
  ("Homing not enabled",
   "Soft limits cannot be enabled without homing also enabled."),
  ("Line overflow",
   "Max characters per line exceeded. Received command line was not executed."),
  ("Step rate > 30kHz",
   "Grbl '$' setting value cause the step rate to exceed the maximum supported."),
  ("Check Door",
   "Safety door detected as opened and door state initiated."),
  ("Line length exceeded",
   "Build info or startup line exceeded EEPROM line length limit. Line not stored."),
  ("Travel exceeded",
   "Jog target exceeds machine travel. Jog command has been ignored."),
  ("Invalid jog command",
   "Jog command has no '=' or contains prohibited g-code."),
  ("Setting disabled",
   "Laser mode requires PWM output."),
  ("Unsupported command",
   "Unsupported or invalid g-code command found in block."),
  ("Modal group violation",
   "More than one g-code command from same modal group found in block."),
  ("Undefined feed rate",
   "Feed rate has not yet been set or is undefined."),
  ("Invalid gcode ID:23",
   "G-code command in block requires an integer value."),
  ("Invalid gcode ID:24",
   "More than one g-code command that requires axis words found in block."),
  ("Invalid gcode ID:25",
   "Repeated g-code word found in block."),
  ("Invalid gcode ID:26",
   "No axis words found in block for g-code command or current modal state which requires them."),
  ("Invalid gcode ID:27",
   "Line number value is invalid."),
  ("Invalid gcode ID:28",
   "G-code command is missing a required value word."),
  ("Invalid gcode ID:29",
   "G59.x work coordinate systems are not supported."),
  ("Invalid gcode ID:30",
   "G53 only allowed with G0 and G1 motion modes."),
  ("Invalid gcode ID:31",
   "Axis words found in block when no command or current modal state uses them."),
  ("Invalid gcode ID:32",
   "G2 and G3 arcs require at least one in-plane axis word."),
  ("Invalid gcode ID:33",
   "Motion command target is invalid."),
  ("Invalid gcode ID:34",
   "Arc radius value is invalid."),
  ("Invalid gcode ID:35",
   "G2 and G3 arcs require at least one in-plane offset word."),
  ("Invalid gcode ID:36",
   "Unused value words found in block."),
  ("Invalid gcode ID:37",
   "G43.1 dynamic tool length offset is not assigned to configured tool length axis."),
  ("Invalid gcode ID:38",
   "Tool number greater than max supported value."),
]

Setting = namedtuple("Setting", "default name units description")
#### FIXME fix the default values
SETTINGS = {
    0: Setting(0,
               "Step pulse time",
               "microseconds",
               "Sets time length per step. Minimum 3usec."),
    1: Setting(0,
               "Step idle delay",
               "milliseconds",
               "Sets a short hold delay when stopping to let dynamics settle before disabling steppers. Value 255 keeps motors enabled with no delay."),
    2: Setting(0,
               "Step pulse invert",
               "mask",
               "Inverts the step signal. Set axis bit to invert (00000ZYX)."),
    3: Setting(0,
               "Step direction invert",
               "mask",
               "Inverts the direction signal. Set axis bit to invert (00000ZYX)."),
    4: Setting(0,
               "Invert step enable pin",
               "boolean",
               "Inverts the stepper driver enable pin signal."),
    5: Setting(0,
               "Invert limit pins",
               "boolean",
               "Inverts the all of the limit input pins."),
    6: Setting(0,
               "Invert probe pin",
               "boolean",
               "Inverts the probe input pin signal."),
    10: Setting(0,
                "Status report options",
                "mask",
                "Alters data included in status reports."),
    11: Setting(0,
                "Junction deviation",
                "millimeters",
                "Sets how fast Grbl travels through consecutive motions. Lower value slows it down."),
    12: Setting(0,
                "Arc tolerance",
                "millimeters",
                "Sets the G2 and G3 arc tracing accuracy based on radial error. Beware: A very small value may effect performance."),
    13: Setting(0,
                "Report in inches",
                "boolean",
                "Enables inch units when returning any position and rate value that is not a settings value."),
    20: Setting(0,
                "Soft limits enable",
                "boolean",
                "Enables soft limits checks within machine travel and sets alarm when exceeded. Requires homing."),
    21: Setting(0,
                "Hard limits enable",
                "boolean",
                "Enables hard limits. Immediately halts motion and throws an alarm when switch is triggered."),
    22: Setting(0,
                "Homing cycle enable",
                "boolean",
                "Enables homing cycle. Requires limit switches on all axes."),
    23: Setting(0,
                "Homing direction invert",
                "mask",
                "Homing searches for a switch in the positive direction. Set axis bit (00000ZYX) to search in negative direction."),
    24: Setting(0,
                "Homing locate feed rate",
                "mm/min",
                "Feed rate to slowly engage limit switch to determine its location accurately."),
    25: Setting(0,
                "Homing search seek rate",
                "mm/min",
                "Seek rate to quickly find the limit switch before the slower locating phase."),
    26: Setting(0,
                "Homing switch debounce delay",
                "milliseconds",
                "Sets a short delay between phases of homing cycle to let a switch debounce."),
    27: Setting(0,
                "Homing switch pull-off distance",
                "millimeters",
                "Retract distance after triggering switch to disengage it. Homing will fail if switch isn't cleared."),
    30: Setting(0,
                "Maximum spindle speed",
                "RPM",
                "Maximum spindle speed. Sets PWM to 100% duty cycle."),
    31: Setting(0,
                "Minimum spindle speed",
                "RPM",
                "Minimum spindle speed. Sets PWM to 0.4% or lowest duty cycle."),
    32: Setting(0,
                "Laser-mode enable",
                "boolean",
                "Enables laser mode. Consecutive G1/2/3 commands will not halt when spindle speed is changed."),
    100: Setting(0,
                 "X-axis travel resolution",
                 "step/mm",
                 "X-axis travel resolution in steps per millimeter."),
    101: Setting(0,
                 "Y-axis travel resolution",
                 "step/mm",
                 "Y-axis travel resolution in steps per millimeter."),
    102: Setting(0,
                 "Z-axis travel resolution",
                 "step/mm",
                 "Z-axis travel resolution in steps per millimeter."),
    110: Setting(0,
                 "X-axis maximum rate",
                 "mm/min",
                 "X-axis maximum rate. Used as G0 rapid rate."),
    111: Setting(0,
                 "Y-axis maximum rate",
                 "mm/min",
                 "Y-axis maximum rate. Used as G0 rapid rate."),
    112: Setting(0,
                 "Z-axis maximum rate",
                 "mm/min",
                 "Z-axis maximum rate. Used as G0 rapid rate."),
    120: Setting(0,
                 "X-axis acceleration",
                 "mm/sec^2",
                 "X-axis acceleration. Used for motion planning to not exceed motor torque and lose steps."),
    121: Setting(0,
                 "Y-axis acceleration",
                 "mm/sec^2",
                 "Y-axis acceleration. Used for motion planning to not exceed motor torque and lose steps."),
    122: Setting(0,
                 "Z-axis acceleration",
                 "mm/sec^2",
                 "Z-axis acceleration. Used for motion planning to not exceed motor torque and lose steps."),
    130: Setting(0,
                 "X-axis maximum travel",
                 "millimeters",
                 "Maximum X-axis travel distance from homing switch. Determines valid machine space for soft-limits and homing search distances."),
    131: Setting(0,
                 "Y-axis maximum travel",
                 "millimeters",
                 "Maximum Y-axis travel distance from homing switch. Determines valid machine space for soft-limits and homing search distances."),
    132: Setting(0,
                 "Z-axis maximum travel",
                 "millimeters",
                 "Maximum Z-axis travel distance from homing switch. Determines valid machine space for soft-limits and homing search distances.")
}

REALTIME_COMMANDS = {
    'CYCLE_START': 0x7e,    # cycle start ('~')
    'FEED_HOLD': 0x21,      # feed hold ('!')
    'STATUS': 0x3f,         # current status ('?')
    'RESET': 0x18,          # reset GRBL (Ctrl-X)
    'SAFETY_DOOR': 0x84,    # SW equivalent of door switch
    'JOG_CANCEL': 0x85,     # cancels current jog state by Feed Hold and flushes jog commands in buffer
    'FEED_100': 0x90,       # set feed rate to 100% of programmed rate
    'FEED_INCR_10': 0x91,   # increase feed rate by 10% of programmed rate
    'FEED_DECR_10': 0x92,   # decrease feed rate by 10% of programmed rate
    'FEED_INCR_1': 0x93,    # increase feed rate by 1% of programmed rate
    'FEED_DECR_1': 0x94,    # decrease feed rate by 1% of programmed rate
    'RAPID_100': 0x95,      # set rapid rate to full 100% rapid rate
    'RAPID_50': 0x96,       # set rapid rate to 50% of rapid rate
    'RAPID_25': 0x97,       # set rapid rate to 25% of rapid rate
    'TOGGLE_SPINDLE': 0x9e, # toggle spindle enable/disable -- only in HOLD state
    'TOGGLE_FLOOD': 0xa0,   # toggle flood coolant state
    'TOGGLE_MIST': 0xa1     # toggle mist coolant state
}

'''
* Grbl v1.1 "Dollar" Commands that aren't just views (some take args):
  - '$<num>=<val>': set setting number <num> to <val>
  - '$N<num>=<str>': (persistently) modified startup line <num>
  - '$C': toggles check g-code mode on/off
    * returns a startup line (does a soft-reset?), then "[MSG:Enable]"/"[MSG:Disabled]", followed by 'ok'
  - '$X': kill alarm lock
  - '$H': run homing cycle
  - '$J=<cmds>': jog command
  - '$RST=<char>': restore Grbl settings and data to default values
'''
DOLLAR_COMMANDS = {
    'VIEW_SETTINGS': "$",   # view Grbl settings
    'VIEW_PARAMETERS': "#", # view '#' parameters
    'VIEW_PARSER': "G",     # view parser state
    'VIEW_BUILD': "I",      # view build info
    'VIEW_STARTUPS': "N",   # view startup blocks
    'GCODE_MODE': "C",      # check gcode mode
    'KILL_ALARM': "X",      # kill alarm lock
    'RUN_HOMING': "H",      # run homing cycle
    'JOG_COMMAND': "J",     # jog command
    'RESTORE_DATA': "RST",  # restore data
    'SLEEP': "SLP",         # put machine into sleep mode
    'HELP': ""              # print help message -- no command character, just '$'
}

DOLLAR_VIEW_COMMANDS = [s for s in DOLLAR_COMMANDS.keys() if s.startswith('VIEW')]


def alarmDescription(msg, full=True):
    """Take a raw Alarm message from the controller and return its description.
    """
    description = None
    res = parse("ALARM:{num}", msg)
    if res:
        try:
            description = ALARM_CODES[int(res['num'])][1 if full else 0]
        except IndexError:
            pass
    return description

def errorDescription(msg, full=True):
    """Take a raw Error message from the controller and return its description.
    """
    description = None
    res = parse("error:{num}", msg)
    if res:
        try:
            description = ERROR_CODES[int(res['num'])][1 if full else 0]
        except IndexError:
            pass
    return description


class CommandGroups():
    NON_MODAL_CMDS = 0
    MOTION_MODES = 1
    FEED_MODES = 2
    UNIT_MODES = 3
    DISTANCE_MODES = 4
    ARC_MODES = 5
    PLANE_MODES = 6
    TOOL_LENGTH_MODES = 7
    CUTTER_MODES = 8
    COORDINATE_MODES = 9
    CONTROL_MODES = 10
    PROGRAM_FLOW = 11
    COOLANT_CONTROL = 12
    SPINDLE_CONTROL = 13
    NON_CMD_WORDS = 14

COMMAND_GROUP_NAMES = [v for v in dir(CommandGroups) if not v.startswith('__')]


#
# TEST
#
if __name__ == '__main__':
    #### FIXME add real tests
    alarmMsg = "ALARM:5"  # probe fail
    print(alarmDescription(alarmMsg))
    print(alarmDescription(alarmMsg, False))
    print(alarmDescription("ALAR:9"))  # should fail
    errorMsg = "error:13"  # check door
    print(errorDescription(errorMsg))
    print(errorDescription(errorMsg, False))
    print(errorDescription("eror:3"))  # should fail
