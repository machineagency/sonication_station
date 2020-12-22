from sonication_station.sonication_station import SonicationStation


# Assume the machine is homed and already populated with labware at this poifnt!

if __name__ == "__main__":
    with SonicationStation() as jubilee:
        #jubilee.home_all()
        response = input("Please populate the deck with labware. Press Enter when ready or CTRL-c to quit.")
        rows = ["A", "B", "C"]
        columns = [1, 2, 3, 4]
        for row in rows:
            for col in columns:
                jubilee.sonicate_well(0, row, col, plunge_depth=20, seconds=1, power = 0.5, autoclean = False)
