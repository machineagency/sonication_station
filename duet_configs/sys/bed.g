G30 P0 X195 Y40 Z-99999   ; probe near back leadscrew
G30 P1 X240 Y270 Z-99999    ; probe near front left leadscrew
G30 P2 X65 Y270 Z-99999 S3   ; probe near front right leadscrew and calibrate 3 motors
G1 X0 Y0 F10000
