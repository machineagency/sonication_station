; Engage the toolchanger lock

G91                 ; Set relative mode
G1 U10 F5000 H0     ; Back off the limit switch with a small move
M906 U900           ; Temporarily increase motor current
G1 U180 F5000 H1    ; Perform up to one rotation looking for the torque limit switch
M906 U670           ; Temporarily increase motor current
G90                 ; Set absolute mode
