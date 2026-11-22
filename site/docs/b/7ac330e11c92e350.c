/*
 * lcd_lvgl.c — F550 (JC8048F550) LCD + touch + LVGL (via esp_lvgl_port).
 *
 * Hardware parameters are taken verbatim from guition_boards/jc8048f550
 * (board_devices.yaml + board_peripherals.yaml), the board the reference
 * display_lv_demo_widgets example is built for.
 *
 *   - Display : RGB (ST7262), 800x480, RGB565, 16-bit data bus, PCLK 24 MHz
 *   - Touch   : GT911, I2C port 0 (SDA 2 / SCL 3), addr 0x5D/0x14 (7-bit), no RST
 *   - Backlight: GPIO 17 (active high)
 *
 * Target: ESP32-S3.
 *
 * LVGL is integrated through the official Espressif `esp_lvgl_port` component
 * (v2.9.0, LVGL v9 path), which drives the RGB panel and the GT911 touch.
 */
#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_heap_caps.h"
#include "esp_lcd_panel_rgb.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_touch.h"
#include "esp_lcd_touch_gt911.h"
#include "esp_err.h"
#include "esp_log.h"
#include "lvgl.h"
#include "esp_lvgl_port.h"

static const char *TAG = "F550_JC8048F550";

/* ----------------------------- LCD (RGB) ----------------------------- */
#define LCD_H_RES             800
#define LCD_V_RES             480
#define LCD_PCLK_HZ           24000000   /* rgb_panel_config.timings.pclk_hz */
#define LCD_HSYNC_GPIO        44         /* hsync_gpio_num */
#define LCD_VSYNC_GPIO        45         /* vsync_gpio_num */
#define LCD_DE_GPIO           43         /* de_gpio_num */
#define LCD_PCLK_GPIO         40         /* pclk_gpio_num */
#define LCD_DISP_GPIO         -1         /* disp_gpio_num */
/* data_gpio_nums from board_devices.yaml rgb_panel_config.data_gpio_nums */
#define LCD_DATA_GPIO_NUMS    {36, 37, 38, 39, 46, 7, 35, 51, 50, 49, 48, 4, 5, 0, 1, 6}

/* --------------------------- Backlight ------------------------------- */
#define BL_GPIO_NUM           17   /* ledc_backlight.gpio_num (active high) */

/* ----------------------------- Touch --------------------------------- */
#define TOUCH_I2C_PORT        0    /* i2c_master.port */
#define TOUCH_I2C_SDA         2    /* board_peripherals.yaml i2c_master.sda */
#define TOUCH_I2C_SCL         3    /* board_peripherals.yaml i2c_master.scl */
/* board_devices.yaml i2c_addr is [0xBA, 0x28] (8-bit); esp_lcd I2C uses the
 * 7-bit forms 0x5D / 0x14. We probe both and use whichever ACKs. */
#define TOUCH_I2C_SPEED       400000
#define TOUCH_RST_GPIO        -1   /* touch_config.rst_gpio_num (no reset) */
#define TOUCH_INT_GPIO        -1   /* touch_config.int_gpio_num (polling) */
#define TOUCH_X_MAX           800
#define TOUCH_Y_MAX           480



esp_err_t lcd_lvgl_init(void)
{
    esp_err_t ret = ESP_OK;

    /* ---- Backlight on (active high; board uses LEDC on GPIO 17) ---- */
    gpio_config_t bl_cfg = {
        .pin_bit_mask = 1ULL << BL_GPIO_NUM,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&bl_cfg));
    gpio_set_level(BL_GPIO_NUM, 1);
    ESP_LOGI(TAG, "backlight on (GPIO %d)", BL_GPIO_NUM);

    /* ---- I2C master bus for GT911 ---- */
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = TOUCH_I2C_PORT,
        .sda_io_num = TOUCH_I2C_SDA,
        .scl_io_num = TOUCH_I2C_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags = { .enable_internal_pullup = true },
    };
    i2c_master_bus_handle_t i2c_bus = NULL;
    ret = i2c_new_master_bus(&bus_cfg, &i2c_bus);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "I2C bus init failed: %s", esp_err_to_name(ret));
    }

    /* ---- GT911 touch: probe address, then init driver (no RST on this board) ---- */
    esp_lcd_touch_handle_t touch_handle = NULL;
    if (i2c_bus) {
        const uint16_t gt911_addrs[] = { 0x5D, 0x14 };
        uint16_t gt911_addr = 0;
        for (int i = 0; i < (int)(sizeof(gt911_addrs) / sizeof(gt911_addrs[0])); i++) {
            if (i2c_master_probe(i2c_bus, gt911_addrs[i], 50) == ESP_OK) {
                gt911_addr = gt911_addrs[i];
                ESP_LOGI(TAG, "GT911 found at I2C addr 0x%02X", gt911_addr);
                break;
            }
        }
        if (gt911_addr == 0) {
            ESP_LOGW(TAG, "GT911 not found on I2C (checked 0x5D/0x14) - touch disabled");
        } else {
            esp_lcd_panel_io_handle_t touch_io = NULL;
            esp_lcd_panel_io_i2c_config_t io_cfg = {
                .dev_addr = gt911_addr,
                .scl_speed_hz = TOUCH_I2C_SPEED,
                .control_phase_bytes = 1,
                .dc_bit_offset = 0,
                .lcd_cmd_bits = 16,
                .lcd_param_bits = 0,
                .transaction_timeout_ms = 1000,
                .flags = { .disable_control_phase = true },
            };
            ret = esp_lcd_new_panel_io_i2c(i2c_bus, &io_cfg, &touch_io);
            if (ret == ESP_OK) {
                esp_lcd_touch_config_t touch_cfg = {
                    .x_max = TOUCH_X_MAX,
                    .y_max = TOUCH_Y_MAX,
                    .rst_gpio_num = TOUCH_RST_GPIO,
                    .int_gpio_num = TOUCH_INT_GPIO,
                    .flags = { .swap_xy = 0, .mirror_x = 0, .mirror_y = 0 },
                };
                ret = esp_lcd_touch_new_i2c_gt911(touch_io, &touch_cfg, &touch_handle);
                if (ret != ESP_OK) {
                    ESP_LOGW(TAG, "GT911 init failed: %s (touch disabled)", esp_err_to_name(ret));
                    esp_lcd_panel_io_del(touch_io);
                    touch_handle = NULL;
                } else {
                    ESP_LOGI(TAG, "GT911 touch ready");
                }
            } else {
                ESP_LOGE(TAG, "GT911 IO init failed: %s", esp_err_to_name(ret));
            }
        }
    }

    /* ---- RGB LCD panel (ST7262) ---- */
    esp_lcd_rgb_panel_config_t panel_cfg = {
        .clk_src = LCD_CLK_SRC_DEFAULT,
        .timings = {
            .pclk_hz = LCD_PCLK_HZ,
            .h_res = LCD_H_RES,
            .v_res = LCD_V_RES,
            .hsync_pulse_width = 4,
            .hsync_back_porch = 8,
            .hsync_front_porch = 8,
            .vsync_pulse_width = 4,
            .vsync_back_porch = 8,
            .vsync_front_porch = 8,
            .flags = {
                .hsync_idle_low = 0,
                .vsync_idle_low = 0,
                .de_idle_high = 0,
                .pclk_active_neg = 1,
                .pclk_idle_high = 0,
            },
        },
        .data_width = 16,
        .in_color_format = LCD_COLOR_FMT_RGB565,
        .out_color_format = LCD_COLOR_FMT_RGB565,
        .num_fbs = 3,
        .bounce_buffer_size_px = 0,
        .dma_burst_size = 64,
        .hsync_gpio_num = LCD_HSYNC_GPIO,
        .vsync_gpio_num = LCD_VSYNC_GPIO,
        .de_gpio_num = LCD_DE_GPIO,
        .pclk_gpio_num = LCD_PCLK_GPIO,
        .disp_gpio_num = LCD_DISP_GPIO,
        .data_gpio_nums = LCD_DATA_GPIO_NUMS,
        .flags = {
            .disp_active_low = 0,
            .refresh_on_demand = 0,
            .fb_in_psram = 1,
            .double_fb = 0,
            .no_fb = 0,
            .bb_invalidate_cache = 0,
        },
    };
    esp_lcd_panel_handle_t panel = NULL;
    ret = esp_lcd_new_rgb_panel(&panel_cfg, &panel);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "RGB panel create failed: %s", esp_err_to_name(ret));
        return ret;
    }
    ret = esp_lcd_panel_init(panel);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "RGB panel init failed: %s", esp_err_to_name(ret));
        return ret;
    }
    ESP_LOGI(TAG, "RGB LCD ready (%dx%d)", LCD_H_RES, LCD_V_RES);

    /* ---- LVGL port (esp_lvgl_port, RGB path) ---- */
    lvgl_port_cfg_t port_cfg = ESP_LVGL_PORT_INIT_CONFIG();
    port_cfg.task_stack = 8192;
    ret = lvgl_port_init(&port_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "lvgl_port_init failed: %s", esp_err_to_name(ret));
        return ret;
    }

    lvgl_port_display_cfg_t disp_cfg = {
        .io_handle = NULL,            /* RGB panel: no IO handle */
        .panel_handle = panel,
        .buffer_size = LCD_H_RES * LCD_V_RES,
        .double_buffer = false,
        .hres = LCD_H_RES,
        .vres = LCD_V_RES,
        .color_format = LV_COLOR_FORMAT_RGB565,
        .flags = {
            .buff_spiram = true,      /* S3 PSRAM is not DMA-capable */
            .buff_dma = false,
            .swap_bytes = 0,
        },
    };
    lvgl_port_display_rgb_cfg_t rgb_cfg = {
        .flags = {
            .bb_mode = 0,
            .avoid_tearing = 0,
        },
    };
    lv_display_t *disp = lvgl_port_add_disp_rgb(&disp_cfg, &rgb_cfg);
    if (disp == NULL) {
        ESP_LOGE(TAG, "lvgl_port_add_disp_rgb failed");
        return ESP_FAIL;
    }
    ESP_LOGI(TAG, "LVGL display registered");

    if (touch_handle) {
        lvgl_port_touch_cfg_t tp_cfg = {
            .disp = disp,
            .handle = touch_handle,
            .scale = { .x = 1.0f, .y = 1.0f },
        };
        lv_indev_t *indev = lvgl_port_add_touch(&tp_cfg);
        if (indev == NULL) {
            ESP_LOGW(TAG, "lvgl_port_add_touch failed (touch disabled)");
        } else {
            ESP_LOGI(TAG, "LVGL touch registered");
        }
    }

    ESP_LOGI(TAG, "LVGL UI started");

    return ESP_OK;
}
