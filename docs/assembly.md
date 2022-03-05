# Machine Assembly

Transforming Jubilee into the Sonication Station requires the addition of some custom hardware and software beyond building the frame.

## Hardware Checklist

### Single Board Computer for SBC Mode
* 32GB SD card
* Raspberry Pi 4, 4GB
* ethernet cable
* [ethernet-to-usb3 adapter](https://www.amazon.com/gp/product/B00M77HMU0)

### Sonicator Tool
* Q125 Sonicator Horn
* Sonicator Probe (various probe sizes, including pn: 4423, pn: 4422, and pn: 4435)
* Sonicator Control PCB, pn: KITVC1025 (20kHz) or pn: KITVC1045 (40kHz)
* Sonicator Wiring Harness
    * 1x [Molex: 0022552102](https://www.digikey.com/en/products/detail/molex/0022552102/303176)
    * 3x [Molex: 0016020086](https://www.digikey.com/en/products/detail/molex/0016020086/467788)
    * 1x [McMaster-Carr: 7243K117](https://www.mcmaster.com/7243K117/) for the sonicator horn wiring
    * 1x [McMaster-Carr: 7243K122](https://www.mcmaster.com/7243K122/) for the sonicator horn wiring

### Camera Tool
* [Sonicator Pi Hat PCB](./pcb)
* [Arducam Lens Board](https://www.amazon.com/gp/product/B013JTY8WY)
* [HDMI Cable](https://www.amazon.com/gp/product/B00Z07JYLE) (flexible, 2m or 6ft)
* [Arducam CSI to HDMI Cable Extension Module](https://www.amazon.com/gp/product/B06XDNBM63)


## Overall Setup

Jubilee will be provisioned in "SBC Mode" and the sonication\_station python package in this repository will be installed on it.
The Sonicator Pi Hat will be attached to the Pi and connected to the Sonicator Control PCB.


## Diagram HERE


## Assembly Instructions
1. Order and populate the [Sonicator Pi Hat](./pcb) PCB.
1. Order the Parts for a Sonicator Tool and a Camera Tool.
1. Install [DuetPi](https://docs.duet3d.com/en/User_manual/Machine_configuration/SBC_setup) OS on the Raspberry Pi
1. Assemble the Sonicator Tool and harness and the camera tool and harness.
1. Connect to the Raspberry Pi, give it internet access, and install the sonication\_station package according to the [instructions](https://github.com/machineagency/sonication_station#installation)
1. Set the XYZ Tool Offsets of the Sonicator and and Jubilee Tool.
