#!/usr/bin/env python3
"""Driver for Controlling Jubilee"""
import socket
import json
import time
import curses
import readline
from threading import Thread, Lock
from inpromptu import Inpromptu, cli_method

#TODO: Figure out how to print error messages from the Duet.

class JubileeMotionController(Inpromptu):
    """Driver for sending motion cmds and polling the machine state."""
    POLL_INTERVAL_S = 0.4 # Interval for updating the machine model.
    SOCKET_ADDRESS = '/var/run/dsf/dcs.sock'
    MM_BUFFER_SIZE = 131072
    SUBSCRIBE_MODE = "Full"

    MOVE_TIMEOUT_S = 10
    TIMEOUT_S = 10 # a general timeout

    EPSILON = 0.01


    def __init__(self, debug=False, simulated=False, reset=False):
        """Start with sane defaults. Setup command and subscribe connections."""
        super().__init__()
        self.debug = debug
        self.simulated = simulated
        self.machine_model = {}
        self.command_socket = None
        self.wake_time = None # Next scheduled time that the update thread updates.
        self.state_update_thread = None # The thread.
        self.keep_subscribing = True # bool for keeping the thread alive.
        self.absolute_moves = True
        self.connect()
        if reset:
            self.reset() # also does a reconnect.

    def cli(self):
        """Drop the user into a command line interface."""
        self.cmdloop()


    def connect(self):
        """Connect to Jubilee over the default unix socket."""
        if self.simulated:
            return
        self.command_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        #self.command_socket.settimeout(5)
        self.command_socket.connect(self.__class__.SOCKET_ADDRESS)
        self.command_socket.setblocking(True)
        # Receive response packet with version info.
        version_pkt = self.command_socket.recv(128).decode()
        if self.debug:
            print(f"received: {version_pkt}")
        # Request to enter command mode.
        j=json.dumps({"mode":"command", "version": 8}).encode()
        self.command_socket.sendall(j)
        r=self.command_socket.recv(256).decode()
        if self.debug:
            print(f"received: {r}")

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
        subscribe_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        #subscribe_socket.settimeout(5)
        subscribe_socket.connect(self.__class__.SOCKET_ADDRESS)
        subscribe_socket.setblocking(True)
        # Receive response packet with version info.
        version_pkt = subscribe_socket.recv(128).decode()
        if self.debug:
            print(f"received: {version_pkt}")
        # Set the wakeup schedule based on the first time we update.
        self.wake_time = time.perf_counter()
        # Request to enter patch-based subscription mode.
        j=json.dumps({"mode":"subscribe",
                      "version": 8,
                      #"subscriptionMode": "Patch"}).encode()
                      "subscriptionMode": self.__class__.SUBSCRIBE_MODE}).encode()
        subscribe_socket.sendall(j)
        # Do the first update.
        r = subscribe_socket.recv(self.__class__.MM_BUFFER_SIZE).decode()
        with Lock(): # Lock access to the machine model.
            self.machine_model.update(json.loads(r))
        # Do scheduled updates on a loop.
        while self.keep_subscribing:
            #print(f"thread woke up at {time.perf_counter()}")
            if self.debug:
                loop_start = time.perf_counter()
            # Acknowledge patch and request more; apply the patch; sleep
            j = json.dumps({"command": "Acknowledge"}).encode()
            subscribe_socket.sendall(j)
            # TODO: Optimize. If we are in patch mode, only the first few
            #       packets need a big buffer.
            start_time = time.perf_counter()
            try:
                r = subscribe_socket.recv(self.__class__.MM_BUFFER_SIZE).decode()
            except json.decoder.JSONDecodeError:
                print("Buffer too small!")
            with Lock(): # Lock access to the machine model.
                    self.machine_model.update(json.loads(r))
            if self.debug:
                print(f"lock + receive delay: {time.perf_counter() - start_time}")
            # TODO: we need a recursive update here for Patch mode.
            # Sleep until next scheduled update time.
            if self.debug:
                print(f"loop time: {time.perf_counter() - loop_start}")
                print()
            # Update the next wake time.
            self.wake_time = self.__class__.POLL_INTERVAL_S + self.wake_time
            if time.perf_counter() <= self.wake_time:
                #print(f"thread sleeping. next update time: {self.wake_time}")
                time.sleep(self.wake_time - time.perf_counter())
            else:
                # TODO: maybe accumulate or raise an error here?
                print("Error: thread update speed too fast! "
                                   "Missed update deadline!")
        subscribe_socket.shutdown(socket.SHUT_RDWR)
        subscribe_socket.close()


    #@cli_method
    #def print_curr_time_and_wake_time(self):
    #    print(f"curr_time: {time.perf_counter()} | wake time: {self.wake_time}")
    #    print(self.wake_time > time.perf_counter())

    def disconnect(self):
        """Close the connection."""
        if not self.simulated:
            self.command_socket.shutdown(socket.SHUT_RDWR)
            self.command_socket.close()


    def gcode(self, cmd: str = ""):
        """Send a GCode string and wait for reply to ensure it was processed."""
        gcode_packet = {"code": cmd,"channel": 0,"command": "SimpleCode"}
        if self.debug or self.simulated:
            print(f"sending: {gcode_packet}")
        if self.simulated:
            return
        j=json.dumps(gcode_packet).encode()
        self.command_socket.send(j)
        r=self.command_socket.recv(self.__class__.MM_BUFFER_SIZE).decode()
        if ('Error' in r):
            print('Error detected, stopping script')
            print(j)
            print(r)
            exit(8)
        return(r)


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


    def _move_xyz(self, x: float = None, y: float = None, z: float = None,
                wait: bool = True):
        """Move in XYZ. Absolute/relative set externally. Optional: wait until done."""
        # TODO: find way to recover from out-of-bounds move requests.
        # TODO: check if machine is homed first. Bail early if True.

        # TODO: Either start in a state where the machine is not busy so we don't
        #       save the wrong position and accumulate incorrectly OR
        #       track the overall commanded position and compare.
        x_movement = f"X{x} " if x is not None else ""
        y_movement = f"Y{y} " if y is not None else ""
        z_movement = f"Z{z} " if z is not None else ""
        self.gcode(f"G0 {x_movement}{y_movement}{z_movement}F10000")

        if not wait:
            return
        self.wait_until_idle()


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


    def move_xyz_relative(self, x: float = None, y: float = None,
                          z: float = None, wait: bool = True):
        """Do a relative move in XYZ."""
        self._set_relative_moves()
        self._move_xyz(x, y, z, wait=wait)


    @cli_method
    def move_xyz_absolute(self, x: float = None, y: float = None,
                          z: float = None, wait: bool = True):
        """Do an absolute move in XYZ."""
        # TODO: use push and pop sematics instead.
        self._set_absolute_moves()
        self._move_xyz(x, y, z, wait)


    @cli_method
    def get_position(self):
        """Returns the machine control point in mm."""
        # We are assuming axes are ordered X, Y, Z, U. Where is this order defined?
        tool_offsets = [0, 0, 0]
        current_tool = self.machine_model['state']['currentTool']
        if current_tool != -1: # "-1" is equivalent to "no tools."
            tool_offsets = self.machine_model['tools'][current_tool]['offsets'][:3]

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


    def is_busy(self):
        """Get the high-level status of the machine."""
        return self.machine_model['state']['status'].lower() == 'busy'

    @property
    @cli_method
    def curr_tool_index(self):
        """Return the index of the current tool."""
        return self.machine_model['state']['currentTool']



    @cli_method
    def test_square(self):
        self.gcode("G0 X0 Y0", wait=False)
        self.gcode("G0 X20 Y0", wait=False)
        self.gcode("G0 X20 Y20", wait=False)
        self.gcode("G0 X00 Y20", wait=False)
        self.gcode("G0 X0 Y0")

    @cli_method
    def test_circle(self):
        import math
        radius = 10
        center = [150, 150]
        segments = 20
        for i in range(segments):
            x = center[0] + radius * math.cos(i/segments * math.pi * 2)
            y = center[1] + radius * math.sin(i/segments * math.pi * 2)
            #print(f"x: {x} | y: {y}")
            self.move_xyz_absolute(x, y, wait=False)


    @cli_method
    def show_machine_model(self):
        import pprint
        pprint.pprint(self.machine_model)


    @cli_method
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
        stdscr.addstr(1,0,"Press 'q' to quit.")
        stdscr.addstr(2,0,"Commands:")
        stdscr.addstr(3,0,"  Arrow keys for XY; '[' and ']' to increase movement step size")
        stdscr.addstr(4,0,"  '[' and ']' to decrease/increase movement step size")
        stdscr.addstr(5,0,"  's' and 'w' to lower/raise z")
        stdscr.addstr(6,0,f"Step Size: {step_size:<8}")
        stdscr.refresh()

        key = ''
        try:
            while key != ord('q'):
                key = stdscr.getch()
                stdscr.refresh()
                if key == curses.KEY_UP:
                    self.move_xyz_relative(y=-step_size, wait=False)
                elif key == curses.KEY_DOWN:
                    self.move_xyz_relative(y=step_size, wait=False)
                elif key == curses.KEY_LEFT:
                    self.move_xyz_relative(x=step_size, wait=False)
                elif key == curses.KEY_RIGHT:
                    self.move_xyz_relative(x=-step_size, wait=False)
                elif key == ord('w'):
                    self.move_xyz_relative(z=step_size, wait=False)
                elif key == ord('s'):
                    self.move_xyz_relative(z=-step_size, wait=False)
                elif key == ord('['):
                    step_size = step_size/2.0
                    if step_size < min_step_size:
                        step_size = min_step_size
                    stdscr.addstr(6,0,f"Step Size: {step_size:<8}")
                elif key == ord(']'):
                    step_size = step_size*2.0
                    if step_size > max_step_size:
                        step_size = max_step_size
                    stdscr.addstr(6,0,f"Step Size: {step_size:<8}")
            self.wait_until_idle()
        finally:
            curses.nocbreak()
            stdscr.keypad(False)
            curses.echo()
            curses.endwin()

    def wait_until_idle(self, timeout = TIMEOUT_S):
        start_wait_time = time.perf_counter()
        # Wait at least a full update interval to ensure we are polling
        # new data after the move command was sent.
        # Note: we are assuming that if a gcode is acknowledged it immediately
        #       changes from idle to busy if it was not already busy.
        self._sleep_until_next_update()
        self._sleep_until_next_update()
        while self.is_busy():
            if time.perf_counter() - start_wait_time > timeout:
                raise RuntimeError("Error: Machine has timed out while waiting "
                                   "for a move to complete.")
            self._sleep_until_next_update()

    def _sleep_until_next_update(self):
        """Sleep until we know the machine model has received fresh data."""
        #print(f"attempting to sleep at {time.perf_counter()}. Will sleep till {self.wake_time}")
        sleep_interval = self.wake_time - time.perf_counter()
        if sleep_interval < 0:
            # Woke up before or during update thread's execution. Sleep again.
            #print(f"  Awoke too early. Will actually sleep till {self.wake_time + self.__class__.POLL_INTERVAL_S}")
            sleep_interval = self.wake_time + self.__class__.POLL_INTERVAL_S - time.perf_counter()
        # Small delta to guarantee we wakeup after the thread.
        time.sleep(sleep_interval)


    def __enter__(self):
      return self

    def __exit__(self, *args):
      self.disconnect()


if __name__ == "__main__":
    with JubileeMotionController(simulated=True) as jubilee:
        jubilee.cli()
