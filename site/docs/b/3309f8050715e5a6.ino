// ----------------------------------------------------------------------------
// LVGL 9 example with software display rotation for the F550 / JC8048F550
// (ESP32-S3) board. Hardware parameters follow lvgl_demo_v8.
//  - 800x480 RGB LCD (16-bit RGB565, ST7262), PCLK 24 MHz
//  - GT911 capacitive touch (I2C port 0, SDA=2 / SCL=3, addr 0x5D/0x14)
//  - Backlight on GPIO 17 (active high)
// Touch is handled by the gt911_touch class in src/touch/.
//
// Requires the LVGL 9.x Arduino library to be installed.
// ----------------------------------------------------------------------------

#include <Arduino.h>

// Point LVGL at the lv_conf.h that lives next to this sketch.
// Using LV_CONF_PATH (instead of LV_CONF_INCLUDE_SIMPLE) avoids the
// GCC "__has_include then #include silently fails" bug, so the config
// is reliably pulled in.
 
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

// ----------------------------- Board config ---------------------------------
// F550 / JC8048F550 reference values (same as lvgl_demo_v8).
#define LCD_WIDTH   800
#define LCD_HEIGHT  480
#define LCD_PCLK_HZ 24000000

// Display rotation applied in software (the RGB panel has no HW rotation).
// Supported: LV_DISP_ROTATION_0 / _90 / _180 / _270
#define DISP_ROTATION  LV_DISPLAY_ROTATION_90

// RGB panel GPIOs (same as the lvgl_demo_v8 / F550 reference).
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

// Touch I2C pins (GT911, I2C port 0 same as lvgl_demo_v8).
#define TOUCH_I2C_PORT  I2C_NUM_0
#define TOUCH_SDA_GPIO  ((gpio_num_t)2)
#define TOUCH_SCL_GPIO  ((gpio_num_t)3)
// GT911 selects 0x5D or 0x14 depending on the INT level during power-on.
#define TOUCH_ADDR_PRIMARY  0x5D
#define TOUCH_ADDR_BACKUP   0x14

// ----------------------------- Globals --------------------------------------
static esp_lcd_panel_handle_t g_panel = NULL;
static i2c_master_bus_handle_t g_touch_bus = NULL;

// Partial draw buffer living in PSRAM.
static lv_color_t *g_buf1 = NULL;

// Scratch buffer (PSRAM) used to hold the rotated pixel block before it is
// sent to the panel. Must be at least as large as the draw buffer.
static lv_color_t *g_rot_buf = NULL;

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
    esp_lcd_panel_reset(g_panel);
    ret = esp_lcd_panel_init(g_panel);
    if (ret != ESP_OK) {
        Serial.printf("RGB panel init failed: %s\n", esp_err_to_name(ret));
    }
    esp_lcd_panel_disp_on_off(g_panel, true);
}

// ------------------------- Touch I2C bus setup -----------------------------
// GT911 SDA/SCL are on I2C port 0, so the I2C master bus must be created
// on TOUCH_I2C_PORT before the touch driver is used.
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
// Rotate an RGB565 pixel block. Conventions match LVGL's lv_draw_sw_rotate so
// the result is consistent with lv_display_rotate_area() used below.
// src/dst strides are in BYTES (use lv_draw_buf_width_to_stride).
static void rotate_rgb565(const uint8_t *src, uint8_t *dst,
                          int32_t w, int32_t h,
                          int32_t src_stride, int32_t dst_stride,
                          lv_display_rotation_t rot)
{
    const uint16_t *s = (const uint16_t *)src;
    uint16_t *d = (uint16_t *)dst;
    int32_t ss = src_stride / 2;   // byte stride -> uint16 stride
    int32_t ds = dst_stride / 2;

    if (rot == LV_DISPLAY_ROTATION_90) {
        for (int32_t x = 0; x < w; x++) {
            int32_t di = (w - 1 - x);
            int32_t si = x;
            for (int32_t y = 0; y < h; y++) {
                d[di * ds + y] = s[si];
                si += ss;
            }
        }
    } else if (rot == LV_DISPLAY_ROTATION_270) {
        for (int32_t x = 0; x < w; x++) {
            int32_t di = x * ds;
            int32_t si = x;
            for (int32_t y = 0; y < h; y++) {
                d[di + (h - 1 - y)] = s[si];
                si += ss;
            }
        }
    } else if (rot == LV_DISPLAY_ROTATION_180) {
        for (int32_t y = 0; y < h; y++) {
            int32_t di = (h - 1 - y) * ds;
            int32_t si = y * ss;
            for (int32_t x = 0; x < w; x++) {
                d[di + (w - 1 - x)] = s[si + x];
            }
        }
    }
}

static void disp_flush(lv_display_t *disp, const lv_area_t *area, uint8_t *px_map)
{
    // LVGL hands us a *logical* (un-rotated) area + pixel map. When rotation
    // is active we must rotate both the pixels and the area into the panel's
    // physical coordinate space before pushing to the LCD.
    if (g_rot_buf != NULL) {
        lv_display_rotation_t rot = lv_display_get_rotation(disp);
        if (rot != LV_DISPLAY_ROTATION_0) {
            int32_t w  = lv_area_get_width(area);
            int32_t h  = lv_area_get_height(area);
            lv_color_format_t cf = lv_display_get_color_format(disp);
            uint32_t w_stride = lv_draw_buf_width_to_stride(w, cf);
            uint32_t h_stride = lv_draw_buf_width_to_stride(h, cf);

            // Destination (rotated) width is h for 90/270, w for 0/180.
            uint32_t dst_stride = (rot == LV_DISPLAY_ROTATION_90 ||
                                   rot == LV_DISPLAY_ROTATION_270) ? h_stride : w_stride;

            rotate_rgb565(px_map, (uint8_t *)g_rot_buf, w, h, w_stride, dst_stride, rot);
            px_map = (uint8_t *)g_rot_buf;

            lv_area_t rotated = *area;
            lv_display_rotate_area(disp, &rotated);
            area = &rotated;
        }
    }

    esp_lcd_panel_draw_bitmap(g_panel,
                              area->x1, area->y1,
                              area->x2 + 1, area->y2 + 1,
                              (const void *)px_map);
    lv_display_flush_ready(disp);
}

static void touchpad_read(lv_indev_t *indev, lv_indev_data_t *data)
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
    if (g_buf1 == NULL) {
        Serial.println("LVGL draw buffer alloc failed!");
        return;
    }

    // Rotation scratch buffer: a rotated block is never larger than the draw
    // buffer, so the same size is sufficient.
    g_rot_buf = (lv_color_t *)heap_caps_malloc(buf_px * sizeof(lv_color_t),
                                               MALLOC_CAP_SPIRAM);
    if (g_rot_buf == NULL) {
        Serial.println("LVGL rotation buffer alloc failed!");
    }

    lv_display_t *disp = lv_display_create(LCD_WIDTH, LCD_HEIGHT);
    lv_display_set_flush_cb(disp, disp_flush);
    lv_display_set_buffers(disp, g_buf1, NULL, buf_px * sizeof(lv_color_t),
                           LV_DISPLAY_RENDER_MODE_PARTIAL);

    // Apply the requested software rotation. This makes LVGL render into a
    // 480x800 (for 90/270) logical screen that is rotated onto the 800x480
    // panel by disp_flush(). Touch input is rotated automatically by LVGL.
    lv_display_set_rotation(disp, DISP_ROTATION);


    lv_indev_t *indev = lv_indev_create();
    lv_indev_set_type(indev, LV_INDEV_TYPE_POINTER);
    lv_indev_set_read_cb(indev, touchpad_read);
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
    Serial.println("LVGL 9 example ready (F550 800x480, SW rotation).");
     lv_demo_widgets(); /* 小部件示例 */
    //lv_demo_music();        /* 类似智能手机的现代音乐播放器演示 */
    //  lv_demo_stress();       /* LVGL 压力测试 */
    // lv_demo_benchmark();    /* 用于测量 LVGL 性能或比较不同设置的演示 */


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
