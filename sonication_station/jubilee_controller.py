#!/usr/bin/env python3
"""Driver for Controlling Jubilee"""
import websocket # for reading the machine model
import requests # for issuing commands
import json
import time
import curses
import pprint
from threading import Thread, Lock
from inpromptu import Inpromptu, cli_method
from functools import wraps

#TODO: Figure out how to print error messages from the Duet.

class MachineStateError(Exception):
    """Raise this error if the machine is in the wrong state to perform such a command."""
    pass

def machine_is_homed(func):
    @wraps(func) # We need this for @cli_method to work
    def homing_check(self, *args, **kwds):
        if not all([axis['homed'] for axis in self.machine_model['move']['axes']]):
            raise MachineStateError("Error: machine must first be homed.")
        return func(self, *args, **kwds)

    return homing_check

class JubileeMotionController(Inpromptu):
    """Driver for sending motion cmds and polling the machine state."""
    POLL_INTERVAL_S = 0.5 # Interval for updating the machine model.
    SOCKET_ADDRESS = '/var/run/dsf/dcs.sock'
    MM_BUFFER_SIZE = 131072
    SUBSCRIBE_MODE = "Full"

    TIMEOUT_S = 15 # a general timeout
    LOCALHOST = "127.0.0.1"


    def __init__(self, address=LOCALHOST, debug=False, simulated=False, reset=False):
        """Start with sane defaults. Setup command and subscribe connections."""
        super().__init__()
        self.address = address
        self.debug = debug
        self.simulated = simulated
        self.machine_model = {}
        self.model_update_timestamp = 0
        self.command_ws = None
        self.wake_time = None # Next scheduled time that the update thread updates.
        self.state_update_thread = None # The thread.
        self.keep_subscribing = True # bool for keeping the thread alive.
        self.absolute_moves = True
        self.connect()
        if reset:
            self.reset() # also does a reconnect.
        self._set_absolute_moves(force=True)


    def connect(self):
        """Connect to Jubilee over the default unix socket."""
        if self.simulated:
            return
        # Launch the Update Thread.
        self.state_update_thread = \
            Thread(target=self.update_machine_model_worker,
                    name="Machine Model Update Thread",
                    daemon=True)
        self.state_update_thread.start()


    def update_machine_model_worker(self):
        """Thread worker for periodically updating the machine model."""
        if self.simulated:
            return

        # Subscribe to machine model updates
        subscribe_ws = websocket.create_connection(f"ws://{self.address}/machine")
        # Set the wakeup schedule based on the first time we update.
        self.wake_time = time.perf_counter()
        # Do the first update.
        with Lock(): # Lock access to the machine model before updating it.
            self.machine_model = json.loads(subscribe_ws.recv())
        pprint.pprint(self.machine_model)
        self.model_update_timestamp = time.perf_counter()
        # Do scheduled updates on a loop.
        while self.keep_subscribing:
            #print(f"thread woke up at {time.perf_counter()}")
            if self.debug:
                loop_start = time.perf_counter()
            # Acknowledge patch and request more; apply the update
            subscribe_ws.send("OK\n")
            start_time = time.perf_counter()
            machine_model_patch = json.loads(subscribe_ws.recv())
            if self.debug:
                pprint.pprint(machine_model_patch)
            self.apply_patch(machine_model_patch)
            self.model_update_timestamp = time.perf_counter()
            # TODO: only update if there is actual data.
            with Lock(): # Lock access to the machine model.
                self.machine_model.update(machine_model_patch)
            #if self.debug:
            #    print(f"lock + receive delay: {time.perf_counter() - start_time}")
            # Sleep until next scheduled update time.
            #if self.debug:
            #    print(f"loop time: {time.perf_counter() - loop_start}")
            #    print()
            # Update the next wake time.
            self.wake_time = self.__class__.POLL_INTERVAL_S + self.wake_time
            if time.perf_counter() <= self.wake_time:
                #print(f"thread sleeping. next update time: {self.wake_time}")
                time.sleep(self.wake_time - time.perf_counter())
            else:
                print("Error: thread update speed too fast! Missed update deadline!")

        subscribe_ws.close()


    def apply_patch(self, patch):
        return self._apply_patch(patch, self.machine_model)

    def _apply_patch(self, patch, object_model_ref=None, indentation=0):
        """recursively apply object model patch to the current object model."""
        # Starting case.
        #if indentation == 0:
        #    print("APPLYING PATCH")
        #    print(" "*indentation + f"current_object_model: original.")
        #else:
        #    print(" "*indentation + f"current_object_model: {object_model_ref}")

        if type(patch) == list:
            #print(" "*indentation + f"current_patch (list): {patch}")
            # Check if item was removed from list. If so, take the whole patch.
            if len(patch) < len(object_model_ref):
                # Modify by reference, not by value
                object_model_ref.clear()
                object_model_ref.extend(patch)
                return
            for index, patch_item in enumerate(patch):
                # Add new entries to the list.
                #print(" "*indentation + f"list index: {index} | len(object_model_ref): {len(object_model_ref)}")
                if index >= len(object_model_ref):
                    #print(" "*indentation + f"APPENDING {patch_item} to {object_model_ref}")
                    object_model_ref.append(patch_item)
                    #print(" "*indentation + f"RESULT: {object_model_ref}")
                elif type(patch_item) in [dict, list]:
                    self._apply_patch(patch_item, object_model_ref[index], indentation+4)
                else:
                    # Base case.
                    object_model_ref[index] = patch_item
        elif type(patch) == dict:
            #print(" "*indentation + f"current_patch (dict): {patch}")
            for patch_key in patch.keys():
                if type(patch[patch_key]) == dict:
                    # Add new entries to the dict
                    if patch_key not in object_model_ref:
                        object_model_ref[patch_key] = patch[patch_key]
                    else:
                        self._apply_patch(patch[patch_key], object_model_ref[patch_key], indentation+4)
                elif type(patch[patch_key]) == list:
                    self._apply_patch(patch[patch_key], object_model_ref[patch_key], indentation+4)
                else:
                    # Base case.
                    object_model_ref[patch_key] = patch[patch_key]
        #print(" "*indentation + f"done")



    def gcode(self, cmd: str = ""):
        """Send a GCode cmd; return the response"""
        if self.debug or self.simulated:
            print(f"sending: {cmd}")
        if self.simulated:
            return None
        response = requests.post(f"http://{self.address}/machine/code", data=f"{cmd}").text
        if self.debug:
            print(f"received: {response}")
            #print(json.dumps(r, sort_keys=True, indent=4, separators=(',', ':')))
        return response


    @cli_method
    def reset(self):
        """Issue a software reset."""
        # End the subscribe thread first.
        self.keep_subscribing = False
        self.state_update_thread.join()
        self.keep_subscribing = True
        self.gcode("M999") # Issue a board reset. Assumes we are already connected
        self.disconnect()
        print("Reconnecting...")
        for i in range(10):
            time.sleep(1)
            try:
                self.connect()
                return
            except FileNotFoundError as e:
                pass
        print("Reconnecting failed.")


    @cli_method
    def home_all(self):
        self.gcode("M98 P\"homeall.g\"")
        self._set_absolute_moves(force=True)


    @cli_method
    def home_xyu(self):
        """Home the XY axes.
        Home Y before X to prevent possibility of crashing into the tool rack.
        """
        self.gcode("G28 Y")
        self.gcode("G28 X")
        self.gcode("G28 U")
        self._set_absolute_moves(force=True)


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
            if axis not in ['X', 'Y', 'Z', 'U']:
                raise TypeError(f"Error: cannot home unknown axis: {axis}.")
            self.gcode(f"G92 {axis.upper()}0")


    @machine_is_homed
    def _move_xyz(self, x: float = None, y: float = None, z: float = None, wait: bool = False):
        """Move in XYZ. Absolute/relative set externally. Wait until done."""
        # TODO: find way to recover from out-of-bounds move requests.

        x_movement = f"X{x} " if x is not None else ""
        y_movement = f"Y{y} " if y is not None else ""
        z_movement = f"Z{z} " if z is not None else ""
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
        # TODO: consider replacing with M114.
        # We are assuming axes are ordered X, Y, Z, U.
        tool_offsets = [0, 0, 0]
        if self.active_tool_index != -1: # "-1" is equivalent to "no tools."
            tool_offsets = self.machine_model['tools'][self.active_tool_index]['offsets'][:3]

        axis_info = self.machine_model['move']['axes']
        x = axis_info[0].get('machinePosition', None)
        y = axis_info[1].get('machinePosition', None)
        z = axis_info[2].get('machinePosition', None)

        if x is not None:
            x += tool_offsets[0]
        if y is not None:
            y += tool_offsets[1]
        if z is not None:
            z += tool_offsets[2]

        return x, y, z


    @cli_method
    def pickup_tool(self, tool_index: int):
        """Pick up the tool specified by tool index."""
        if tool_index < 0:
            return
        self.gcode(f"T{tool_index}")


    @cli_method
    def park_tool(self):
        """Park the current tool."""
        self.gcode("T-1")


    @property
    def is_busy(self):
        """Get the high-level status of the machine."""
        #return self.machine_model['state']['status'].lower() == 'busy'
        return self.machine_model['state']['status'].lower() != 'idle'


    @property
    @cli_method
    def active_tool_index(self):
        """Return the index of the current tool."""
        # TODO: consider replacing with T.
        return self.machine_model['state']['currentTool']


    @cli_method
    def show_machine_model(self):
        pprint.pprint(self.machine_model)


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
            self.wait_until_idle()
        finally:
            curses.nocbreak()
            stdscr.keypad(False)
            curses.echo()
            curses.endwin()
            self._set_absolute_moves(force=True)


    def wait_until_idle(self, timeout = TIMEOUT_S):
        start_wait_time = time.perf_counter()
        # Wait at least a full update interval to ensure we are polling
        # new data after the move command was sent.
        # Note: we are assuming that if a gcode is acknowledged it immediately
        #       changes from idle to busy if it was not already busy.
        #print(f"start state: {self.machine_model['state']['status'].lower()} | {time.perf_counter():.3f}")
        self._sleep_until_next_update()
        while self.is_busy:
            #print(f"curr state:  {self.machine_model['state']['status'].lower()} | {time.perf_counter():.3f}")
            if time.perf_counter() - start_wait_time > timeout:
                raise RuntimeError("Error: Machine has timed out while waiting for a move to complete.")
            self._sleep_until_next_update()
        #print(f"end state:   {self.machine_model['state']['status'].lower()} | {time.perf_counter():.3f}")


    def _sleep_until_next_update(self):
        """Sleep until we know the machine model has received fresh data."""
        last_model_update = self.model_update_timestamp
        # Sleep at least until the thread is scheduled to update again.
        #print(f"attempting to sleep at {time.perf_counter()}. Will sleep till {self.wake_time}")
        sleep_interval = self.wake_time - time.perf_counter()
        if sleep_interval < 0:
            # Woke up before or during update thread's execution. Sleep again.
            #print(f"  Awoke too early. Will actually sleep till {self.wake_time + self.__class__.POLL_INTERVAL_S}")
            sleep_interval = self.wake_time + self.__class__.POLL_INTERVAL_S - time.perf_counter()
        time.sleep(sleep_interval)
        # Sleep in small increments until the thread has finished the current update.
        while self.model_update_timestamp == last_model_update:
            time.sleep(0.001)


    def disconnect(self):
        """Close the connection."""
        if not self.simulated:
            self.command_ws.close()


    def __enter__(self):
      return self

    def __exit__(self, *args):
      self.disconnect()


if __name__ == "__main__":
    with JubileeMotionController(simulated=False, debug=True) as jubilee:
        jubilee.cmdloop()
