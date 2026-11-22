#pragma once
#include "lvgl.h"

#ifdef __cplusplus
extern "C" {
#endif

// Creates the WiFi scan screen and starts the first scan.
// Call once from setup() after lvgl_init().
void wifi_screen_init(void);

#ifdef __cplusplus
}
#endif
