## Intro
This project wraps a python interface around the existing Duet 3 Socket Interface, turning Jubilee into a plate handling lab automation device for sonication.

## Connecting to Jubilee
There are two ways to connect to Jubilee and execute code: (1) locally and (2) with a separate PC over a network connection.

They look like this:

### Local Connection
<img src="https://github.com/machineagency/sonication_station/blob/master/docs/pics/jubilee_duet3_local_connection.png">
In this mode, the Python protocol runs on the Raspberry Pi attached to the machine. It is recommended for production use.

### Closed Network Connection
<img src="https://github.com/machineagency/sonication_station/blob/master/docs/pics/jubilee_duet3_closed_network_connection.png">
In this mode, the Python protocol runs on a separate pc with this software package installed. It is useful for testing but not recommended for production.

When running the machine in this mode, note that turning off your PC or losing the network connection will halt the machine mid-execution.
Furthermore, a laggy network connection will cause the machine to lag.
To avoid these issues in production, we recommended that running the protocol locally (on the Raspberry Pi) instead of using an arbitrary PC on the same network.

## Installation
If you are running this code locally, clone this repository onto Jubilee's attached Raspberry Pi. If you are running it over a network connection, clone it onto your PC.

Then, from within this directory (the one with this README in it), install the project via pip with ....
```
pip install -e .
```

Now you can spin up a connection to Jubilee by importing the driver.

## Conventions
Looking top-down at the plate, plates are indexed as follows:

<img src="https://github.com/machineagency/sonication_station/blob/master/docs/pics/bed_plate_reference.png" width="480">

### Starting Machine State
When Jubilee is first powered up, it will need to first home all axes. You must issue this command yourself. To home, the deck must be clear of all labware.
After homing, you may populate the deck and execute protocols can be run. You only need to home once when Jubilee is first turned on, or once after any situation where the machine has lost it's position (from an event like a crash).

### Ending Machine State
All tools must be put away before Jubilee is powered off. This is the default behavior if you run the code inside a *with* statement. In any situation where the Jubilee was powered off in an emergency, you must remove any active tools on Jubilee's carriage before powering it back on.

## API
There are 3 ways of interacting with the machine:
(1) directly through a python script,
(2) interactively through a command prompt, and
(3) procedurally with predefined protocol.

## Python Script Mode
After installing this package with pip, you should be able to simply import it in python:

If you are running the code locally, the code will look like this:
```python
from sonication_station.sonication_station import SonicationStation
with SonicationStation() as jubilee:
    jubilee.sonicate_well(0, 'A', 0, 3, 10, False)
```
If you are running the code over a network from a separate PC, the code may look like this:
```python
from sonication_station.sonication_station import SonicationStation
with SonicationStation(address="192.168.1.2") as jubilee:
    jubilee.sonicate_well(0, 'A', 0, 3, 10, False)
```
Here the above *address* argument is the ip address of Jubilee as it appears on your network.

## Manual (Maintenance) Mode
You can interactively control Jubilee through a custom prompt.
To interact with the prompt, spin it up from the python shell with:

```python
from sonication_station.sonication_station import SonicationStation
with SonicationStation() as jubilee:
    jubilee.cmdloop()
```

or, from the command line:

```
sudo path/to/sonication_station/sonication_station.py
```

This will drop you into an interactive prompt that looks like this:
```

  ____              _           _   _               ____  _        _   _             
 / ___|  ___  _ __ (_) ___ __ _| |_(_) ___  _ __   / ___|| |_ __ _| |_(_) ___  _ __  
 \___ \ / _ \| '_ \| |/ __/ _` | __| |/ _ \| '_ \  \___ \| __/ _` | __| |/ _ \| '_ \ 
  ___) | (_) | | | | | (_| (_| | |_| | (_) | | | |  ___) | || (_| | |_| | (_) | | | |
 |____/ \___/|_| |_|_|\___\__,_|\__|_|\___/|_| |_| |____/ \__\__,_|\__|_|\___/|_| |_|
                                                                                     

>>> 

```
This mode lets you input commands one at a time.

In this mode you can:

* home the machine
* execute movement commands
* execute sonication commands
* pickup and park tools
* interactively set the location/type of a new well plate
* control the machine with the keyboard arrow keys
setup the machine and execute commands serially. This interface is useful for adding to the plate inventory.

To see the list of supported commands, press TAB twice. This mode also supports TAB completion, that is, if you start typing a command and press TAB twice, the prompt will either attempt to auto-complete any possibilities or show you a list of possible completions.
To get help on any command, simply type:

```
>>> help command_name_here
```


## Protocol Mode
This method is for invoking predefined protocol. Protocol mode may be useful for generating a series of plate operations programmatically from another program and then simply executing them on the Sonication Station. Protocols consist of a series of sonication commands executed sequentially.

### Protocol API
A sample protocol looks like this:
```json
{
   "protocol": [
       {
           "operation": "sonicate_well",
           "specs": {
               "deck_index": 5,
               "row_letter": "A",
               "column_index": 1,
               "plunge_depth": 10.0,
               "seconds": 3.0,
               "autoclean": false
           }
       },
       {
           "operation": "sonicate_well",
           "specs": {
               "deck_index": 5,
               "row_letter": "A",
               "column_index": 2,
               "plunge_depth": 10.0,
               "seconds": 3.0,
               "autoclean": false
           }
       }
   ]
}
```
So far, only one operation **sonicate_well**, is implemented. the options are as follows:
* **deck_index:** the deck index of the plate
* **row_letter:** the row index on the plate, indicated by letter
* **column_index:** the column indicated by integer
* **plunge_depth:** the depth to plunge the sonicator into the glassware as measured from the top of the glassware
* **seconds:** time in seconds to run the sonicator
* **autoclean**: (boolean), whether or not to run a predefined cleaning protocol.

Note that if **autoclean** is set to true, a cleaning protocol must be defined in the machine configuration. Cleanin protocols can also be defined in manual mode.

### Running the machine in Protocol Mode
```python
from sonication_station.sonication_station import SonicationStation
with SonicationStateion() as jubilee:
    jubilee.home_all()
    jubile.execute_protocol_from_file("path/to/file.json")
```
