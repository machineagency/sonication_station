#!/usr/bin/env python3
"""Driver for Controlling Jubilee as a Lab Automation Device"""
import socket
import json
import time
import copy
from threading import Thread, Lock
from introspect_interface import MASH, cli_method
from jubilee_controller import JubileeMotionController

class Labmate(JubileeMotionController):
    """Driver for sending motion cmds and polling the machine state."""

    DECK_PLATE_COUNT = 6

    DECK_PLATE_CONFIG = \
        {"id": "",
         "starting_well_position": (None, None),
         "ending_well_position": (None, None),
         "well_count": None,
         "row_count": None,
         "col_count": None}


    def __init__(self, debug=False, simulated=False, deck_config_filepath=None):
        """Start with sane defaults. Setup Deck configuration."""
        super().__init__(debug, simulated)
        self.safe_z = None
        self.deck_plate_config = [copy.deepcopy(self.__class__.DECK_PLATE_CONFIG) \
                            for i in range(self.__class__.DECK_PLATE_COUNT)]
        if deck_config_filepath:
            self.load_deck_config(filepath)


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


    def move_xy_absolute(self, x: float = None, y: float = None,
                         wait: bool = True):
        """Move in XY, but include the safe Z retract first if defined."""
        if self.safe_z is not None:
            super().move_xyz_absolute(z=self.safe_z)
        super().move_xy_absolute(x,y,wait)


    @cli_method
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


    @cli_method
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
    def setup_plate(self, deck_index: int):
        """Configure the plate type and location."""
        try:
            self.completions = ["6", "48", "96"]
            well_count = self.input(f"Enter the number of wells: ")
            self.deck_plate_config[deck_index]["well_count"] = int(well_count)
            self.completions = ["2", "6", "8"]
            row_count = self.input(f"Enter the number of rows: ")
            self.deck_plate_config[deck_index]["row_count"] = int(row_count)
            self.completions = ["3", "8", "12"]
            col_count = self.input(f"Enter the number of columns: ")
            self.deck_plate_config[deck_index]["col_count"] = int(col_count)
        finally:
            self.completions = None


    def __enter__(self):
      return self

    def __exit__(self, *args):
      self.disconnect()


if __name__ == "__main__":
    with Labmate(simulated=True) as jubilee:
        #jubilee.home_xy()
        jubilee.cli()
