/*
 * Minimal, self-contained ES8389 codec driver for Arduino / ESP32.
 *
 * Ported from the Espressif ES8389 reference driver used by the
 * JC1060F570 factory demo (components/audio_runtime/.../es8389.c).
 *
 * It does NOT depend on esp_codec_dev / ESP-IDF audio framework: it talks to
 * the codec purely over the Arduino Wire (I2C) bus and exposes just what the
 * MP3 player needs (init, volume, sample-rate reconfiguration).
 *
 * Default configuration matches the JC1060F570 board:
 *   - codec is I2S SLAVE (ESP32 generates BCLK/WS)
 *   - no MCLK pin (codec clocked from BCLK)
 *   - internal DAC reference enabled
 */

#ifndef _ES8389_H_
#define _ES8389_H_

#include <Arduino.h>
#include <Wire.h>
#include "es8389_reg.h"

class ES8389 {
public:
    ES8389();

    /* Initialize I2C, open and power-up the codec.
     * addr is the 7-bit I2C address (default 0x10 for ES8389). */
    bool begin(uint8_t addr = 0x10, int sda = 2, int scl = 3);

    /* Set DAC output volume: 0x00 (mute) .. 0xFF (max). Writes regs 0x46/0x47. */
    void setVolume(uint8_t vol);

    /* Reconfigure the codec clocking/format for a new sample rate.
     * Call this whenever the decoded audio sample rate changes. */
    bool configure(uint32_t sampleRate, uint8_t bits = 16);

    /* Mute (true) / unmute (false) the DAC path. */
    void mute(bool m);

    /* Power up (true) / down (false) the analog bias of the codec. */
    void enable(bool on);

    uint8_t readReg(uint8_t reg);

private:
    TwoWire *_wire;
    uint8_t  _addr;
    bool     _open;
    bool     _useMclk;   // false: codec is clocked from BCLK (no MCLK pin)
    bool     _noDacRef;  // false: use internal reference signal

    void writeReg(uint8_t reg, uint8_t val);
    void updateBits(uint8_t reg, uint8_t mask, uint8_t val);
    bool probeAddr(uint8_t a);   // true if device ACKs its address

    void openCodec();
    void startBias();
    void configFmt();
    void setBitsPerSample(uint8_t bits);
    void configSample(uint32_t sr, uint8_t bits);
    int  findCoeff(uint32_t mclk, uint32_t rate);
};

#endif // _ES8389_H_
