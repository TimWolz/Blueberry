import numpy as np
from smbus2 import SMBus  # This package does the i2c communication
from time import sleep
import struct as st

address = 0x76
REG_DATA = 0xF7
REG_CONTROL = 0xF4
REG_CAL_T = 0x88
REG_CAL_H = 0xE1
REG_CAL_P = 0x8E


class Thermometer:
    """
    Class to communicate with the SMB280 temperature sensor. Extracts the temperature and also shows the
    temperature on the LEDs of the SEEED 4 mic array. The latter function may be moved later.
    """
    def __init__(self):
        """
        In the init routine we get the calibration data for the conversion of ADC values to temperature.
        We have to shift the bytes to get the correct values, which are stored on the chip.
        Also, we calculate the register value for the forced mode with an oversampling of 1. This means we have to start
        the measurement manually.
        """
        with SMBus(1) as bus:
            cal_data_T = bus.read_i2c_block_data(address, REG_CAL_T, 6)
            cal_data_H0 = bus.read_i2c_block_data(address, 0xA1, 1)
            cal_data_H = bus.read_i2c_block_data(address, REG_CAL_H, 7)
            cal_data_P = bus.read_i2c_block_data(address, REG_CAL_P, 18)

        self.dig_T1 = (cal_data_T[1] << 8) + cal_data_T[0]
        self.dig_T2 = (cal_data_T[3] << 8) + cal_data_T[2]
        self.dig_T3 = (cal_data_T[5] << 8) + cal_data_T[4]
        
        self.dig_P = [0]
        for i in np.arange(0,18,2):
            if i == 0:
                self.dig_P.append((cal_data_P[i+1] << 8) + cal_data_P[i])
            else:
                self.dig_P.append(st.unpack('h', st.pack('H',(cal_data_P[i+1] << 8) + cal_data_P[i]))[0])

        self.dig_H1 = cal_data_H0[0]
        self.dig_H2 = st.unpack('h', st.pack('H', (cal_data_H[1] << 8) + cal_data_H[0]))[0]
        self.dig_H3 = cal_data_H[2]
        self.dig_H4 = st.unpack('h', st.pack('H', (cal_data_H[3] << 4) + (cal_data_H[4] & 15)))[0]
        self.dig_H5 = st.unpack('h', st.pack('H', (cal_data_H[4] >> 4 & 0x0F) | (cal_data_H[5] << 4)))[0]
        self.dig_H6 = st.unpack('b', st.pack('B', cal_data_H[6]))[0]
        
        self.oversample_temp = 1
        self.oversample_pres = 1
        self.mode = 1
        # need to shift the bits for the control reg
        self.control = self.oversample_temp << 5 | self.oversample_pres << 2 | self.mode
        self.good_temp=22

    def get_temperature(self):
        """
        Here we get the temperature, humdity and, pressure, by writing into the control register and then by asking the data from the
        data register. After that we have to convert the data to temperature. No explanations given in the data
        sheet. It's basically copy and past
        :return: temperature, humidity, pressure (float, float, float)
        """
        with SMBus(1) as bus:
            bus.write_byte_data(address, REG_CONTROL, self.control)
            sleep(0.5)
            data = bus.read_i2c_block_data(address, REG_DATA, 8)
        temp_raw = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
        pres_raw = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        hum_raw = (data[6] << 8) + data[7]
        var1 = (((temp_raw >> 3)-(self.dig_T1 << 1)) * self.dig_T2) >> 11
        var2 = (((((temp_raw >> 4) - self.dig_T1) * ((temp_raw >> 4) - self.dig_T1)) >> 12) * self.dig_T3) >> 14
        t_fine = var1+var2
        temperature = float(((t_fine * 5) + 128) >> 8)/100
        
        humidity = t_fine - 76800.0
        humidity = (hum_raw - (self.dig_H4 * 64.0 + self.dig_H5 / 16384.0 * humidity)) * (self.dig_H2 / 65536.0 * (1.0 + self.dig_H6 / 67108864.0 * humidity * (1.0 + self.dig_H3 / 67108864.0 * humidity)))
        humidity = humidity * (1.0 - self.dig_H1 * humidity / 524288.0)
            
        var1 = t_fine / 2.0 - 64000.0
        var2 = var1 * var1 * self.dig_P[6] / 32768.0
        var2 = var2 + var1 * self.dig_P[5] * 2.0
        var2 = var2 / 4.0 + self.dig_P[4] * 65536.0
        var1 = (self.dig_P[3] * var1 * var1 / 524288.0 + self.dig_P[2] * var1) / 524288.0
        var1 = (1.0 + var1 / 32768.0) * self.dig_P[1]

        pressure = 1048576.0 - pres_raw
        pressure = ((pressure - var2 / 4096.0) * 6250.0) / var1
        var1 = self.dig_P[9] * pressure * pressure / 2147483648.0
        var2 = pressure * self.dig_P[8] / 32768.0
        pressure = (pressure + (var1 + var2 + self.dig_P[7]) / 16.0)/100
        
        return temperature, humidity, pressure

    # ToDo: move to led_helper and pass temperature
    def show_temperature(self, leds, value=64, leds_num=(9, 10, 11, 0)):
        """
        Converts the measured temperature into the LED colorcode. At good temp all 4 leds shine green.
        If it's colder the LEDs change to blue, one for each degree. If it's warmer, they change to red.
        :param leds: the led object to be controlled
        :param value: brightness of the LED
        :param leds_num: The led number on the LED stripe
        :return:
        """
        temp, _, _ = self.get_temperature()
        difference = int(np.rint(temp - self.good_temp))
        if difference > 4:
            difference = 4
        if difference < -4:
            difference = -4

        if difference < 0:
            for i in np.arange(difference * (-1)):
                leds.set_pixel(leds_num[i], 0, 0, value, bright_percent=0.1)
            for i in np.arange(difference * (-1), 4):
                leds.set_pixel(leds_num[i], 0, value, 0, bright_percent=0.1)
        elif difference > 0:
            for i in np.arange(4 - difference):
                leds.set_pixel(leds_num[i], 0, value, 0, bright_percent=0.1)
            for i in np.arange(4 - difference, 4):
                leds.set_pixel(leds_num[i], value, 0, 0, bright_percent=0.1)
        else:
            for i in np.arange(4):
                leds.set_pixel(leds_num[i], 0, value, 0, bright_percent=0.1)
        leds.show()
