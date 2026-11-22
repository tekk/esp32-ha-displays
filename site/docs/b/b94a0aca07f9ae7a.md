# Guition JC3636F318

基于 JC3636F318（ESP32-S31）硬件，按厂商 demo 的 PINCONFIG.H 适配的固件。

## 引脚定义

| 功能 | 引脚 |
| --- | --- |
| LCD QSPI SCL / CS / D0-D3 / RST / TE / BLK | GPIO12 / 13 / 14-17 / 18 / 19 / 7 |
| 触摸 I2C (I2C_NUM_1) SDA / SCL / RST / INT | GPIO10 / 11 / 9 / 8 |
| 音频 codec I2C (I2C_NUM_0) SDA / SCL | GPIO42 / 43 |
| I2S BCK / WS / DO / DIN / MCLK | GPIO44 / 46 / 45 / 47 / NC |
| 功放 PA_CTRL | GPIO49 |
| SDMMC SCK / CMD / D0-D3 | GPIO24 / 25 / 20 / 21 / 22 / 23 |
| 电池 BAT_DAC | GPIO55 |
| 旋钮 KNOB_A / KNOB_B | GPIO3 / GPIO2 |

显示屏分辨率 360x360，16bit，使用 ST77916 驱动（QSPI 接口）。触摸使用 CST816S。

音频使用 ES8389（I2C 地址 0x20，标准 I2S，主机模式）。硬件上 R22 将 I2S_DO 与 MCLK 短接，
因此禁止驱动 MCLK（`AUDIO_I2S_GPIO_MCLK = GPIO_NUM_NC`、`AUDIO_CODEC_USE_MCLK = false`）。

## 编译

```bash
idf.py set-target esp32s31
idf.py menuconfig
# Xiaozhi Assistant -> Board Type -> Guition JC3636F318
idf.py build
```

或使用构建脚本：

```bash
python3 scripts/build.py guition-jc3636f318 --name guition-jc3636f318
```

> 注意：`AUDIO_CODEC_PA_PIN`(GPIO49) 由 ES8389 驱动在开关输出时控制，默认高电平使能功放。
> 若实际硬件为低电平有效，请调整 ES8389 codec 的 pa 电平配置。
