# sonication_station
jubilee masquerading as a science robot

## Intro
This project wraps a python interface around the existing Duet 3 Socket Interface, turning Jubilee into a plate handling lab automation device for sonication.

## Conventions
PLATE PICTURE HERE

## API
There are 3 ways of interacting with the machine: (1) directly through a python script, (2) interactively through a command prompt, and (3) procedurally with predefined protocol.

## Python Script Mode

## Manual Mode

### Running the machine in manual mode:
```python
with JubileeMotionController(simulated=False) as jubilee:
    jubilee.cmdloop()
```

## Protocol Mode
This method is for invoking predefined protocol. Protocol mode may be useful for generating a series of plate operations programmatically from another program and then simply executing them on the Sonication Station. Protocols consist of a series of sonication commands executed sequentially.

### Protocol API
A sample protocol looks like this:
```
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
So far, only one operation **sonicate_well**, is implemented.

### Running the machine in Protocol Mode
```python
with JubileeMotionController(simulated=False) as jubilee:
    jubilee.home_all()
    jubile.execute_protocol_from_file("path/to/file.json")
```
