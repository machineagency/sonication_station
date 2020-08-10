; Jubilee 2.0 Config File

; Networking
M586 P2 S1                              ; Enable Telnet

; Debugging
M929 P"eventlog.txt" S1                 ; Start logging to file eventlog.txt

; General Preferences
M555 P2                                 ; Set Marlin-style output
G21                                     ; Set dimensions to millimetres
G90                                     ; Send absolute coordinates...
M83                                     ; ...but relative extruder moves

; Joints
M584 X0 Y1 Z3:4:5 U2   ; Map Z to drivers 6, 7, 8. Map extruders to 3 and 4. Create Toolchanger Lock axis.

M569 P0 S0                  ; Drive 0 direction | X stepper
M569 P1 S0                  ; Drive 1 direction | Y Stepper

M569 P3 S0                  ; Drive 3 direction | Front Left Z
M569 P4 S0                  ; Drive 4 direction | Front Right Z
M569 P5 S0                  ; Drive 5 direction | Back Z

M569 P2 S1                  ; Drive 2 direction | Toolchanger Actuator

; Joint Kinematics
M669 K1                                 ; CoreXY mode

; Kinematic bed ball locations.
; Locations are extracted from CAD model assuming lower left build plate corner is (0, 0) on a 305x305mm plate.
M671 X297:2.5:150 Y313.5:313.5:-16.5 S10 ; Front Left: (297.5, 313.5) | Front Right: (2.5, 313.5) | Back: (150, -16.5)


; Axis and Motor Configuration
M350 X16 Y16 Z16 U2 I1                   ; Set 16x microstepping for xyz , 2x for toolchanger lock. Use interpolation.
M906 X1950 Y1950 Z1600                   ; Motor currents (mA)
M906 U1000 I70                           ; StepperOnline Toolchanger Elastic Lock Motor current and idle motor percentage. Do not lower idle current.
M201 X1000 Y1000 Z20 U1000               ; Accelerations (mm/s^2)
M203 X13000 Y13000 Z800 U10000           ; Maximum speeds (mm/min). Conservative to ensure steps aren't lost when carrying tools.
M566 X1000 Y1000 Z2 U200                 ; Maximum jerk speeds mm/minute
M92 X200 Y200                            ; Steps/mm for X,Y
M92 U5.7575                              ; formerly 11.515 ; Steps/deg for U from (200 * 4 * 5.18)/360
M92 Z3200                                ; Steps/mm for Z for a 2mm pitch leadscrew, 0.9mm stepper. (16 * 400)/2

; Homing Switch Configuration
M574 X1 S1 P"^io0.in"                    ; configure homing switch X1 = low-end, S1 = active-high (NC), ^ =  use pullup
M574 Y1 S1 P"^io1.in"                    ; configure homing switch Y1 = low-end, S1 = active-high (NC), ^ =  use pullup
; Z Homing specified in M558 command
M574 U1 S1 P"^io3.in"                    ; configure homing switch U1 = low-end, S1 = active-high (NC), ^ =  use pullup

; Set axis software limits and min/max switch-triggering positions.
; Adjusted such that (0,0) lies at the lower left corner of a 300x300mm square in the 305mmx305mm build plate.
M208 X-13.75:313.75 Y-44:341 Z-0.2:305
M208 U0:200                                 ; Set Elastic Lock (U axis) max rotation angle

; Z probing settings
M558 P5 C"^io2.in" H20 A1 T10000  S0.02
; P5 --> probe type: filtered digital input
; C"^io2.in" --> endstop number
; H5 --> dive height
; A1 --> max number of times to probe
; T100000 --> travel speed between probe points
; S0.02 --> tolerance when probing multiple times

M501                                    ; Load saved parameters from non-volatile memory


; Tool definitions
M563 P0 S"Camera"                    ; Define tool 0
G10 P0 Y44 Z-20                          ; Set tool 0 offset from the bed. These will be different for everyone.

M563 P1 S"Sonicator"                      ; Define tool 1
G10 P1 Y37 Z-150                           ; Set tool 1 offset from the bed. These will be different for everyone.
