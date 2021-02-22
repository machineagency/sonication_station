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

    def sonicate(self, exposure_time: float = 1.0, power: float = 0.4,
                 pulse_duty_cycle: float = 0.5, pulse_interval: float = 1.0):
        """enable the sonicator at the power level for the exposure time."""
        # Quick sanity checks
        assert 0 <= power <= 1.0, \
            f"Error: power must be between 0.0 and 1.0. Value specified is: {power}"
        assert 0 <= pulse_duty_cycle <= 1.0, \
            f"Error: pulse_duty_cycle must be between 0.0 and 1.0. Value specified is: {pulse_duty_cycle}"
        assert pulse_interval > 0, \
            f"Error: pulse_interval must be positive. Value specified is: {pulse_interval}."
        assert pulse_interval <= exposure_time, \
            f"Error: pulse_interval cannot exceed exposure time. Value specified is: {pulse_interval}, " \
            f"but total exposure time is {exposure_time}."

        self.dac.normalized_value = power
        on_interval = pulse_duty_cycle * pulse_interval
        off_interval = (1 - pulse_duty_cycle) * pulse_interval

        start_time = time.perf_counter()
        stop_time = exposure_time + start_time
        while True:
            # On interval.
            curr_time = time.perf_counter()
            if curr_time + on_interval < stop_time:
                print(f"{time.perf_counter() - start_time :.2f} | Sonicator on.")
                self.sonicator_enable.value = True
                time.sleep(on_interval)
            elif stop_time > curr_time: # last time to sleep.
                print(f"{time.perf_counter() - start_time :.2f} | Sonicator on.")
                self.sonicator_enable.value = True
                time.sleep(stop_time - curr_time)

            # Off interval.
            curr_time = time.perf_counter()
            if curr_time + off_interval < stop_time:
                print(f"{time.perf_counter() - start_time :.2f} | Sonicator off.")
                self.sonicator_enable.value = False
                time.sleep(off_interval)
            elif stop_time > curr_time: # last time to sleep.
                print(f"{time.perf_counter() - start_time :.2f} | Sonicator off.")
                self.sonicator_enable.value = False
                time.sleep(stop_time - curr_time)
                break
            else:
                print(f"{time.perf_counter() - start_time :.2f} | Sonicator off.")
                break

        print(f"{time.perf_counter() - start_time :.2f} | Finished sonicating.")
        self.sonicator_enable.value = False
        self.dac.normalized_value = 0

    def __exit__(self, *args):
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
