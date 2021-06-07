# cnc_pendant
Connect an XHC WHB04B pendant to a GRBL-based CNC controller

**TODO**
* Clean this up and add some text about how all this is supposed to work
* Document the code
* Add tests
* Provide pictures and documentation for the HW

**Notes**

- Button Interpretation:
  * Reset: issue a soft reset to the Controller 
    - using '^X' realtime command
  * Stop: stop everything and leave it in position
    - using '!' realtime command
  * Start/Pause: toggle between cycle start and resume
    - using '~' realtime command
  * Feed+/-: adjust feed rate while program is running
  * Spindle+/-: adjust spindle speed while program is running
  * M-Home: stop and home all three axes in machine coordinate space
    - set to machine coordinate space
  * Safe-Z: retract spindle to top of Z axis travel (home Z axis only)
  * W-Home: stop and home all three axes in workpiece coordinate space
  * S-on/off: toggle spindle on/off
  * Probe-Z: run probing cycle
  * Continuous: set into continuous movement mode
    - selected axis will move in direction of jog wheel movement (i.e., cw or ccw)
    - movement will stop whenever wheel movement stops
    - movement is done at the rate given by the increment knob setting
      * i.e., a percentage of max movement rate
    - movement is independent of speed at which the jog wheel is rotated
  * Step: set into step movement mode
    - selected axis will move in direction of jog wheel movement
    - movement is in increments given by the increment knob setting
  * Macro-[1-11]: defined by yaml in button config file

- Adding more increments to the incr knob in step mode: 10.0, 50.0, 100.0
  * ignoring/not implementing the 'Lead' setting

- Reset
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
- Display
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
- Input
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
- always have to click motion mode button after power-on of pendant (i.e., either "Continuous" or "Step")
- need to interogate the Controller to get the current values for the Coordinate
- the -4 pendant only has four values (0x11-0x14), other two values for the -6
- this application should interpret the final three positions of the incr knob as: 10, 50, 100?
- starting up this program will force the pendant into RESET state
  * will have to select motion mode in order to get out of reset
- the input from the pendant and the pendant's display are logically independent
  * it may take some time for the controller to receive inputs from the pendant and send back results that then are sent to the pendant's display
  * everything should converge to a consistent state quickly
