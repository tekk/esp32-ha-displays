// ----------------------------------------------------------------------------
// WiFi scan example for the F550 / JC8048F550 (ESP32-S3) board, LVGL 8.
//  - 800x480 RGB LCD (16-bit RGB565, ST7262), PCLK 24 MHz
//  - GT911 capacitive touch (I2C port 0, SDA=2 / SCL=3, addr 0x5D/0x14)
//  - Backlight on GPIO 17 (active high)
// Hardware parameters follow the F550 reference (lvgl_demo_v8 / main/main.c).
// Touch is handled by the gt911_touch class in src/touch/.
//
// Requires the LVGL 8.x Arduino library to be installed.
// ----------------------------------------------------------------------------

#include <Arduino.h>
#include "lvgl.h"
#include "demos/lv_demos.h"
// esp-lcd components (available inside Arduino-ESP32 / ESP-IDF).
#include "esp_lcd_panel_rgb.h"
#include "esp_lcd_panel_ops.h"
#include "driver/ledc.h"
#include "driver/i2c_master.h"
#include "esp_err.h"
#include "esp_heap_caps.h"

// Touch driver shipped with this project (compiled from src/touch/).
#include "src/touch/gt911_touch.h"

// WiFi scan screen (compiled from src/wifi_screen.cpp).
#include "src/wifi_screen.h"

// ----------------------------- Board config ---------------------------------
// F550 / JC8048F550 reference values (lvgl_demo_v8 / main/main.c).
#define LCD_WIDTH   800
#define LCD_HEIGHT  480
#define LCD_PCLK_HZ 24000000

// RGB panel GPIOs (board_devices.yaml rgb_panel_config.data_gpio_nums).
// Cast to gpio_num_t: in C++ an int cannot be implicitly converted to the enum.
#define LCD_HSYNC_GPIO  ((gpio_num_t)44)
#define LCD_VSYNC_GPIO  ((gpio_num_t)45)
#define LCD_DE_GPIO     ((gpio_num_t)43)
#define LCD_PCLK_GPIO   ((gpio_num_t)40)
#define LCD_DATA_GPIO0  ((gpio_num_t)36)
#define LCD_DATA_GPIO1  ((gpio_num_t)37)
#define LCD_DATA_GPIO2  ((gpio_num_t)38)
#define LCD_DATA_GPIO3  ((gpio_num_t)39)
#define LCD_DATA_GPIO4  ((gpio_num_t)46)
#define LCD_DATA_GPIO5  ((gpio_num_t)7)
#define LCD_DATA_GPIO6  ((gpio_num_t)35)
#define LCD_DATA_GPIO7  ((gpio_num_t)51)
#define LCD_DATA_GPIO8  ((gpio_num_t)50)
#define LCD_DATA_GPIO9  ((gpio_num_t)49)
#define LCD_DATA_GPIO10 ((gpio_num_t)48)
#define LCD_DATA_GPIO11 ((gpio_num_t)4)
#define LCD_DATA_GPIO12 ((gpio_num_t)5)
#define LCD_DATA_GPIO13 ((gpio_num_t)0)
#define LCD_DATA_GPIO14 ((gpio_num_t)1)
#define LCD_DATA_GPIO15 ((gpio_num_t)6)

// Backlight on GPIO 17 (active high), driven by LEDC PWM.
#define LCD_BACKLIGHT_GPIO         ((gpio_num_t)17)
#define LCD_BACKLIGHT_LEDC_TIMER   LEDC_TIMER_0
#define LCD_BACKLIGHT_LEDC_CHANNEL LEDC_CHANNEL_0
#define LCD_BACKLIGHT_LEDC_RESOLUTION LEDC_TIMER_8_BIT
#define LCD_BACKLIGHT_PWM_FREQ_HZ  20000

// GT911 I2C bus (port 0, 400 kHz in gt911_touch). Probe both 7-bit addresses:
// the GT911 selects 0x5D or 0x14 depending on the INT level during power-on.
#define TOUCH_I2C_PORT      I2C_NUM_0
#define TOUCH_SDA_GPIO      ((gpio_num_t)2)
#define TOUCH_SCL_GPIO      ((gpio_num_t)3)
#define TOUCH_ADDR_PRIMARY  0x5D
#define TOUCH_ADDR_BACKUP   0x14

// ----------------------------- Globals --------------------------------------
static esp_lcd_panel_handle_t   g_panel = NULL;
static i2c_master_bus_handle_t  g_touch_bus = NULL;
static lv_disp_draw_buf_t     g_disp_buf;
static lv_disp_drv_t          g_disp_drv;
static lv_indev_drv_t         g_indev_drv;

// Partial draw buffer living in PSRAM.
static lv_color_t *g_buf1 = NULL;

// GT911 touch instance.
static gt911_touch touch(TOUCH_SDA_GPIO, TOUCH_SCL_GPIO, -1, -1);

// --------------------------- Backlight setup --------------------------------
static void lcd_backlight_init(void)
{
    ledc_timer_config_t timer_cfg = {
        .speed_mode       = LEDC_LOW_SPEED_MODE,
        .duty_resolution  = LCD_BACKLIGHT_LEDC_RESOLUTION,
        .timer_num        = LCD_BACKLIGHT_LEDC_TIMER,
        .freq_hz          = LCD_BACKLIGHT_PWM_FREQ_HZ,
        .clk_cfg          = LEDC_AUTO_CLK,
    };
    ledc_timer_config(&timer_cfg);

    ledc_channel_config_t chan_cfg = {
        .gpio_num   = LCD_BACKLIGHT_GPIO,
        .speed_mode = LEDC_LOW_SPEED_MODE,
        .channel    = LCD_BACKLIGHT_LEDC_CHANNEL,
        .timer_sel  = LCD_BACKLIGHT_LEDC_TIMER,
        .duty       = (1 << LCD_BACKLIGHT_LEDC_RESOLUTION) - 1,  // 100%
        .hpoint     = 0,
    };
    ledc_channel_config(&chan_cfg);
}

// ----------------------------- LCD setup ------------------------------------
static void lcd_init(void)
{
    esp_lcd_rgb_panel_config_t panel_config = {
        .clk_src = LCD_CLK_SRC_DEFAULT,
        .timings = {
            .pclk_hz             = LCD_PCLK_HZ,
            .h_res               = LCD_WIDTH,
            .v_res               = LCD_HEIGHT,
            .hsync_pulse_width   = 4,
            .hsync_back_porch    = 8,
            .hsync_front_porch   = 8,
            .vsync_pulse_width   = 4,
            .vsync_back_porch    = 8,
            .vsync_front_porch   = 8,
            .flags = {
                .hsync_idle_low  = false,
                .vsync_idle_low  = false,
                .de_idle_high    = false,
                .pclk_active_neg = true,
                .pclk_idle_high  = false,
            },
        },
        .data_width        = 16,
        .in_color_format   = LCD_COLOR_FMT_RGB565,
        .out_color_format  = LCD_COLOR_FMT_RGB565,
        .num_fbs           = 3,
        .bounce_buffer_size_px = 0,
        .dma_burst_size    = 64,
        .hsync_gpio_num    = LCD_HSYNC_GPIO,
        .vsync_gpio_num    = LCD_VSYNC_GPIO,
        .de_gpio_num       = LCD_DE_GPIO,
        .pclk_gpio_num     = LCD_PCLK_GPIO,
        .disp_gpio_num     = (gpio_num_t)-1,
        .data_gpio_nums = {
            LCD_DATA_GPIO0,  LCD_DATA_GPIO1,  LCD_DATA_GPIO2,  LCD_DATA_GPIO3,
            LCD_DATA_GPIO4,  LCD_DATA_GPIO5,  LCD_DATA_GPIO6,  LCD_DATA_GPIO7,
            LCD_DATA_GPIO8,  LCD_DATA_GPIO9,  LCD_DATA_GPIO10, LCD_DATA_GPIO11,
            LCD_DATA_GPIO12, LCD_DATA_GPIO13, LCD_DATA_GPIO14, LCD_DATA_GPIO15,
            (gpio_num_t)-1, (gpio_num_t)-1, (gpio_num_t)-1, (gpio_num_t)-1,
            (gpio_num_t)-1, (gpio_num_t)-1, (gpio_num_t)-1, (gpio_num_t)-1,
        },
        .flags = {
            .fb_in_psram = true,
        },
    };

    esp_err_t ret = esp_lcd_new_rgb_panel(&panel_config, &g_panel);
    if (ret != ESP_OK) {
        Serial.printf("RGB panel create failed: %s\n", esp_err_to_name(ret));
        return;
    }
    ret = esp_lcd_panel_init(g_panel);
    if (ret != ESP_OK) {
        Serial.printf("RGB panel init failed: %s\n", esp_err_to_name(ret));
    }
}

// ------------------------- Touch I2C bus setup -----------------------------
// Same bus configuration as the F550 reference (port 0, glitch filter 7,
// internal pull-ups). The bus handle is passed to gt911_touch.begin().
static bool touch_i2c_bus_init(void)
{
    // Avoid designated/nested initializers here: GCC's C++ mode mishandles
    // the anonymous-union clk_source member together with .flags.x.
    i2c_master_bus_config_t bus_cfg = {};
    bus_cfg.i2c_port   = TOUCH_I2C_PORT;
    bus_cfg.sda_io_num = TOUCH_SDA_GPIO;
    bus_cfg.scl_io_num = TOUCH_SCL_GPIO;
    bus_cfg.clk_source = I2C_CLK_SRC_DEFAULT;
    bus_cfg.glitch_ignore_cnt = 7;
    bus_cfg.flags.enable_internal_pullup = true;
    esp_err_t ret = i2c_new_master_bus(&bus_cfg, &g_touch_bus);
    if (ret != ESP_OK) {
        Serial.printf("I2C bus init failed: %s\n", esp_err_to_name(ret));
        g_touch_bus = NULL;
        return false;
    }
    return true;
}

// GT911 can sit at 0x5D or 0x14 (INT level at power-on). Probe both 7-bit
// addresses with a finite timeout and use whichever ACKs.
static uint8_t touch_probe_gt911(void)
{
    const uint8_t addrs[] = {TOUCH_ADDR_PRIMARY, TOUCH_ADDR_BACKUP};
    for (uint8_t addr : addrs) {
        if (i2c_master_probe(g_touch_bus, addr, 50) == ESP_OK) {
            Serial.printf("GT911 found at I2C addr 0x%02X\n", (unsigned)addr);
            return addr;
        }
    }
    Serial.println("GT911 not found (checked 0x5D/0x14) - touch disabled");
    return 0;
}

// --------------------------- LVGL callbacks ---------------------------------
static void disp_flush(lv_disp_drv_t *drv, const lv_area_t *area, lv_color_t *color_map)
{
    esp_lcd_panel_draw_bitmap(g_panel,
                              area->x1, area->y1,
                              area->x2 + 1, area->y2 + 1,
                              color_map);
    lv_disp_flush_ready(drv);
}

static void touchpad_read(lv_indev_drv_t *indev_drv, lv_indev_data_t *data)
{
    static uint16_t touch_x = 0, touch_y = 0;
    if (touch.getTouch(&touch_x, &touch_y)) {
        data->state = LV_INDEV_STATE_PRESSED;
        data->point.x = touch_x;
        data->point.y = touch_y;
    } else {
        data->state = LV_INDEV_STATE_RELEASED;
    }
}

static void lvgl_init(void)
{
    lv_init();

    // Partial draw buffer (~50 lines) in PSRAM.
    const size_t buf_lines = 50;
    const size_t buf_px = LCD_WIDTH * buf_lines;
    g_buf1 = (lv_color_t *)heap_caps_malloc(buf_px * sizeof(lv_color_t),
                                           MALLOC_CAP_SPIRAM);
    lv_disp_draw_buf_init(&g_disp_buf, g_buf1, NULL, buf_px);

    lv_disp_drv_init(&g_disp_drv);
    g_disp_drv.hor_res   = LCD_WIDTH;
    g_disp_drv.ver_res   = LCD_HEIGHT;
    g_disp_drv.flush_cb  = disp_flush;
    g_disp_drv.draw_buf  = &g_disp_buf;
    g_disp_drv.user_data = g_panel;
    lv_disp_drv_register(&g_disp_drv);

    lv_indev_drv_init(&g_indev_drv);
    g_indev_drv.type    = LV_INDEV_TYPE_POINTER;
    g_indev_drv.read_cb = touchpad_read;
    lv_indev_drv_register(&g_indev_drv);
}

 

// ------------------------------- Arduino ------------------------------------
void setup()
{
    Serial.begin(115200);
    delay(100);

    // Same order as the F550 reference: backlight, I2C/touch, RGB panel.
    lcd_backlight_init();
    if (touch_i2c_bus_init()) {
        uint8_t addr = touch_probe_gt911();
        if (addr != 0 && !touch.begin(g_touch_bus, addr, LCD_WIDTH, LCD_HEIGHT)) {
            Serial.println("GT911 init failed - touch disabled");
        }
    }
    lcd_init();

    lvgl_init();
    Serial.println("LVGL 8 example ready (F550 800x480).");
    wifi_screen_init();   /* WiFi 扫描界面 */


}

void loop()
{
    // When LV_TICK_CUSTOM is disabled, drive LVGL's tick from millis() here.
#if !defined(LV_TICK_CUSTOM) || (LV_TICK_CUSTOM == 0)
    static uint32_t last_tick = 0;
    uint32_t now = millis();
    lv_tick_inc(now - last_tick);
    last_tick = now;
#endif

    lv_timer_handler();
    delay(5);
}
