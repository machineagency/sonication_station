; tpost0.g
; called after firmware thinks Tool0 is selected
; Note: tool offsets are applied at this point!

; Note that commands preempted with G53 will NOT apply the tool offset.

G53 G1 Y335 F6000            ; Move to the pickup position with tool-0.
M98 P"/macros/tool_lock.g"   ; Lock the tool
G1 R2 Z0                     ; Restore prior position now accounting for new tool offset.
                             ; Restore Z first so we don't crash the tool on retraction.
G53 G1 Y310 F6000            ; Retract the entire tool.
G1 R2 Y0                     ; Restore Y position next now accounting for new tool offset.
                             ; Restoring Y next ensures the tool is fully removed from parking post.
G1 R2 X0                     ; Restore X position now accounting for new tool offset.

M208 Z-0.2:155               ; Shrink travel region to account for large tool length. (305 - tool_height)

