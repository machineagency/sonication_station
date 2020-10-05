; tpost1.g
; called after firmware thinks Tool1 is selected
; Note: tool offsets are applied at this point!

; Note that commands preempted with G53 will NOT apply the tool offset.

G90                          ; Ensure the machine is in absolute mode before issuing movements.
G53 G1 Y339 F6000            ; Move to the pickup position with tool-0.
M98 P"/macros/tool_lock.g"   ; Lock the tool
;M208 Z-0.2:150               ; Apply new Z travel limits based on tool height.
G1 R2 Z0                     ; Restore prior Z position before tool change was initiated.
                             ; Note: tool tip position is automatically saved to slot 2 upon the start of a tool change.
                             ; Restore Z first so we don't crash the tool on retraction.
G1 R0 Y0                     ; Retract tool by restoring Y position next now accounting for new tool offset.
                             ; Restoring Y next ensures the tool is fully removed from parking post.
G1 R0 X0                     ; Restore X position now accounting for new tool offset.

