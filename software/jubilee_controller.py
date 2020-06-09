import socket
import json
import time
from threading import Thread, Lock
from introspect_interface import MASH, cli_method

class JubileeController(MASH):
    # Interval for updating the machine model.
    POLL_INTERVAL_S = 0.1
    SOCKET_ADDRESS = '/var/run/dsf/dcs.sock'
    MM_BUFFER_SIZE = 32768


    def __init__(self, debug=False):
        """Start with sane defaults. Setup command and subscribe connections."""
        super().__init__()
        self.debug = debug
        self.machine_model = {}
        self.command_socket = None
        self.connect()
        self.state_update_thread = \
            Thread(target=self.update_machine_model_worker,
                    name="Machine Model Update Thread",
                    daemon=True).start() # terminate when the main thread exits

    def cli(self):
        """Drop the user into a command line interface."""
        self.cmdloop()


    def connect(self):
        """Connect to Jubilee over the default unix socket."""
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
        self.command_socket.close()


    @cli_method
    def gcode(self, cmd: str = ""):
        """Send a string of GCode"""
        j=json.dumps({"code": cmd,"channel": 0,"command": "SimpleCode"}).encode()
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
        self.gcode("G28 Y")
        self.gcode("G28 X")


    @cli_method
    def move_xy_absolute(self, x: float = None, y: float = None):
        x_movement = f"X{x} " if x is not None else ""
        y_movement = f"Y{y} " if y is not None else ""
        self.gcode(f"G0 {x_movement}{y_movement} F10000")

    @cli_method
    def move_xyz_absolute(self, x: float = None, y: float = None, z: float = None):
        x_movement = f"X{x} " if x is not None else ""
        y_movement = f"Y{y} " if y is not None else ""
        z_movement = f"Z{z} " if y is not None else ""
        self.gcode(f"G0 {x_movement}{y_movement}{z_movement}F10000")

    @cli_method
    def test_func(self, z: float = None):
        pass


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


    def __enter__(self):
      return self

    def __exit__(self, *args):
      self.disconnect()


if __name__ == "__main__":
    with JubileeController() as jubilee:
        #jubilee.home_xy()
        jubilee.cli()
