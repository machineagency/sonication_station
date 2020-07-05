; tfree1.g
; Runs at the start of a toolchange if the current tool is tool-0.
; Note: tool offsets are applied at this point unless we preempt commands with G53!

M208 Z-0.2:305               ; Reclaim full travel region
G53 G0 X150 Y290 F10000      ; Rapid to the approach position with tool-0. (park_x, park_y - offset)
                             ; This position must be chosen such that the most protruding y point of the current tool
                             ; (while on the carriage) does not collide with the most protruding y point of any parked tool.
G53 G1 Y335 F6000            ; Controlled move to the park position with tool-0. (park_x, park_y)
M98 P"/macros/tool_unlock.g" ; Unlock the tool
G53 G1 Y310 F6000            ; Retract the pin.
;G1 Y290 F6000                ; Move to a safe place to save the position (with offsets applied but without the tool).
G60 S2               	     ; Save this position with tool offsets applied.
                             ; DSF will apply a "G1 R2 X0 Y0 Z0" immediately after this.
