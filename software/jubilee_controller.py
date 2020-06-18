#!/usr/bin/env python3
"""Driver for Controlling Jubilee"""
import socket
import json
import time
#from sys import stdin # alternative to input() for keyboard control
import readline
import getch
from threading import Thread, Lock
from introspect_interface import MASH, cli_method

class JubileeMotionController(MASH):
    """Driver for sending motion cmds and polling the machine state."""
    # Interval for updating the machine model.
    POLL_INTERVAL_S = 0.1
    SOCKET_ADDRESS = '/var/run/dsf/dcs.sock'
    MM_BUFFER_SIZE = 32768


    def __init__(self, debug=False, simulated=False):
        """Start with sane defaults. Setup command and subscribe connections."""
        super().__init__()
        self.debug = debug
        self.simulated = simulated
        self.machine_model = {}
        self.command_socket = None
        self.connect()
        self.state_update_thread = \
            Thread(target=self.update_machine_model_worker,
                    name="Machine Model Update Thread",
                    daemon=True).start() # terminate when the main thread exits
        #TODO: figure out how to get the whole tree of cmds from any attributes
        #      that also inherit from MASH such that we can "cd" into them.

    def cli(self):
        """Drop the user into a command line interface."""
        self.cmdloop()


    def connect(self):
        """Connect to Jubilee over the default unix socket."""
        if self.simulated:
            return
        self.command_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
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


    def update_machine_model_worker(self):
        """Thread worker for periodically updating the machine model."""
        if self.simulated:
            return
        # Subscribe to machine model updates
        subscribe_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        subscribe_socket.connect(self.__class__.SOCKET_ADDRESS)
        subscribe_socket.setblocking(True)
        # Receive response packet with version info.
        version_pkt = subscribe_socket.recv(128).decode()
        if self.debug:
            print(f"received: {version_pkt}")
        # Request to enter patch-based subscription mode.
        j=json.dumps({"mode":"subscribe",
                      "version": 8,
                      "subscriptionMode": "Patch"}).encode()
        subscribe_socket.sendall(j)
        # Do the first update.
        r = subscribe_socket.recv(self.__class__.MM_BUFFER_SIZE).decode()
        if self.debug:
            print(f"received: subscription 1st response")
        with Lock(): # Lock access to the machine model.
            self.machine_model.update(json.loads(r))
        while True:
            # Acknowledge patch and request more; apply the patch; sleep
            # This whole loop takes time, so we need to measure it such
            # that our poll interval stays constant.
            start_time_s = time.perf_counter()
            j = json.dumps({"command": "Acknowledge"}).encode()
            subscribe_socket.sendall(j)
            # TODO: Optimize. Only the first few packets need a big buffer.
            r = subscribe_socket.recv(self.__class__.MM_BUFFER_SIZE).decode()
            if self.debug:
                print(f"received: {r}")
            with Lock(): # Lock access to the machine model.
                try:
                    self.machine_model.update(json.loads(r))
                except json.decoder.JSONDecodeError:
                    print("Buffer too small!")
            elapsed_time_s = time.perf_counter() - start_time_s
            if elapsed_time_s < self.__class__.POLL_INTERVAL_S:
                time.sleep(self.__class__.POLL_INTERVAL_S - elapsed_time_s)


    def disconnect(self):
        """Close the connection."""
        if not self.simulated:
            self.command_socket.close()


    def gcode(self, cmd: str = ""):
        """Send a string of GCode"""
        gcode_packet = {"code": cmd,"channel": 0,"command": "SimpleCode"}
        if self.debug or self.simulated:
            print(f"sending: {gcode_packet}")
        if self.simulated:
            return
        j=json.dumps(gcode_packet.encode())
        self.command_socket.send(j)
        r=self.command_socket.recv(self.__class__.MM_BUFFER_SIZE).decode()
        if ('Error' in r):
          print('Error detected, stopping script')
          print(j)
          print(r)
          exit(8)
        return(r)


    @cli_method
    def home_xy(self):
        """Home the XY axes.
        Home Y before X to prevent possibility of crashing into the tool rack.
        """
        self.gcode("G28 Y")
        self.gcode("G28 X")

    @cli_method
    def home_z(self):
        """Home the Z axis.
        Note that the Deck must be clear first.
        """
        response = input("Is the Deck free of obstacles? [y/n]")
        if response.lower() in ["y", "yes"]:
            self.gcode("G28 Z")


    @cli_method
    def move_xy_absolute(self, x: float = None, y: float = None,
                         wait: bool = True):
        """Do an absolute move in XY."""
        # TODO: check if machine is homed first.
        x_movement = f"X{x} " if x is not None else ""
        y_movement = f"Y{y} " if y is not None else ""
        self.gcode(f"G0 {x_movement}{y_movement} F10000")

    @cli_method
    def move_xyz_absolute(self, x: float = None, y: float = None,
                          z: float = None, wait: bool = True):
        """Do an absolute move in XYZ."""
        # TODO: check if machine is homed first.
        x_movement = f"X{x} " if x is not None else ""
        y_movement = f"Y{y} " if y is not None else ""
        z_movement = f"Z{z} " if y is not None else ""
        self.gcode(f"G0 {x_movement}{y_movement}{z_movement}F10000")


    @cli_method
    def get_pos(self):
      result = self.machine_model['move']['axes']
      x = result[0].get('machinePosition', None)
      y = result[1].get('machinePosition', None)
      z = result[2].get('machinePosition', None)

      x2 = result[0].get('userPosition', None)
      y2 = result[1].get('userPosition', None)
      z2 = result[2].get('userPosition', None)
      #FIXME: actually return this; don't just print it.
      print(f"Current Machine position: X:{x} Y:{y} Z:{z}")
      print(f"Next Machine position: X:{x2} Y:{y2} Z:{z2}")


    @cli_method
    def home_in_place(self, *args: str):
        """Set the current location of a machine axis or axes to 0."""
        for axis in args:
            if axis not in ['X', 'Y', 'Z', 'U']:
                raise TypeError(f"Error: cannot home unknown axis: {axis}.")
            self.gcode(f"G92 {axis.upper()}0")


    #@cli_method
    def print_machine_model(self):
        import pprint
        pprint.pprint(self.machine_model)


    #@cli_method
    def keyboard_control(self):
        """Use keyboard input to move the machine in steps.
        W = forwards (-Y)
        A = left (+X)
        S = right (-X)
        D = backwards (+Y)
        ↑ = tool tip up (+Z)
        ↓ = tool tip down (-Z)
        ← = decrease movement step size
        ↓ = increase movement step size
        """
        #stop = False
        #while not stop:
        #    char = getch.getch()
        #    if char == b'\x1b':
        #        print("received: escape char!")
        #        print(readline.get_line_buffer())
        pass



    def __enter__(self):
      return self

    def __exit__(self, *args):
      self.disconnect()


if __name__ == "__main__":
    with JubileeMotionController(simulated=True) as jubilee:
        #jubilee.home_xy()
        jubilee.cli()
