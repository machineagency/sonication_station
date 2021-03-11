#!/usr/bin/env python3
"""Driver for Controlling Jubilee"""
#import websocket # for reading the machine model
import requests # for issuing commands
import json
import time
import curses
import pprint
from inpromptu import Inpromptu, cli_method
from functools import wraps

#TODO: Figure out how to print error messages from the Duet.

class MachineStateError(Exception):
    """Raise this error if the machine is in the wrong state to perform such a command."""
    pass

def machine_is_homed(func):
    @wraps(func) # We need this for @cli_method to work
    def homing_check(self, *args, **kwds):
        # Check the cached value if one exists.
        if self.axes_homed and all(self.axes_homed):
            return func(self, *args, **kwds)
        # Request homing status from the object model if not known.
        self.axes_homed = json.loads(self.gcode("M409 K\"move.axes[].homed\""))["result"][:4]
        if not all(self.axes_homed):
            raise MachineStateError("Error: machine must first be homed.")
        return func(self, *args, **kwds)
    return homing_check


class JubileeMotionController(Inpromptu):
    """Driver for sending motion cmds and polling the machine state."""

    LOCALHOST = "127.0.0.1"

    def __init__(self, address=LOCALHOST, debug=False, simulated=False, reset=False):
        """Start with sane defaults. Setup command and subscribe connections."""
        super().__init__()
        if address != self.__class__.LOCALHOST:
            print("Warning: disconnecting this application from the network will halt connection to Jubilee.")
        self.address = address
        self.debug = debug
        self.simulated = simulated
        self.model_update_timestamp = 0
        self.command_ws = None
        self.wake_time = None # Next scheduled time that the update thread updates.
        self.absolute_moves = True
        self._active_tool_index = None # Cached value under the @property.
        self._tool_z_offsets = None # Cached value under the @property.
        self._axis_limits = None # Cached value under the @property.
        self.axes_homed = [False]*4 # Starter value before connecting.
        self.connect()
        if reset:
            self.reset() # also does a reconnect.
        self._set_absolute_moves(force=True)


    def connect(self):
        """Connect to Jubilee over http."""
        if self.simulated:
            return
        # Do the equivalent of a ping to see if the machine is up.
        if self.debug:
            print(f"Connecting to {self.address} ...")
        try:
            # "Ping" the machine by updating the only cacheable information we care about.
            self.axes_homed = json.loads(self.gcode("M409 K\"move.axes[].homed\"", timeout=1))["result"][:4]

            # These data members are tied to @properties of the same name
            # without the '_' prefix.
            # Upon reconnecting, we need to flag that the @property must
            # refresh; otherwise we will retrieve old values that may be invalid.
            self._active_tool_index = None
            self._tool_z_offsets = None
            self._axis_limits = None

            # To save time upon connecting, let's just hit the API on the
            # first try for all the @properties we care about.
            self.active_tool_index
            self.tool_z_offsets
            self.axis_limits
            #pprint.pprint(json.loads(requests.get("http://127.0.0.1/machine/status").text))
            # TODO: recover absolute/relative from object model instead of enforcing it here.
            self._set_absolute_moves(force=True)
        except json.decoder.JSONDecodeError as e:
            raise MachineStateError("DCS not ready to connect.") from e
        except requests.exceptions.Timeout as e:
            raise MachineStateError("Connection timed out. URL may be invalid, or machine may not be connected to the network.") from e
        if self.debug:
            print("Connected.")


    def gcode(self, cmd: str = "", timeout: float = None):
        """Send a GCode cmd; return the response"""
        if self.debug or self.simulated:
            print(f"sending: {cmd}")
        if self.simulated:
            return None
        # RRF3 Only
        response = requests.post(f"http://{self.address}/machine/code", data=f"{cmd}", timeout=timeout).text
        if self.debug:
            print(f"received: {response}")
            #print(json.dumps(r, sort_keys=True, indent=4, separators=(',', ':')))
        return response


    def download_file(self, filepath: str = None, timeout: float = None):
        """Download the file into a file object. Full filepath must be specified.
        Example: /sys/tfree0.g
        """
        # RRF3 Only
        file_contents = requests.get(f"http://{self.address}/machine/file{filepath}",
                                     timeout=timeout).text
        return file_contents


    @cli_method
    def reset(self):
        """Issue a software reset."""
        # End the subscribe thread first.
        self.gcode("M999") # Issue a board reset. Assumes we are already connected
        self.axes_homed = [False]*4
        self.disconnect()
        print("Reconnecting...")
        for i in range(10):
            time.sleep(1)
            try:
                self.connect()
                return
            except MachineStateError as e:
                pass
        raise MachineStateError("Reconnecting failed.")


    @cli_method
    def home_all(self):
        # Having a tool is only possible if the machine was already homed.
        if self.active_tool_index != -1:
            self.park_tool()
        self.gcode("G28")
        self._set_absolute_moves(force=True)
        # Update homing state. Do not query the object model because of race condition.
        self.axes_homed = [True, True, True, True] # X, Y, Z, U


    @cli_method
    def home_xyu(self):
        """Home the XY axes.
        Home Y before X to prevent possibility of crashing into the tool rack.
        """
        self.gcode("G28 Y")
        self.gcode("G28 X")
        self.gcode("G28 U")
        self._set_absolute_moves(force=True)
        # Update homing state. Pull Z from the object model which will not create a race condition.
        z_home_status = json.loads(self.gcode("M409 K\"move.axes[].homed\""))["result"][2]
        self.axes_homed = [True, True, z_home_status, True]


    @cli_method
    def home_z(self):
        """Home the Z axis.
        Note that the Deck must be clear first.
        """
        response = input("Is the Deck free of obstacles? [y/n]")
        if response.lower() in ["y", "yes"]:
            self.gcode("G28 Z")
        self._set_absolute_moves(force=True)


    @cli_method
    def home_in_place(self, *args: str):
        """Set the current location of a machine axis or axes to 0."""
        for axis in args:
            if axis.upper() not in ['X', 'Y', 'Z', 'U']:
                raise TypeError(f"Error: cannot home unknown axis: {axis}.")
            self.gcode(f"G92 {axis.upper()}0")


    @machine_is_homed
    def _move_xyz(self, x: float = None, y: float = None, z: float = None, wait: bool = False):
        """Move in XYZ. Absolute/relative set externally. Wait until done."""
        # TODO: find way to recover from out-of-bounds move requests.

        x_movement = f"X{x} " if x is not None else ""
        y_movement = f"Y{y} " if y is not None else ""
        z_movement = f"Z{z} " if z is not None else ""
        if x_movement or y_movement or z_movement:
            self.gcode(f"G0 {x_movement}{y_movement}{z_movement}F13000")
        if wait:
            self.gcode(f"M400")

    def _set_absolute_moves(self, force: bool = False):
        if self.absolute_moves and not force:
            return
        self.gcode("G90")
        self.absolute_moves = True


    def _set_relative_moves(self, force: bool = False):
        if not self.absolute_moves and not force:
            return
        self.gcode("G91")
        self.absolute_moves = False


    def move_xyz_relative(self, x: float = None, y: float = None, z: float = None, wait: bool = False):
        """Do a relative move in XYZ."""
        self._set_relative_moves()
        self._move_xyz(x, y, z, wait)


    @cli_method
    def move_xyz_absolute(self, x: float = None, y: float = None, z: float = None, wait: bool = False):
        """Do an absolute move in XYZ."""
        # TODO: use push and pop sematics instead.
        self._set_absolute_moves()
        self._move_xyz(x, y, z, wait)


    @property
    @cli_method
    def position(self):
        """Returns the machine control point in mm."""
        # Axes are ordered X, Y, Z, U, E, E0, E1, ... En, where E is a copy of E0.
        response_chunks = self.gcode("M114").split()
        positions = [float(a.split(":")[1]) for a in response_chunks[:3]]
        return positions


    @cli_method
    def pickup_tool(self, tool_index: int):
        """Pick up the tool specified by tool index."""
        if tool_index < 0:
            return
        self.gcode(f"T{tool_index}")
        # Update the cached value to prevent read delays.
        self._active_tool_index = tool_index


    @cli_method
    def park_tool(self):
        """Park the current tool."""
        self.gcode("T-1")
        # Update the cached value to prevent read delays.
        self._active_tool_index = -1


    @property
    @cli_method
    def active_tool_index(self):
        """Return the index of the current tool."""
        if self._active_tool_index is None: # Starting from a fresh connection.
            try:
                response = self.gcode("T")
                # On HTTP Interface, we get a string instead of -1 when there are no tools.
                if response.startswith('No tool'):
                    return -1
                # On HTTP Interface, we get a string instead of the tool index.
                elif response.startswith('Tool'):
                    # Recover from the string: 'Tool X is selected.'
                    self._active_tool_index = int(response.split()[1])
                else:
                    self._active_tool_index = int(response)
            except ValueError as e:
                print("Error occurred trying to read current tool!")
                raise e
        # Return the cached value.
        return self._active_tool_index

    @property
    @cli_method
    def tool_z_offsets(self):
        """Return (in tool order) a list of tool's z offsets"""
        # Starting from fresh connection, query from the Duet.
        if self._tool_z_offsets is None:
            try:
                response = json.loads(self.gcode("M409 K\"tools\""))["result"]
                #pprint.pprint(response)
                self._tool_z_offsets = [] # Create a fresh list.
                for tool_data in response:
                    tool_z_offset = tool_data["offsets"][2] # Pull Z axis
                    self._tool_z_offsets.append(tool_z_offset)
            except ValueError as e:
                print("Error occurred trying to read z offsets of all tools!")
                raise e
        # Return the cached value.
        return self._tool_z_offsets


    @property
    @cli_method
    def axis_limits(self):
        """Return (in XYZU order) a list of tuples specifying (min, max) axis limit"""
        # Starting from fresh connection, query from the Duet.
        if self._axis_limits is None:
            try:
                response = json.loads(self.gcode("M409 K\"move.axes\""))["result"]
                #pprint.pprint(response)
                self._axis_limits = [] # Create a fresh list.
                for axis_data in response:
                    axis_min = axis_data["min"]
                    axis_max = axis_data["max"]
                    self._axis_limits.append((axis_min, axis_max))
            except ValueError as e:
                print("Error occurred trying to read axis limits on each axis!")
                raise e
        # Return the cached value.
        return self._axis_limits

    @cli_method
    @machine_is_homed
    def keyboard_control(self, prompt: str = "=== Manual Control ==="):
        """Use keyboard input to move the machine in steps.
        ↑ = forwards (-Y)
        ← = left (+X)
        → = right (-X)
        ↓ = backwards (+Y)
        w = tool tip up (+Z)
        s = tool tip down (-Z)
        [ = decrease movement step size
        ] = increase movement step size
        """
        min_step_size = 0.015625
        max_step_size = 8.0
        step_size = 1

        stdscr = curses.initscr()
        curses.cbreak()
        curses.noecho()
        stdscr.keypad(True)

        stdscr.addstr(0,0, prompt)
        stdscr.addstr(2,0,"Press 'q' to quit.")
        stdscr.addstr(3,0,"Commands:")
        stdscr.addstr(4,0,"  Arrow keys for XY; '[' and ']' to increase movement step size")
        stdscr.addstr(5,0,"  '[' and ']' to decrease/increase movement step size")
        stdscr.addstr(6,0,"  's' and 'w' to lower/raise z")
        stdscr.addstr(7,0,f"Step Size: {step_size:<8}")
        stdscr.refresh()

        key = ''
        try:
            while key != ord('q'):
                key = stdscr.getch()
                stdscr.refresh()
                if key == curses.KEY_UP:
                    self.move_xyz_relative(y=-step_size)
                elif key == curses.KEY_DOWN:
                    self.move_xyz_relative(y=step_size)
                elif key == curses.KEY_LEFT:
                    self.move_xyz_relative(x=step_size)
                elif key == curses.KEY_RIGHT:
                    self.move_xyz_relative(x=-step_size)
                elif key == ord('w'):
                    self.move_xyz_relative(z=step_size)
                elif key == ord('s'):
                    self.move_xyz_relative(z=-step_size)
                elif key == ord('['):
                    step_size = step_size/2.0
                    if step_size < min_step_size:
                        step_size = min_step_size
                    stdscr.addstr(7,0,f"Step Size: {step_size:<8}")
                elif key == ord(']'):
                    step_size = step_size*2.0
                    if step_size > max_step_size:
                        step_size = max_step_size
                    stdscr.addstr(7,0,f"Step Size: {step_size:<8}")
            self.move_xyz_relative(wait=True) # Wait for last move to finish.
        finally:
            curses.nocbreak()
            stdscr.keypad(False)
            curses.echo()
            curses.endwin()
            self._set_absolute_moves(force=True)


    def disconnect(self):
        """Close the connection."""
        # Nothing to do?
        pass


    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.disconnect()


if __name__ == "__main__":
    with JubileeMotionController(simulated=False, debug=False) as jubilee:
        jubilee.cmdloop()
        #jubilee.home_all()
        #jubilee.move_xyz_absolute(z=20)
        #jubilee.move_xyz_absolute(150, 150, wait=True)
        #print("done moving to initial spot.")
        #jubilee.move_xyz_relative(10)
        #jubilee.move_xyz_relative(0, 10)
        #jubilee.move_xyz_relative(-10)
        #jubilee.move_xyz_relative(0, -10)
        #jubilee.move_xyz_absolute(0, 0, wait=True)
        #print("done moving!")
