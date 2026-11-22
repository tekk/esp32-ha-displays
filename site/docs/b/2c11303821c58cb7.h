#ifndef _GT911_TOUCH_H
#define _GT911_TOUCH_H

#include <stdint.h>
#include "driver/i2c_master.h"
#include "esp_lcd_touch.h"

// Thin wrapper around esp_lcd_touch_gt911 for the F550 / JC8048F550 board.
// The I2C master bus is created by the sketch (port 0, SDA 2 / SCL 3) and the
// GT911 address is detected by probing 0x5D / 0x14 before calling begin().
class gt911_touch
{
public:
    // sda/scl are kept for compatibility; the bus pins come from the handle.
    gt911_touch(int8_t sda_pin, int8_t scl_pin, int8_t rst_pin = -1, int8_t int_pin = -1);

    // Returns false when the controller is absent or cannot be initialized.
    bool begin(i2c_master_bus_handle_t bus, uint8_t dev_addr,
               uint16_t x_max, uint16_t y_max);
    bool getTouch(uint16_t *x, uint16_t *y);
    void set_rotation(uint8_t r);

private:
    int8_t _sda, _scl, _rst, _int;
    esp_lcd_touch_handle_t _tp;
};

#endif
