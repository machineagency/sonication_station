#!/usr/bin/env python3
from sonication_station.sonication_station import SonicationStation

if __name__ == "__main__":
    with SonicationStation() as jubilee:
        jubilee.cmdloop()
