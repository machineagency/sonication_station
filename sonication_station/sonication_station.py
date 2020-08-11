#!/usr/bin/env python3
"""Driver for Controlling Jubilee as a Lab Automation Device"""
import socket
import json
import time
import copy
import pprint
import re
import subprocess, signal, os # for launching/killing video feed
from math import sqrt, acos, asin, cos, sin
from functools import wraps
from threading import Thread, Lock
from inpromptu import cli_method, UserInputError
from jubilee_controller import JubileeMotionController, MachineStateError
from sonicator import Sonicator

# TODO: put stickers on the deck plate to enumerate them.


def protocol_method(func):
    """Mark a function as usable in protocols."""
    func.is_protocol_method = True
    return func

def requires_safe_z(func):
    @wraps(func) # We need this for @cli_method to work
    def safe_z_check(self, *args, **kwds):
        if self.safe_z is None:
            raise MachineStateError("Error: a safe_z height must first be defined before invoking this function.")
        return func(self, *args, **kwds)
    return safe_z_check


def requires_cleaning_station(func):
    @wraps(func) # We need this for @cli_method to work
    def cleaning_station_check(self, *args, **kwds):
        if self.deck_config["cleaning_config"] is None:
            raise MachineStateError("Error: a cleaning station must first be defined before invoking this function.")
        return func(self, *args, **kwds)
    return cleaning_station_check


class SonicationStation(JubileeMotionController):
    """Driver for sending motion cmds and polling the machine state.

    Protocol Methods:
        methods decorated with @protocol_method can be invoked serially from a json file.

    CLI Methods:
        methods decorated with @cli_method are exposed to the prompt-based user interface.
    """

    # Constants and Lookups:
    WELL_COUNT_TO_ROWS = {96: (8, 12),
                          48: (6, 8),
                           6: (2, 3),
                           12: (3, 4)}
    DECK_PLATE_COUNT = 6

    CAMERA_FOCAL_LENGTH_OFFSET = 19

    # TODO: this info should be read from the machine model.
    CAMERA_TOOL_INDEX = 0
    SONICATOR_TOOL_INDEX = 1

    # Blank Configuration Template
    BLANK_DECK_CONFIGURATION = \
        {"plates": {},              # plate type and location, keyed by deck index.
         "safe_z": None,            # retract height before moving around in XY.
         "cleaning_config": None    # specs and protocol for cleaning.
        }

    BLANK_DECK_PLATE_CONFIG = \
        {"id": "",
         "corner_well_centroids": [(None, None), (None, None), (None, None)],
         "well_count": None,
         "liquid_level": {}
        }

    BLANK_CLEANING_CONFIG = \
        {"plates": [],
         "protocol": []
        }

    CLEANING_TIME_S = 3


    SPLASH = \
"""
       __      __    _ __                     
      / /_  __/ /_  (_) /__  ___              
 __  / / / / / __ \/ / / _ \/ _ \             
/ /_/ / /_/ / /_/ / / /  __/  __/             
\_____\__,_/_._____/_/\___/\___/      __      
   / /   ____ _/ /_  ____ ___  ____ _/ /____  
  / /   / __ `/ __ \/ __ `__ \/ __ `/ __/ _ \ 
 / /___/ /_/ / /_/ / / / / / / /_/ / /_/  __/ 
/_____/\__,_/_.___/_/ /_/ /_/\__,_/\__/\___/  
                                              
"""


    def __init__(self, debug=False, simulated=False, deck_config_filepath="./config.json"):
        """Start with sane defaults. Setup Deck configuration."""
        super().__init__(debug, simulated)
        print(self.__class__.SPLASH)
        # Pull Deck Configuration if one is specified. Make a blank one otherwise.
        self.deck_config = copy.deepcopy(self.__class__.BLANK_DECK_CONFIGURATION)
        if deck_config_filepath:
            try:
                self.load_deck_config(deck_config_filepath)
            except FileNotFoundError:
                print("Could not load deck plate configuration from: "
                      f"{deck_config_filepath}")

        self.protocol_methods = self._collect_protocol_methods()
        self.sonicator = Sonicator()
        self.cam_feed_process = None

    def _collect_protocol_methods(self):
        """Collect all protocol methods decorated with the correpsonding decorator.

        protocol methods are any methods that can be invoked programmatically
        from a json protocol file.
        """
        protocol_methods = {}
        # # Workaround because getmembers does not get functions decorated specifically with @property
        # https://stackoverflow.com/questions/3681272/can-i-get-a-reference-to-a-python-property
        def get_dict_attr(obj, attr):
            for obj in [obj] + obj.__class__.mro():
                if attr in obj.__dict__:
                    return obj.__dict__[attr]
            raise AttributeError

        for name in dir(self):
            value = get_dict_attr(self, name)
            # Special case properties, which store setter functions in a different location.
            if isinstance(value, property):
                if hasattr(value.fset, 'is_protocol_method'):
                    protocol_methods[name] = value.fset
                continue
            # Special case classmethods.
            if isinstance(value, classmethod):
                value = value.__func__
            if hasattr(value, 'is_protocol_method'):
                protocol_methods[name] = value
        return protocol_methods


    @property
    @cli_method
    def safe_z(self):
        """Return the \"safe z\" height."""
        return self.deck_config["safe_z"]


    @safe_z.setter
    @cli_method
    def safe_z(self, z: float = None):
        """Set the specified height to be the \"safe z\" height.
        If no height is specified, the machine will take the current height.
        The machine will always retract to this position before moving in XY.
        """
        if z is None:
        # Get current height.
            _, _, self.deck_config['safe_z'] = self.position
        elif z > 0:
            self.deck_config['safe_z'] = z


    @cli_method
    def move_xy_absolute(self, x: float = None, y: float = None,
                         wait: bool = True):
        """Move in XY, but include the safe Z retract first if defined."""
        if self.safe_z is not None:
            super().move_xyz_absolute(z=self.safe_z, wait=wait)
        super().move_xyz_absolute(x,y,wait=wait)


    @cli_method
    def home_all(self):
        response = input("WARNING: is the deck clear of plates? [y/n]")
        if response.lower() in ["y", "yes"]:
            super().home_all()
        else:
            print("Aborting homing. Please remove all plates from the deck first.")


    @cli_method
    @requires_safe_z
    def check_plate_registration_points(self, plate_index: int = 0):
        """Move to predefined starting location for deck plate."""
        if plate_index < 0 or plate_index >= self.__class__.DECK_PLATE_COUNT:
            raise UserInputError(f"Error: deck plates must fall \
                within the range: [0, {plate_index}).")
        if self.active_tool_index != self.__class__.CAMERA_TOOL_INDEX:
            self.pickup_tool(self.__class__.CAMERA)

        if self.position[2] < self.safe_z:
            self.move_xyz_absolute(z=self.safe_z)

        try:
            self.enable_live_video()
            for x,y in self.deck_config['plates'][plate_index]['corner_well_centroids']:
                if x is None or y is None:
                    raise UserInputError(f"Error: this reference position \
                        for deck plate {plate_index} is not defined.")
                self.move_xy_absolute(x, y)
                # TODO: adjust focus??
                # TODO: implement adjustments in this situation?
                self.input("Press any key to continue.")
        finally:
            self.disable_live_video()
        self.park_tool()


    @cli_method
    def load_deck_config(self, file_path: str = "./config.json"):
        """Load a specified configuration of plates on the deck."""
        print(f"Loading deck plate configuration from: {file_path}.")
        with open(file_path, 'r') as config_file:
            self.deck_config = json.loads(config_file.read())


    @cli_method
    def save_deck_config(self, file_path: str = "./config.json"):
        """Save the current configuration of plates on the deck to a file."""
        with open(file_path, 'w+') as config_file:
            json.dump(self.deck_config, config_file, indent=4)
            print(f"Saving configuration to {file_path}.")


    @cli_method
    def show_deck_config(self):
        """Render the deck configuration."""
        pprint.pprint(self.deck_config)


    @cli_method
    @requires_safe_z
    def setup_cleaning_station(self):
        """Setup the cleaning station plates and procedure."""
        # Helper function for splitting rows and cols of a well.
        # https://stackoverflow.com/questions/13673781/splitting-a-string-where-it-switches-between-numeric-and-alphabetic-characters
        def well_id_split(row_col_str):
            return tuple(filter(None, re.split(r'(\d+)', row_col_str)))

        cleaning_config = copy.deepcopy(self.__class__.BLANK_CLEANING_CONFIG)

        # Prompt user to populate the machine with plates for cleaning.
        try:
            print("Cleaning Station Setup | Part 1: Plate Installation and Locating")
            plate_count = int(self.input("Enter the number of plates used for cleaning."))
            for plate_index in range(plate_count):
                deck_index = int(self.input("Enter the deck index for this plate (i.e: 0, 1, .. 5)."))
                cleaning_config["plates"].append(deck_index)
                self.setup_plate(deck_index)
            print("Cleaning Station Setup | Part 2: Bath Specs")
            # Repeatedly prompt the user to define the visit order of each cleaning bath.
            while True:
                deck_index = self.input("Enter the deck index for the current bath (i.e: 0, 1, 2, etc.).")
                row, col = well_id_split(self.input("Enter the well location of the bath (i.e: A1, B2, etc.)."))
                plunge_depth = self.input("Enter the sonicator plunge depth in mm.")
                plunge_time = float(self.input("Enter the time (in seconds) to activate the sonicator."))
                cmd = {"operation": "sonicate_well",
                       "specs": {"deck_index": deck_index,
                                 "row_letter": row,
                                 "column_index": col,
                                 "plunge_depth": plunge_depth,
                                 "seconds": plunge_time,
                                 "clean": False}} # Do not set to True, or infinite recursion.
                cleaning_config["protocol"].append(cmd)
                user_response = self.input("Add another bathing cycle? [y/n]")
                if user_response.lower() not in ['y', 'yes']:
                    break

            self.deck_config['cleaning_config'] = cleaning_config
        except KeyboardInterrupt:
            print("Aborting Cleaning Configuration without saving changes.")


    @cli_method
    @requires_safe_z
    def setup_plate(self, deck_index: int = None, well_count: int = None,
                    plate_loaded: bool = False):
        """Configure the plate type and location."""
        teach_points = []
        try:
            if deck_index is None:
                self.completions = list(map(str,range(self.__class__.DECK_PLATE_COUNT)))
                deck_index = int(self.input(f"Enter deck index: "))

            # Issue warning if this plate already exists. Bail if they cancel.
            if deck_index in self.deck_config['plates']:
                self.completions = ["y", "n"]
                response = self.input(f"Warning: configuration for deck slot {deck_index} already exists. "
                                      "Continuing will override the current config. Continue? [y/n]")
                if plate_loaded.lower() not in ["y", "yes"]:
                    return

            # TODO: ask for the plate type with an enum instead of by well count.
            if well_count is None:
                self.completions = list(map(str, self.__class__.WELL_COUNT_TO_ROWS.keys()))
                well_count = int(self.input(f"Enter number of wells: "))

            self.completions = ["y", "n"]
            plate_loaded = self.input(f"Is the plate already loaded on deck slot {deck_index}?")
            if plate_loaded.lower() not in ["y", "yes"]:
                # Move out of the way and let the user load the plate.
                self.move_xy_absolute(0,0)
                self.input(f"Please load the plate in deck slot {deck_index}. "
                           "Press any key when ready.")

            row_count, col_count = self.__class__.WELL_COUNT_TO_ROWS[well_count]
            last_row_letter = chr(row_count + 65 - 1)

            self.enable_live_video()
            # Move such that the well plates are in focus.
            self.move_xyz_absolute(z=(self.safe_z + self.__class__.CAMERA_FOCAL_LENGTH_OFFSET))
            self.pickup_tool(self.__class__.CAMERA_TOOL_INDEX)
            self.input("Commencing manual zeroing. Press any key when ready or 'CTRL-C' to abort")
            self.keyboard_control(prompt="Center the camera over well position A1. " \
                                  "Press 'q' to set the teach point or 'CTRL-C' to abort.")
            teach_points.append(self.position[0:2])

            self.input("Commencing manual zeroing. Press any key when ready or 'CTRL-C' to abort.")
            self.keyboard_control(prompt=
                f"Center the camera over well position A{row_count}")
            teach_points.append(self.position[0:2])

            self.input("Commencing manual zeroing. Press any key when ready or CTRL-C to abort.")
            self.keyboard_control(prompt=
                f"Center the camera over well position {last_row_letter}{row_count}. "
                "Press 'q' to set the teach point or 'CTRL-C' to abort.")
            teach_points.append(self.position[0:2])
            # Save everything at the end such that the user can abort at any time.
            self.deck_config['plates'][deck_index] = copy.deepcopy(self.__class__.BLANK_DECK_PLATE_CONFIG)
            self.deck_config['plates'][deck_index]["well_count"] = well_count
            self.deck_config['plates'][deck_index]["corner_well_centroids"][0] = teach_points[0]
            self.deck_config['plates'][deck_index]["corner_well_centroids"][1] = teach_points[1]
            self.deck_config['plates'][deck_index]["corner_well_centroids"][2] = teach_points[2]
        except KeyboardInterrupt:
            print("Aborting. Well locations not saved.")
        finally:
            self.disable_live_video()
            self.park_tool()


    @cli_method
    @protocol_method
    @requires_safe_z
    @requires_cleaning_station
    def sonicate_well(self, deck_index: int, row_letter: str, column_index: int,
                      plunge_depth: int, seconds: float, clean: bool = True):
        """Sonicate one well at a specified depth for a given time. Then clean the tip."""
        # Sanity check that we're not plunging too deep. Plunge depth is relative.
        if z - plunge_depth < 0:
            raise UserInputError("Error: plunge depth is too deep.")

        if self.active_tool_index != self.__class__.SONICATOR_TOOL_INDEX:
            self.pickup_tool(self.__class__.SONICATOR_TOOL_INDEX)

        row_index = ord(row_letter.upper()) - 65 # map row letters to numbers.
        x,y = self._get_well_position(deck_index, row_index, column_index)

        print(f"Sonicating at: ({x}, {y})")
        self.move_xy_absolute(x,y) # Position over the well at safe z height.
        _, _, z = self.position
        self.move_xyz_absolute(z=(z - plunge_depth), wait=True)
        print(f"sonicating for {seconds} seconds!!")
        self.sonicator.sonicate(seconds)
        self.move_xy_absolute() # leave the machine at the safe height.
        if clean:
            self.clean_sonicator()


    @cli_method
    @protocol_method
    @requires_safe_z
    @requires_cleaning_station
    def clean_sonicator(self):
        """Run the sonicator through the cleaning protocol."""
        self.execute_protocol(self.deck_config['cleaning_config']['protocol'])


    def execute_protocol_from_file(self, protocol_file_path):
        """Open the protocol file and run the protocol."""
        with open(protocol_file_path, 'r') as protocol_file:
            protocol = json.loads(protocol_file.read())
            self.execute_protocol(protocol)


    def execute_protocol(self, protocol):
        """Execute a list of protocol commands."""
        for cmd in cleaning_step:
            if cmd['operation'] not in self.protocol_methods:
                raise UserInputError(f"Error. Method cmd['name'] is not a method that can be used in a protocol.")
            fn = self.protocol_methods[cmd['operation']]
            kwargs = cmd['specs']
            fn(**kwargs)


    def enable_live_video(self):
        """Enables the video feed."""
        print("Starting camera feed.")
        self.discarded_cam_output = open(os.devnull, 'w')
        self.cam_feed_process = \
            subprocess.Popen("./launch_camera_alignment_feed.sh", shell=True,
                             preexec_fn=os.setsid, stderr=self.discarded_cam_output)


    def disable_live_video(self):
        """Disables the video feed."""
        if self.cam_feed_process:
            print("Stopping camera feed.")
            os.killpg(os.getpgid(self.cam_feed_process.pid), signal.SIGTERM)
            #self.cam_feed_process.kill() This doesn't work.
            self.cam_feed_process = None
        if self.discarded_cam_output is not None:
            self.discarded_cam_output.close()


    def _get_well_position(self, deck_index: int, row_index: int, col_index: int):
        """Get the machine coordinates for the specified well plate index."""
        # Note: we lookup well spacing from a built-in dict for now.
        well_count = self.deck_config['plates'][deck_index]["well_count"]
        row_count, col_count = self.__class__.WELL_COUNT_TO_ROWS[well_count]

        if row_index > (row_count - 1) or col_index > (col_count - 1):
            raise LookupError(f"Requested well index ({row_index}, {col_index}) "
                              f"is out of bounds for a plate with {row_count} rows "
                              f"and {col_count} columns.")

        a = self.deck_config['plates'][deck_index]["corner_well_centroids"][0]
        b = self.deck_config['plates'][deck_index]["corner_well_centroids"][1]
        c = self.deck_config['plates'][deck_index]["corner_well_centroids"][2]

        plate_width = sqrt((b[0] - a[0])**2 + (b[1] - a[1])**2)
        plate_height = sqrt((c[0] - b[0])**2 + (c[1] - b[1])**2)

        # Note: we assume evenly spaced wells but possibly distinct x and y spacing
        x_spacing = plate_width/(col_count - 1)
        y_spacing = plate_height/(row_count - 1)

        # We have two redundant angle measurements. Average them.
        theta1 = acos((c[1] - b[1])/plate_height)
        theta2 = acos((b[0] - a[0])/plate_width)
        theta = (theta1 + theta2)/2.0

        # Start with the nominal spot; then translate and rotate to final spot.
        x_nominal = col_index * x_spacing
        y_nominal = row_index * y_spacing
        x_transformed = x_nominal * cos(theta) - y_nominal * sin(theta) + a[0]
        y_transformed = x_nominal * sin(theta) + y_nominal * cos(theta) + a[1]

        return x_transformed, y_transformed


    @cli_method
    def demo(self):
        plunge_depth = 15
        self.sonicate_well(0, "A", 0, plunge_depth, 2)
        self.sonicate_well(0, "A", 1, plunge_depth, 2)
        self.sonicate_well(0, "A", 2, plunge_depth, 2)
        self.sonicate_well(0, "A", 3, plunge_depth, 2)
        self.park_tool()

    def __enter__(self):
      return self

    def __exit__(self, *args):
      super().__exit__(args)
      self.disable_live_video()


if __name__ == "__main__":
    with SonicationStation(simulated=False, debug=False) as jubilee:
        jubilee.cmdloop()
