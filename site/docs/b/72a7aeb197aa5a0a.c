/*
 * Minimal SD-card music player for F318 (ESP32-S31), ESP-IDF 6.1.
 * Same audio path as es8389/t1, but plays one random mp3/wav from
 * /sdcard/music once at startup. No UI, no control state machine.
 */
#include <stdio.h>
#include <string.h>
#include <strings.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

#include "esp_err.h"
#include "esp_log.h"
#include "esp_random.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "driver/i2s_std.h"

#include "esp_codec_dev.h"
#include "esp_codec_dev_defaults.h"
#include "audio_player.h"

#include "sd_card.h"
#include "pinconfig.h"
#include "music_gui.h"

#define TAG "music"

#define CODEC_I2C_PORT       (I2C_NUM_0)
#define CODEC_I2C_SCL_PIN    (PIN_CODEC_I2C_SCL)
#define CODEC_I2C_SDA_PIN    (PIN_CODEC_I2C_SDA)
#define CODEC_I2C_FREQ_HZ    (400000)
#define ES8389_I2C_ADDR      (0x20)

#define CODEC_I2S_PORT       (I2S_NUM_0)
#define CODEC_I2S_BCLK_PIN   (PIN_I2S_BCK)
#define CODEC_I2S_WS_PIN     (PIN_I2S_WS)
#define CODEC_I2S_DOUT_PIN   (PIN_I2S_DO)
#define CODEC_I2S_DIN_PIN    (PIN_I2S_DIN)
#define CODEC_MCLK_PIN_OUT   (PIN_I2S_MCLK)
#define CODEC_PA_PIN         (PIN_PA_CTRL)

#define AUDIO_SAMPLE_RATE    (16000)
#define AUDIO_BITS           (16)
#define AUDIO_CHANNELS       (2)
#define PLAY_VOLUME          (100)
#define CODEC_USE_MCLK       (false)
#define CODEC_NO_DAC_REF     (true)

#define MUSIC_PATH           "/sdcard/music"
#define MAX_TRACKS           (20)
#define MAX_PATH_LEN         (320)

static i2c_master_bus_handle_t s_i2c_bus = NULL;
static i2s_chan_handle_t       s_i2s_tx = NULL;
static esp_codec_dev_handle_t  s_play_dev = NULL;
static SemaphoreHandle_t       s_track_done = NULL;

static esp_err_t board_i2c_init(void)
{
    i2c_master_bus_config_t bus_cfg = {
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .i2c_port = CODEC_I2C_PORT,
        .scl_io_num = CODEC_I2C_SCL_PIN,
        .sda_io_num = CODEC_I2C_SDA_PIN,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    return i2c_new_master_bus(&bus_cfg, &s_i2c_bus);
}

static esp_err_t board_i2s_init(void)
{
    i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(CODEC_I2S_PORT, I2S_ROLE_MASTER);
    chan_cfg.dma_desc_num = 10;
    chan_cfg.dma_frame_num = 480;

    esp_err_t ret = i2s_new_channel(&chan_cfg, &s_i2s_tx, NULL);
    if (ret != ESP_OK) {
        return ret;
    }

    i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(AUDIO_SAMPLE_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(AUDIO_BITS, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = CODEC_MCLK_PIN_OUT,
            .bclk = CODEC_I2S_BCLK_PIN,
            .ws   = CODEC_I2S_WS_PIN,
            .dout = CODEC_I2S_DOUT_PIN,
            .din  = CODEC_I2S_DIN_PIN,
        },
    };
    return i2s_channel_init_std_mode(s_i2s_tx, &std_cfg);
}

static esp_err_t board_codec_init(void)
{
    audio_codec_i2s_cfg_t i2s_cfg = {
        .port = CODEC_I2S_PORT,
        .tx_handle = s_i2s_tx,
    };
    const audio_codec_data_if_t *data_if = audio_codec_new_i2s_data(&i2s_cfg);
    if (data_if == NULL) {
        return ESP_FAIL;
    }

    audio_codec_i2c_cfg_t i2c_cfg = {
        .port = CODEC_I2C_PORT,
        .addr = ES8389_I2C_ADDR,
        .bus_handle = s_i2c_bus,
        .clock_speed_hz = CODEC_I2C_FREQ_HZ,
    };
    const audio_codec_ctrl_if_t *ctrl_if = audio_codec_new_i2c_ctrl(&i2c_cfg);
    if (ctrl_if == NULL) {
        return ESP_FAIL;
    }

    const audio_codec_gpio_if_t *gpio_if = audio_codec_new_gpio();
    if (gpio_if == NULL) {
        return ESP_FAIL;
    }

    es8389_codec_cfg_t es8389_cfg = {
        .ctrl_if = ctrl_if,
        .gpio_if = gpio_if,
        .codec_mode = ESP_CODEC_DEV_WORK_MODE_DAC,
        .pa_pin = CODEC_PA_PIN,
        .pa_reverted = false,
        .master_mode = false,
        .use_mclk = CODEC_USE_MCLK,
        .no_dac_ref = CODEC_NO_DAC_REF,
        .hw_gain = {
            .pa_voltage = 5.0f,
            .codec_dac_voltage = 3.3f,
            .pa_gain = 6.0f,
        },
    };
    const audio_codec_if_t *codec_if = es8389_codec_new(&es8389_cfg);
    if (codec_if == NULL) {
        return ESP_FAIL;
    }

    esp_codec_dev_cfg_t dev_cfg = {
        .dev_type = ESP_CODEC_DEV_TYPE_OUT,
        .codec_if = codec_if,
        .data_if = data_if,
    };
    s_play_dev = esp_codec_dev_new(&dev_cfg);
    if (s_play_dev == NULL) {
        return ESP_FAIL;
    }

    esp_codec_dev_sample_info_t fs = {
        .sample_rate = AUDIO_SAMPLE_RATE,
        .channel = AUDIO_CHANNELS,
        .bits_per_sample = AUDIO_BITS,
    };
    int ret = esp_codec_dev_open(s_play_dev, &fs);
    if (ret != ESP_CODEC_DEV_OK) {
        ESP_LOGE(TAG, "Open codec failed: %d", ret);
        return ESP_FAIL;
    }
    esp_codec_dev_set_out_vol(s_play_dev, PLAY_VOLUME);
    return ESP_OK;
}

static esp_err_t music_write(void *buffer, size_t len, size_t *bytes_written, uint32_t timeout_ms)
{
    (void)timeout_ms;
    int ret = esp_codec_dev_write(s_play_dev, buffer, (int)len);
    if (ret == ESP_CODEC_DEV_OK) {
        *bytes_written = len;
        return ESP_OK;
    }
    *bytes_written = 0;
    return ESP_FAIL;
}

static esp_err_t music_reconfig_clk(uint32_t rate, uint32_t bits, i2s_slot_mode_t ch)
{
    i2s_std_config_t std_cfg = {
        .clk_cfg  = I2S_STD_CLK_DEFAULT_CONFIG(rate),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG((i2s_data_bit_width_t)bits, ch),
        .gpio_cfg = {
            .mclk = CODEC_MCLK_PIN_OUT,
            .bclk = CODEC_I2S_BCLK_PIN,
            .ws   = CODEC_I2S_WS_PIN,
            .dout = CODEC_I2S_DOUT_PIN,
            .din  = CODEC_I2S_DIN_PIN,
        },
    };
    if (bits == 24) {
        std_cfg.clk_cfg.mclk_multiple = I2S_MCLK_MULTIPLE_384;
    }

    ESP_LOGI(TAG, "Track format: %lu Hz, %lu bit, %s", rate, bits,
             ch == I2S_SLOT_MODE_MONO ? "mono" : "stereo");
    esp_err_t ret = i2s_channel_disable(s_i2s_tx);
    ret |= i2s_channel_reconfig_std_clock(s_i2s_tx, &std_cfg.clk_cfg);
    ret |= i2s_channel_reconfig_std_slot(s_i2s_tx, &std_cfg.slot_cfg);
    ret |= i2s_channel_enable(s_i2s_tx);
    return ret;
}

static esp_err_t music_mute(AUDIO_PLAYER_MUTE_SETTING setting)
{
    return esp_codec_dev_set_out_mute(s_play_dev, setting == AUDIO_PLAYER_MUTE);
}

static void music_callback(audio_player_cb_ctx_t *ctx)
{
    if (ctx != NULL && ctx->audio_event == AUDIO_PLAYER_CALLBACK_EVENT_IDLE && s_track_done != NULL) {
        xSemaphoreGive(s_track_done);
    }
}

static bool is_music_file(const char *name)
{
    const char *ext = strrchr(name, '.');
    if (ext == NULL) {
        return false;
    }
    return strcasecmp(ext, ".mp3") == 0 || strcasecmp(ext, ".wav") == 0;
}

static void music_task(void *arg)
{
    (void)arg;
    const char (*files)[256] = NULL;
    char tracks[MAX_TRACKS][256];
    int count = sdcard_filelist(MUSIC_PATH, &files);
    int n = 0;

    for (int i = 0; i < count && n < MAX_TRACKS; i++) {
        if (!is_music_file(files[i])) {
            continue;
        }
        snprintf(tracks[n], sizeof(tracks[n]), "%s", files[i]);
        n++;
    }

    if (n == 0) {
        ESP_LOGE(TAG, "No mp3/wav file in %s", MUSIC_PATH);
        vTaskDelete(NULL);
        return;
    }

    int idx = (int)(esp_random() % (uint32_t)n);
    char path[MAX_PATH_LEN];
    snprintf(path, sizeof(path), "%s/%s", MUSIC_PATH, tracks[idx]);

    FILE *fp = fopen(path, "rb");
    if (fp == NULL) {
        ESP_LOGE(TAG, "fopen failed: %s", path);
        vTaskDelete(NULL);
        return;
    }

    ESP_LOGI(TAG, "Playing random track %d/%d: %s", idx + 1, n, path);
    esp_err_t ret = audio_player_play(fp); /* player owns fp on ESP_OK */
    if (ret == ESP_OK) {
        xSemaphoreTake(s_track_done, portMAX_DELAY);
        ESP_LOGI(TAG, "Playback finished");
    } else {
        fclose(fp);
        ESP_LOGE(TAG, "audio_player_play failed: %s", esp_err_to_name(ret));
    }

    vTaskDelete(NULL);
}

esp_err_t music_init(void)
{
    s_track_done = xSemaphoreCreateBinary();
    if (s_track_done == NULL) {
        return ESP_FAIL;
    }

    esp_err_t ret = board_i2c_init();
    if (ret != ESP_OK) {
        return ret;
    }
    ret = board_i2s_init();
    if (ret != ESP_OK) {
        return ret;
    }
    ret = board_codec_init();
    if (ret != ESP_OK) {
        return ret;
    }

    audio_player_config_t player_cfg = {
        .mute_fn = music_mute,
        .clk_set_fn = music_reconfig_clk,
        .write_fn = music_write,
        .priority = 5,
        .coreID = 0,
    };
    ret = audio_player_new(player_cfg);
    if (ret != ESP_OK) {
        return ret;
    }
    ret = audio_player_callback_register(music_callback, NULL);
    if (ret != ESP_OK) {
        return ret;
    }

    xTaskCreatePinnedToCore(music_task, "music", 4096, NULL, 4, NULL, 1);
    ESP_LOGI(TAG, "ES8389 ready, random track will start shortly, volume=%d", PLAY_VOLUME);
    return ESP_OK;
}
