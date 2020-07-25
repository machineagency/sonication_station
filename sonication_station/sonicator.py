import sys
import signal
import time
import digitalio
import board
import busio
import adafruit_mcp4725

class Sonicator(object):

    def __init__(self):
        """Sonicator init."""
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.dac = adafruit_mcp4725.MCP4725(self.i2c, address=0x60)
        self.sonicator_enable = digitalio.DigitalInOut(board.D4)
        self.sonicator_enable.direction = digitalio.Direction.OUTPUT
        self.sonicator_enable.value = False
        self.dac.normalized_value = 0.50

    def sonicate(self, exposure_time: float = 1.0, power_percentage: float = 0.4):
        """enable the sonicator at the power level for the exposure time."""
        # TODO: clamp this percentage.
        self.dac.normalized_value = power_percentage
        self.sonicator_enable.value = True
        time.sleep(exposure_time)
        self.sonicator_enable.value = False
        self.dac.normalized_value = 0

    def __exit__(self):
        """Cleanup."""
        self.sonicator_enable.value = False
        self.dac.normalized_value = 0


#def graceful_exit(signal, frame):
#    """Turn off the sonicator before exiting the program."""
#    sonicator_enable.value = False
#    dac.normalized_value = 0
#    print("exiting.")
#    sys.exit(1)
#
## On for 3sec; off for 3sec. Cancel with CTRL-C
#if __name__ == "__main__":
#    # Catch CTRL-C by shutting everything off.
#    signal.signal(signal.SIGINT, graceful_exit)
#
#    print("3sec on/off pulse demo. Press CTRL-C to exit cleanly.")
#    while True:
#        sonicator_enable.value = True
#        time.sleep(3.0)
#        sonicator_enable.value = False
#        time.sleep(3.0)
