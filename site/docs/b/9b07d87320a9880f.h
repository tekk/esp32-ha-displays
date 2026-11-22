/*
 * lcd_lvgl.h — F550 (JC8048F550) LCD + touch + LVGL initialization.
 *
 * Brings up the RGB ST7262 panel and the GT911 touch, then initializes
 * LVGL through the official `esp_lvgl_port` component (RGB path) and
 * builds a small demo UI.
 */
#pragma once

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Initialize the RGB LCD + GT911 touch and start LVGL (esp_lvgl_port).
 * LVGL renders in its own task; after this returns, the UI is live.
 *
 * @return ESP_OK on success, or an error code if a critical step failed
 *         (panel / LVGL). Touch failure is non-fatal (UI still works).
 */
esp_err_t lcd_lvgl_init(void);

#ifdef __cplusplus
}
#endif
