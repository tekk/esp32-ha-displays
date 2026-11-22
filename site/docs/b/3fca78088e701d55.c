/*
 * F550 entry point.
 *
 * All hardware bring-up (RGB LCD + GT911 touch) and the LVGL integration
 * live in lcd_lvgl.c. This file just starts it and then idles; LVGL
 * renders in its own task created by esp_lvgl_port.
 */
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "lcd_lvgl.h"
#include "lvgl.h"
#include "lv_demos.h"
#include "esp_lvgl_port.h"
static const char *TAG = "F550_MAIN";

void app_main(void)
{
    esp_err_t ret = lcd_lvgl_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "lcd_lvgl_init failed: %s", esp_err_to_name(ret));
    }
    if (lvgl_port_lock(0)) {
        //lv_demo_music();
         //lv_demo_benchmark();
         lv_demo_widgets();

        lvgl_port_unlock();
    }
 
}
