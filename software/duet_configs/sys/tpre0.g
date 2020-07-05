; tpre0.g
; Runs after freeing the previous tool if the next tool is tool-0.
; Note: tool offsets are not applied at this point!

G1 R2 Z0             ; Restore Z position without tools mounted. Do nothing if no prior position was saved.
G0 X305 Y310 F17000  ; Rapid to the approach position without any current tool.
G60 S2               ; Save this position as the reference point from which to later apply new tool offsets.
