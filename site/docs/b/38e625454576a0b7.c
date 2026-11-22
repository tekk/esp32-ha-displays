#include <stdio.h>
#include "esp_err.h"
#include "esp_log.h"

#include "lvgl.h"
#include "lv_demos.h"
#include "esp_lv_adapter.h"
#include "lcd_init.h"
#include "backlight.h"
#include "led_strip_init.h"
#include "led_strip_gui.h"
#include "knob_gui.h"
#include "mjpeg_gui.h"
#include "sd_card.h"
#include "music_gui.h"

#define IMG_PATH    "/sdcard/pic"

static const char (*image_filename)[256] = NULL;
#define TAG     "main"

//将需要的例子修改为1，一次只建议开启一个
#define LV_DEMO_WIDGETS     1       //lvgl demo
#define LED_STRIP_DEMO      0       //灯带
#define KNOB_DEMO           0       //旋钮控制电脑
#define MJPEG_DEMO          0       //播放sd卡里的mjpeg视频
#define IMAGE_DEMO          0       //显示SD卡中的图片
#define MSC_DEMO            0
#define MUSIC_DEMO          0       //随机播放sd卡中的一首mp3/wav，无UI

#define UI_DEMOS (LV_DEMO_WIDGETS || LED_STRIP_DEMO || KNOB_DEMO || \
                  MJPEG_DEMO || IMAGE_DEMO || MSC_DEMO)

void app_main(void)
{
    esp_err_t ret;

    ESP_LOGI(TAG, "Starting SD card initialization");

#if UI_DEMOS
    lcd_backlight_init();
    lcd_backlight_on();
#endif

    ret = sdcard_mount();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "SD card mount failed: %s", esp_err_to_name(ret));
    }

#if MUSIC_DEMO
    ret = music_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Music init failed: %s", esp_err_to_name(ret));
    }
#endif

#if UI_DEMOS
    lcd_init();
    if (esp_lv_adapter_lock(-1) != ESP_OK) {
        ESP_LOGE(TAG, "Failed to lock LVGL for UI creation");
        return;
    }
    sdcard_filelist(IMG_PATH, &image_filename);
#if LV_DEMO_WIDGETS
    lv_demo_widgets();
#endif
#if LED_STRIP_DEMO
    led_strip_init();
    led_strip_gui();
#endif
#if KNOB_DEMO
    knob_hid_gui();
#endif
#if MJPEG_DEMO
    mjepg_gui();
#endif
#if IMAGE_DEMO
    img_gui();
#endif
    esp_lv_adapter_unlock();
#endif
}
