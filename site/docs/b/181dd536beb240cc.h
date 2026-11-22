#ifndef __PINCONFIG_H
#define __PINCONFIG_H

#include "driver/gpio.h"

#define PIN_SDMMC_SCK           GPIO_NUM_24
#define PIN_SDMMC_CMD           GPIO_NUM_25
#define PIN_SDMMC_D0            GPIO_NUM_20
#define PIN_SDMMC_D1            GPIO_NUM_21
#define PIN_SDMMC_D2            GPIO_NUM_22
#define PIN_SDMMC_D3            GPIO_NUM_23


#define TOUCH_HOST              I2C_NUM_0
#define PIN_TP_SDA              GPIO_NUM_11
#define PIN_TP_SCL              GPIO_NUM_10
#define PIN_TP_INT              GPIO_NUM_8
#define PIN_TP_RST              GPIO_NUM_9

#define LCD_H_RES               360
#define LCD_V_RES               360
#define LCD_BIT_PER_PIXEL       16
#define LCD_HOST                SPI2_HOST

#define PIN_LCD_SCL             GPIO_NUM_12
#define PIN_LCD_CS              GPIO_NUM_13
#define PIN_LCD_D0              GPIO_NUM_14
#define PIN_LCD_D1              GPIO_NUM_15
#define PIN_LCD_D2              GPIO_NUM_16
#define PIN_LCD_D3              GPIO_NUM_17
#define PIN_LCD_RST             GPIO_NUM_18
#define PIN_LCD_TE              GPIO_NUM_19
#define PIN_LCD_BLK             GPIO_NUM_5


#define PIN_PA_CTRL             GPIO_NUM_50
#define PIN_I2S_BCK             GPIO_NUM_53
#define PIN_I2S_WS              GPIO_NUM_51
#define PIN_I2S_DO              GPIO_NUM_52

#define PIN_MIC_SCK             GPIO_NUM_39
#define PIN_MIC_DATA            GPIO_NUM_37

#define PIN_BAT_DAC             GPIO_NUM_55


#define GPIO_KNOB_A             GPIO_NUM_6
#define GPIO_KNOB_B             GPIO_NUM_7



#endif
