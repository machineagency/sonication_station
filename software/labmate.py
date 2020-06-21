#!/usr/bin/env python3
"""Driver for Controlling Jubilee as a Lab Automation Device"""
import socket
import json
import time
import copy
from threading import Thread, Lock
from introspect_interface import MASH, cli_method
from jubilee_controller import JubileeMotionController
#from sonicator import sonicator

class Labmate(JubileeMotionController):
    """Driver for sending motion cmds and polling the machine state."""

    WELL_COUNT_TO_ROWS = {96: (8, 12),
                          48: (6, 8),
                           6: (2, 3)}
    DECK_PLATE_COUNT = 6

    DECK_PLATE_CONFIG = \
        {"id": "",
         "starting_well_centroid": (None, None),
         "first_row_last_col_well_centroid": (None, None),
         "ending_well_centroid": (None, None),
         "well_count": None,
         "row_count": None,
         "col_count": None}

    CLEANING_TIME_S = 3

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


    def __init__(self, debug=False, simulated=False, deck_config_filepath=None):
        """Start with sane defaults. Setup Deck configuration."""
        super().__init__(debug, simulated)
        print(self.__class__.splash)
        self.safe_z = None
        self.deck_plate_config = [copy.deepcopy(self.__class__.DECK_PLATE_CONFIG) \
                            for i in range(self.__class__.DECK_PLATE_COUNT)]
        if deck_config_filepath:
            self.load_deck_config(filepath)
        self.sonicator = None


    # Do not write a getter for this.
    @property
    def z(self):
        """Return current Z height."""
        #FIXME: actually figure out what the subscript is.
        return self.machine_model['z']

    @cli_method
    def set_safe_z(self, z: float):
        """Set the current height to be the \"safe z\" height.
        The machine will retract to this position before moving in XY.
        """
        # Get current height.
        # Save it.
        raise NotImplementedError


    @cli_method
    def move_xy_absolute(self, x: float = None, y: float = None,
                         wait: bool = True):
        """Move in XY, but include the safe Z retract first if defined."""
        if self.safe_z is None:
            super().move_xyz_absolute(z=self.safe_z)
        super().move_xyz_absolute(x,y,wait=wait)


    def move_to_plate_starting_well_pos(self, deck_plate_index: int):
        """Move to predefined starting location for deck plate."""
        if plate_index < 0 or plate_index >= self.__class__.DECK_PLATE_COUNT:
            raise UserInputError(f"Error: deck plates must fall \
                within the range: [0, {plate_index}).")
        x, y = self.deck_plate_config[deck_plate_index]["starting_well_position"]
        if x is None or y is None:
            raise UserInputError(f"Error: starting position \
                for deck plate {plate_index} is not defined.")
        if self.z < self.safe_z:
            self.move_xyz_absolute(z=self.safe_z)
        self.move_xy_absolute(x, y)
        pass


    def move_to_plate_ending_well_pos(self, plate_index: int):
        """Move to predefined ending location for deck plate."""
        if plate_index < 0 or plate_index >= self.__class__.DECK_PLATE_COUNT:
            raise UserInputError(f"Error: deck plates must fall \
                within the range: [0, {plate_index}).")
        x, y = self.deck_plate_config[deck_plate_index]["ending_well_position"]
        if x is None or y is None:
            raise UserInputError(f"Error: ending position \
                for deck plate {plate_index} is not defined.")
        if self.z < self.safe_z:
            self.move_xyz_absolute(z=self.safe_z)
        self.move_xy_absolute(x, y)
        pass


    @cli_method
    def load_deck_config(self, file_path: str = "./config.json"):
        """Load a specified configuration of plates on the deck."""
        with open(file_path, 'r') as config_file:
            self.deck_plate_config = json.loads(config_file.read())


    @cli_method
    def save_deck_config(self, file_path: str = "./config.json"):
        """Save the current configuration of plates on the deck to a file."""
        with open(file_path, 'w+') as config_file:
            json.dump(self.deck_plate_config, config_file)
            print(f"Saving configuration to {file_path}.")

    @cli_method
    def test_input(self):
        """hello."""
        try:
            self.completions = ["yo", "why hello there."]
            response = input("test input:")
            print(f"response: {response}")
        finally:
            self.completions = None


    @cli_method
    def setup_plate(self, deck_index: int = None, well_count: int = None):
        """Configure the plate type and location."""
        try:
            if deck_index is None:
                self.completions = list(map(str,range(self.__class__.DECK_PLATE_COUNT)))
                deck_index = int(self.input(f"Enter deck index: "))

            # TODO: ask for the plate type with an enum.
            if well_count is None:
                self.completions = ["6", "48", "96"]
                well_count = int(self.input(f"Enter number of wells: "))
            self.deck_plate_config[deck_index]["well_count"] = well_count

            row_count, col_count = self.__class__.WELL_COUNT_TO_ROWS[well_count]
            last_row_letter = chr(row_count + 65 - 1)

            self.input("Commencing manual zeroing. Press any key when ready.")
            self.keyboard_control(prompt=
                f"Center the tool head over the well position A1")
            self.deck_plate_config[deck_index]["starting_well_centroid"] = self.get_position()[0:2]

            self.input("Commencing manual zeroing. Press any key when ready.")
            self.keyboard_control(prompt=
                f"Center the tool head over the well position A{row_count}")
            self.deck_plate_config[deck_index]["first_row_last_col_well_centroid"] = self.get_position()[0:2]

            self.input("Commencing manual zeroing. Press any key when ready.")
            self.keyboard_control(prompt=
                f"Center the tool head over the well position {last_row_letter}{row_count}")
            self.deck_plate_config[deck_index]["ending_well_centroid"] = self.get_position()[0:2]
            import pprint
            pprint.pprint(self.deck_plate_config[deck_index])

        finally:
            self.completions = None

    @cli_method
    def sonicate_well(self, deck_index: int, well_index: int, plunge_depth: int,
                      seconds: float):
        """Sonicate one plate well at a specified depth for a given time."""
        x,y = self.get_well_position(deck_index, well_index)
        self.move_xy_absolute(x,y)
        self.move_xyz_absolute(z) # TODO: maybe slow this down?
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


    def __enter__(self):
      return self

    def __exit__(self, *args):
      self.disconnect()


if __name__ == "__main__":
    with Labmate(simulated=True) as jubilee:
        #jubilee.home_xy()
        jubilee.cli()
