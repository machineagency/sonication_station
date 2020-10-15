from sonication_station.sonication_station import SonicationStation


# Assume the machine is homed and already populated with labware at this point!

if __name__ == "__main__":
    with SonicationStation() as jubilee:
        #jubilee.home_all()
        response = input("Please populate the deck with labware. Press Enter when ready or CTRL-c to quit.")
        rows = ["A", "B", "C"]
        #columns = [1, 2, 3, 4]
        columns = [1]
        for row in rows:
            for col in columns:
                jubilee.sonicate_well(1, row, col, plunge_depth=10, seconds=1)
