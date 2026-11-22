#include "esp_err.h"
#include "esp_log.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_touch_gt911.h"
#include "gt911_touch.h"

static const char *TAG = "gt911_touch";

// F550 reference: 400 kHz I2C, 16-bit register addresses, no control phase,
// finite transaction timeout so a stuck bus cannot hang the sketch.
#define TOUCH_IO_SPEED_HZ   400000
#define TOUCH_IO_TIMEOUT_MS 1000

gt911_touch::gt911_touch(int8_t sda_pin, int8_t scl_pin, int8_t rst_pin, int8_t int_pin)
    : _sda(sda_pin), _scl(scl_pin), _rst(rst_pin), _int(int_pin), _tp(NULL)
{
}

bool gt911_touch::begin(i2c_master_bus_handle_t bus, uint8_t dev_addr,
                        uint16_t x_max, uint16_t y_max)
{
    if (bus == NULL || dev_addr == 0) {
        ESP_LOGE(TAG, "invalid I2C bus or GT911 address");
        return false;
    }

    esp_lcd_panel_io_i2c_config_t io_cfg = {};
    io_cfg.dev_addr = dev_addr;
    io_cfg.scl_speed_hz = TOUCH_IO_SPEED_HZ;
    io_cfg.control_phase_bytes = 1;
    io_cfg.dc_bit_offset = 0;
    io_cfg.lcd_cmd_bits = 16;
    io_cfg.lcd_param_bits = 0;
    io_cfg.transaction_timeout_ms = TOUCH_IO_TIMEOUT_MS;
    io_cfg.flags.disable_control_phase = 1;

    esp_lcd_panel_io_handle_t io = NULL;
    esp_err_t ret = esp_lcd_new_panel_io_i2c(bus, &io_cfg, &io);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "GT911 IO init failed: %s", esp_err_to_name(ret));
        return false;
    }

    esp_lcd_touch_config_t tp_cfg = {};
    tp_cfg.x_max = x_max;
    tp_cfg.y_max = y_max;
    tp_cfg.rst_gpio_num = (gpio_num_t)_rst;
    tp_cfg.int_gpio_num = (gpio_num_t)_int;

    ret = esp_lcd_touch_new_i2c_gt911(io, &tp_cfg, &_tp);
    if (ret != ESP_OK) {
        // The bundled driver frees its handle on error but still writes it
        // back, so clear it explicitly before deleting the IO.
        ESP_LOGE(TAG, "GT911 init failed: %s", esp_err_to_name(ret));
        esp_lcd_panel_io_del(io);
        _tp = NULL;
        return false;
    }

    ESP_LOGI(TAG, "GT911 touch ready (addr 0x%02X, %ux%u)",
             (unsigned)dev_addr, (unsigned)x_max, (unsigned)y_max);
    return true;
}

bool gt911_touch::getTouch(uint16_t *x, uint16_t *y)
{
    if (_tp == NULL) {
        return false;
    }

    uint16_t strength[1] = {0};
    uint8_t point_num = 0;
    if (esp_lcd_touch_read_data(_tp) != ESP_OK) {
        return false;
    }
    return esp_lcd_touch_get_coordinates(_tp, x, y, strength, &point_num, 1);
}

void gt911_touch::set_rotation(uint8_t r)
{
    if (_tp == NULL) {
        return;
    }

    switch (r) {
    case 0:
        esp_lcd_touch_set_swap_xy(_tp, false);
        esp_lcd_touch_set_mirror_x(_tp, false);
        esp_lcd_touch_set_mirror_y(_tp, false);
        break;
    case 1:
        esp_lcd_touch_set_swap_xy(_tp, false);
        esp_lcd_touch_set_mirror_x(_tp, true);
        esp_lcd_touch_set_mirror_y(_tp, true);
        break;
    case 2:
        esp_lcd_touch_set_swap_xy(_tp, false);
        esp_lcd_touch_set_mirror_x(_tp, false);
        esp_lcd_touch_set_mirror_y(_tp, false);
        break;
    case 3:
        esp_lcd_touch_set_swap_xy(_tp, false);
        esp_lcd_touch_set_mirror_x(_tp, true);
        esp_lcd_touch_set_mirror_y(_tp, true);
        break;
    }
}
