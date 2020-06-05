# Python module intended for interface to the Duet Software Framework
# Copyright (C) 2020 Danal Estes all rights reserved.
# Released under The MIT
#
# As of Jan 2020, functions for interacting with Duet Control Server are implemented,
#  plus a few things specific to the virtual SD config.g
#

import socket
import json
import time
from threading import Thread, Lock

class Jubilee(object):
    POLL_INTERVAL_S = 0.25

    def __init__(self, debug=False):
        self.debug = debug
        self.machine_model = {}
        self.connect()
        self.state_update_thread = \
            Thread(target=self.update_machine_model_worker,
                    name="Machine Model Update Thread",
                    daemon=True).start() # terminate when the main thread exits


    def connect(self):
        """Connect to Jubilee over the default unix socket."""
        self.DCSsock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.DCSsock.connect('/var/run/dsf/dcs.sock')
        self.DCSsock.setblocking(True)
        # Receive response packet with version info.
        version_pkt = self.DCSsock.recv(128).decode()
        if self.debug:
            print(f"received: {version_pkt}")

        # Request to enter command mode
        j=json.dumps({"mode":"command", "version": 8}).encode()
        self.DCSsock.sendall(j)
        r=self.DCSsock.recv(256).decode()
        if self.debug:
            print(f"received: {r}")


    def update_machine_model_worker(self):
        # Subscribe to machine model updates
        print("Subscribing to Machine Model updates.")
        subscribe_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        subscribe_socket.connect('/var/run/dsf/dcs.sock')
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
        with Lock():
            # Do the first update.
            r = subscribe_socket.recv(4096).decode()
            if self.debug:
                print(f"received: subscription 1st response")
            self.machine_model.update(json.loads(r))
        while True:
            with Lock():
                # Acknowledge patch and request more; apply the patch; sleep
                # This whole loop takes time, so we need to measure it such
                # that our poll interval stays constant.
                start_time_s = time.perf_counter()
                j = json.dumps({"command": "Acknowledge"}).encode()
                subscribe_socket.sendall(j)
                # FIXME: Only the first few packets need a rather large buffer.
                r = subscribe_socket.recv(16834).decode()
                if self.debug:
                    print(f"received: {r}")
                self.machine_model.update(json.loads(r))
                elapsed_time_s = time.perf_counter() - start_time_s
                if elapsed_time_s < self.__class__.POLL_INTERVAL_S:
                    time.sleep(self.__class__.POLL_INTERVAL_S - elapsed_time_s)


    def disconnect(self):
        """Close the connection."""
        self.DCSsock.close()


    def gCode(self,cmd=''):
        j=json.dumps({"code": cmd,"channel": 0,"command": "SimpleCode"}).encode()
        self.DCSsock.send(j)
        r=self.DCSsock.recv(2048).decode()
        if ('Error' in r):
          print('Error detected, stopping script')
          print(j)
          print(r)
          exit(8)
        return(r)


    def homeXY(self):
        self.gCode("G28 Y")
        self.gCode("G28 X")


    def moveXYAbsolute(self, x=None, y=None):
        x_movement = f"X{x} " if x is not None else ""
        y_movement = f"Y{y} " if y is not None else ""
        self.gCode(f"G0 {x_movement}{y_movement} F10000")


    def getPos(self):
      result = json.loads(self.gCode('M408'))['result']
      pos = json.loads(result)['pos']
      #print('getPos = '+str(pos))
      return pos


    def resetEndstops(self):
      self.gCode('M574 X1 S1 P"nil"')
      self.gCode('M574 Y1 S1 P"nil"')
      self.gCode('M574 Z1 S1 P"nil"')
      self.gCode('M574 U1 S1 P"nil"')
      self.gCode('M558 K0 P5 C"nil"')
      c = open('/opt/dsf/sd/sys/config.g','r')
      for each in [line for line in c if (('M574' in line) or ('M558' in line) or ('G31' in line))]: self.gCode(each)
      c.close()



    def resetAxisLimits(self):
      c = open('/opt/dsf/sd/sys/config.g','r')
      for each in [line for line in c if 'M208' in line]: self.gCode(each)
      c.close()


    def home_in_place(self, *args: str):
        """Set the current location of a machine axis or axes to 0."""
        for axis in args:
            if axis not in ['X', 'Y', 'Z', 'U']:
                raise TypeError(f"Error: cannot home unknown axis: {axis}.")
            self.gCode(f"G92 {axis.upper()}0")


    def __enter__(self):
      return self

    def __exit__(self, *args):
      self.disconnect()


if __name__ == "__main__":
    print("Connecting to Jubilee.")
    with Jubilee(debug=True) as jubilee:
        print("Homing...")
        jubilee.homeXY()
        jubilee.moveXYAbsolute(150, 150)
        print(jubilee.getPos())
        time.sleep(6)

