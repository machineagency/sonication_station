#!/usr/bin/env python3
"""Driver for Controlling Jubilee as a Lab Automation Device"""
import socket
import json
import time
import copy
import pprint
import subprocess, signal, os # for launching/killing video feed
from math import sqrt, acos, asin, cos, sin
from threading import Thread, Lock
from inpromptu import cli_method, UserInputError
from jubilee_controller import JubileeMotionController, machine_is_homed
from sonicator import Sonicator
#from sonicator import sonicator

class SonicationStation(JubileeMotionController):
    """Driver for sending motion cmds and polling the machine state."""

    SD_CONFIG_FILEPATH = "/opt/dsf/sd"

    WELL_COUNT_TO_ROWS = {96: (8, 12),
                          48: (6, 8),
                           6: (2, 3),
                           12: (3, 4)}
    DECK_PLATE_COUNT = 6

    DECK_PLATE_CONFIG = \
        {"id": "",
         "starting_well_centroid": (150, 150),
         "first_row_last_col_well_centroid": (100, 150),
         "ending_well_centroid": (100, 120),
         "well_count": 96,
         "row_count": 8,
         "col_count": 12}
        #{"id": "",
        # "starting_well_centroid": (None, None),
        # "first_row_last_col_well_centroid": (None, None),
        # "ending_well_centroid": (None, None),
        # "well_count": None,
        # "row_count": None,
        # "col_count": None}

    CLEANING_TIME_S = 3

    CAMERA_TOOL_INDEX = 0
    SONICATOR_TOOL_INDEX = 1

    splash = \
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
        print(self.__class__.splash)
        # Pull Deck Configuration if one is specified. Make a blank one otherwise.
        self.deck_config = {}
        self.deck_config["plates"] = [copy.deepcopy(self.__class__.DECK_PLATE_CONFIG) \
                                      for i in range(self.__class__.DECK_PLATE_COUNT)]
        self.deck_config["safe_z"] = None
        if deck_config_filepath:
            try:
                self.load_deck_config(deck_config_filepath)
            except FileNotFoundError:
                print("Could not load deck plate configuration from: "
                      f"{deck_config_filepath}")

        self.sonicator = Sonicator()
        self.cam_feed_process = None


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
            _, _, self.deck_config["safe_z"] = self.position
        elif z > 0:
            self.safe_z = z


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
    @machine_is_homed
    def check_plate_registration_points(self, plate_index: int = 0):
        """Move to predefined starting location for deck plate."""
        if self.safe_z is None:
            raise UserInputError(f"Error: safe z height is not defined.")
        if plate_index < 0 or plate_index >= self.__class__.DECK_PLATE_COUNT:
            raise UserInputError(f"Error: deck plates must fall \
                within the range: [0, {plate_index}).")
        if self.curr_tool_index != self.__class__.CAMERA_TOOL_INDEX:
            self.pickup_tool(self.__class__.CAMERA_TOOL_INDEX)

        if self.position[2] < self.safe_z:
            self.move_xyz_absolute(z=self.safe_z)

        well_locations = ["starting_well_centroid",
                          "first_row_last_col_well_centroid",
                          "ending_well_centroid"]
        try:
            self.enable_live_video()
            for key in well_locations:
                x, y = self.deck_config['plates'][plate_index][key]
                if x is None or y is None:
                    raise UserInputError(f"Error: this reference position \
                        for deck plate {plate_index} is not defined.")
                self.move_xy_absolute(x, y)
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
            json.dump(self.deck_config, config_file)
            print(f"Saving configuration to {file_path}.")


    @cli_method
    def show_deck_config(self):
        """Render the deck configuration."""
        pprint.pprint(self.deck_config)


    @cli_method
    @machine_is_homed
    def setup_plate(self, deck_index: int = None, well_count: int = None,
                    plate_loaded: bool = False):
        """Configure the plate type and location."""
        teach_points = []
        try:
            if deck_index is None:
                self.completions = list(map(str,range(self.__class__.DECK_PLATE_COUNT)))
                deck_index = int(self.input(f"Enter deck index: "))

            # TODO: ask for the plate type with an enum.
            if well_count is None:
                self.completions = ["6", "48", "96"]
                well_count = int(self.input(f"Enter number of wells: "))
            self.deck_config['plates'][deck_index]["well_count"] = well_count

            self.completions = ["y", "n"]
            plate_loaded = self.input("Is the plate already loaded on deck slot "
                                      f"{deck_index}?")
            if plate_loaded.lower() not in ["y", "yes"]:
                self.move_xy_absolute(0,0)
                self.input("Please load the plate in deck slot {deck_index}. "
                           "Press any key when ready.")

            row_count, col_count = self.__class__.WELL_COUNT_TO_ROWS[well_count]
            last_row_letter = chr(row_count + 65 - 1)

            self.enable_live_video()
            self.pickup_tool(self.__class__.CAMERA_TOOL_INDEX)
            self.move_xyz_absolute()
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
            # Save points at the end such that the user can abort at any time.
            self.deck_config['plates'][deck_index]["starting_well_centroid"] = teach_points[0]
            self.deck_config['plates'][deck_index]["first_row_last_col_well_centroid"] = teach_points[1]
            self.deck_config['plates'][deck_index]["ending_well_centroid"] = teach_points[2]
        except KeyboardInterrupt:
            print("Aborting. Well locations not saved.")
        finally:
            self.disable_live_video()
            self.park_tool()


    @cli_method
    @machine_is_homed
    def sonicate_well(self, deck_index: int, row_letter: str, column_index: int,
                      plunge_depth: int, seconds: float):
        """Sonicate one plate well at a specified depth for a given time."""
        # Check prerequisites.
        if self.safe_z is None:
            raise UserInputError("Error: safe Z height for XY travel moves "
                                 "must first be defined.")
        # Sanity check that we're not plunging too deep. Plunge depth is relative.
        if z - plunge_depth < 0:
            raise UserInputError("Error: plunge depth is too deep.")

        if self.curr_tool_index != self.__class__.SONICATOR_TOOL_INDEX:
            self.pickup_tool(self.__class__.SONICATOR_TOOL_INDEX)

        row_index = ord(row_letter.upper()) - 65 # map row letters to numbers.
        x,y = self._get_well_position(deck_index, row_index, column_index)

        print(f"Sonicating at: ({x}, {y})")
        self.move_xy_absolute(x,y) # Position over the well at safe z height.
        _, _, z = self.position
        self.move_xyz_absolute(z=(z - plunge_depth), wait=True)
        print(f"sonicating for {seconds} seconds!!")
        self.sonicator.sonicate(seconds) # TODO: maybe slow this down?
        self.move_xy_absolute() # safe height.


    @cli_method
    def clean_sonicator(self, bath_time: int = CLEANING_TIME_S):
        """Run the sonicator through the baths."""
        for x,y in self.cleaning_vile_locations:
            self.move_xy_absolute(x, y)
            self.move_xyz_absolute(z) # TODO: maybe slow this down?
            self.sonicator.sonicate(seconds) # TODO: maybe slow this down?
            self.move_xy_absolute() # safe height.


    def enable_live_video(self):
        """Enables the video feed."""
        self.cam_feed_process = \
            subprocess.Popen("./launch_camera_alignment_feed.sh", shell=True,
                             preexec_fn=os.setsid)


    def disable_live_video(self):
        """Disables the video feed."""
        if self.cam_feed_process:
            print("killing camera feed.")
            os.killpg(os.getpgid(self.cam_feed_process.pid), signal.SIGTERM)
            #self.cam_feed_process.kill() This doesn't work.
            self.cam_feed_process = None


    def _get_well_position(self, deck_index: int, row_index: int, col_index: int):
        """Get the machine coordinates for the specified well plate index."""
        # Note: we lookup well spacing from a built-in dict for now.
        well_count = self.deck_config['plates'][deck_index]["well_count"]
        row_count, col_count = self.__class__.WELL_COUNT_TO_ROWS[well_count]

        if row_index > (row_count - 1) or col_index > (col_count - 1):
            raise LookupError(f"Requested well index ({row_index}, {col_index}) "
                              f"is out of bounds for a plate with {row_count} rows "
                              f"and {col_count} columns.")

        a = self.deck_config['plates'][deck_index]["starting_well_centroid"]
        b = self.deck_config['plates'][deck_index]["first_row_last_col_well_centroid"]
        c = self.deck_config['plates'][deck_index]["ending_well_centroid"]

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
