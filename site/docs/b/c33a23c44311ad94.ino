#include <Arduino.h>
#include "esp_adc/adc_oneshot.h"

#define BATT_PIN    (55)
#define N_SAMPLES   (500)

static adc_oneshot_unit_handle_t s_adc = NULL;
static adc_channel_t             s_channel = ADC_CHANNEL_0;

void setup() {
  Serial.begin(115200);

  adc_unit_t unit = ADC_UNIT_2;
  adc_oneshot_io_to_channel(BATT_PIN, &unit, &s_channel);

  adc_oneshot_unit_init_cfg_t init_cfg = {};
  init_cfg.unit_id  = unit;
  init_cfg.ulp_mode = ADC_ULP_MODE_DISABLE;
  adc_oneshot_new_unit(&init_cfg, &s_adc);

  adc_oneshot_chan_cfg_t chan_cfg = {};
  chan_cfg.atten    = ADC_ATTEN_DB_0;
  chan_cfg.bitwidth = ADC_BITWIDTH_DEFAULT;
  adc_oneshot_config_channel(s_adc, s_channel, &chan_cfg);
}

void loop() {
  int32_t sum = 0;
  int     n   = 0;

  for (int i = 0; i < N_SAMPLES; i++) {
    int raw = 0;
    if (adc_oneshot_read(s_adc, s_channel, &raw) == ESP_OK) {
      sum += raw;
      n++;
    }
  }

  Serial.println(n > 0 ? (int)(sum / n) : 0);
  delay(1000);
}
