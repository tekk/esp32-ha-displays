/*
 * MP3 player for ESP32-S3 (JC1060F570) driving the ES8389 codec directly.
 *
 * Design (no ESP32-audioI2S / "Audio.h" dependency):
 *   - ES8389 is controlled over I2C by a self-contained driver (es8389/ES8389.*).
 *   - PCM is pushed to the codec through the native ESP32 I2S peripheral.
 *   - MP3 decoding is done by the lightweight "codec-helix" (libhelix) library.
 *
 * Install the library "codec-helix" by Phil Schatzmann from the Arduino
 * Library Manager (it is standalone and only needs Arduino's Print class).
 *
 * Pin / clock configuration is taken from the JC1060F570 factory demo:
 *   I2S master, codec I2S slave, no MCLK pin, internal DAC reference.
 *
 * Serial monitor commands while playing:
 *   n  -> next track      p  -> previous track
 *   +  -> volume up       -  -> volume down
 *
 * Note on sample rates: the ES8389 clock table covers the common rates
 * (8k/16k/44.1k/48k). Tracks at other rates (e.g. 32k/22k/24k) will play but
 * the codec clock may not be retuned for them; re-encode such files to
 * 44.1k/48k if you hear distortion.
 */

#include "Wire.h"
#include "SD_MMC.h"
#include "FS.h"

// Arduino-ESP32 3.x: I2S is provided by the bundled "ESP_I2S" library.
#include "ESP_I2S.h"

#include "MP3DecoderHelix.h"//https://github.com/pschatzmann/codec-helix
#include "ES8389.h"

using namespace libhelix;

// ---------------------------- Board pins (JC1060F570) ----------------------------
#define SD_CLK   24
#define SD_CMD   25
#define SD_D0    20
#define SD_D1    21
#define SD_D2    22
#define SD_D3    23

#define I2S_BCK  54
#define I2S_WS   47
#define I2S_DOUT 56
// I2S_DIN (GPIO 16) is unused for playback

#define I2C_SDA  2
#define I2C_SCL  3
#define ES8389_ADDR 0x10

#define PA_ENABLE 42   // active HIGH on this board

// ------------------------------- Globals ----------------------------------------
ES8389 codec;
MP3DecoderHelix mp3;
I2SClass I2S;          // ESP_I2S instance (Arduino-ESP32 3.x has no global I2S)

bool i2sStarted = false;
uint32_t curRate = 0;

#define MP3_BUF_SIZE 2048
static uint8_t  mp3buf[MP3_BUF_SIZE];
static int16_t  outBuf[1152 * 2];   // worst case: mono -> stereo expansion

#define MAX_FILES 20
static char fileList[MAX_FILES][256];
static int  fileCnt = 0;
static int  curFile = 0;
static File mp3File;
static bool playing = false;
static uint8_t g_volume = 0xA0;

// ------------------------------- I2S ---------------------------------------------
static void i2s_setup(uint32_t rate) {
    if (i2sStarted) {
        I2S.end();
        i2sStarted = false;
    }
    // TX only: BCLK, WS(out), DOUT. No MCLK, no DIN.
    I2S.setPins(I2S_BCK, I2S_WS, I2S_DOUT, -1);
    if (!I2S.begin(I2S_MODE_STD, rate, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO)) {
        Serial.printf("I2S begin failed @ %u Hz\r\n", rate);
        return;
    }
    i2sStarted = true;
    curRate = rate;
    Serial.printf("I2S configured @ %u Hz\r\n", rate);
}

// Expand mono -> stereo and write to I2S (blocking, back-pressured by DMA).
static void i2s_write_samples(int16_t *pcm, size_t len, uint8_t channels) {
    int16_t *out;
    size_t   outSamples;
    if (channels == 1) {
        outSamples = len * 2;
        for (size_t i = 0; i < len; i++) {
            outBuf[i * 2]     = pcm[i];
            outBuf[i * 2 + 1] = pcm[i];
        }
        out = outBuf;
    } else {
        outSamples = len;
        out = pcm;
    }
    size_t total = outSamples * sizeof(int16_t);
    size_t done = 0;
    const uint8_t *p = (const uint8_t *)out;
    while (done < total) {
        done += I2S.write(p + done, total - done);
    }
}

// -------------------------- MP3 decoder callback ---------------------------------
static void mp3_data_callback(MP3FrameInfo &info, int16_t *pcm, size_t len, void *ref) {
    if (info.samprate != (int)curRate) {
        // Retune codec + I2S for the actual decoded sample rate.
        codec.configure((uint32_t)info.samprate, 16);
        i2s_setup((uint32_t)info.samprate);
    }
    uint8_t ch = (info.nChans > 0) ? (uint8_t)info.nChans : 2;
    i2s_write_samples(pcm, len, ch);
}

// ------------------------------ File helpers -------------------------------------
static void listDir(fs::FS &fs, const char *dirname) {
    File root = fs.open(dirname);
    if (!root || !root.isDirectory()) {
        Serial.println("Failed to open /music");
        return;
    }
    File f = root.openNextFile();
    while (f && fileCnt < MAX_FILES) {
        if (!f.isDirectory()) {
            snprintf(fileList[fileCnt], 256, "/music/%s", f.name());
            Serial.printf("  %s\r\n", fileList[fileCnt]);
            fileCnt++;
        }
        f = root.openNextFile();
    }
}

static void startFile(int idx) {
    if (idx >= fileCnt) return;
    if (mp3File) mp3File.close();

    mp3File = SD_MMC.open(fileList[idx]);
    if (!mp3File) {
        Serial.printf("Cannot open %s\r\n", fileList[idx]);
        return;
    }
    // Reset the decoder state for a fresh MP3 stream.
    mp3.end();
    mp3.begin();
    mp3.setDataCallback(mp3_data_callback);
    playing = true;
    Serial.printf("Playing: %s\r\n", fileList[idx]);
}

static void nextFile() {
    curFile = (curFile + 1) % fileCnt;
    startFile(curFile);
}

static void prevFile() {
    curFile = (curFile - 1 + fileCnt) % fileCnt;
    startFile(curFile);
}

// ------------------------------ Setup / Loop ------------------------------------
void setup() {
    Serial.begin(115200);
    Serial.println("ES8389 MP3 player (no Audio library)");

    // SD card (4-bit SDMMC, as wired on the board)
    if (!SD_MMC.setPins(SD_CLK, SD_CMD, SD_D0, SD_D1, SD_D2, SD_D3)) {
        Serial.println("SD pin change failed!");
        return;
    }
    if (!SD_MMC.begin()) {
        Serial.println("Card Mount Failed");
        return;
    }
    listDir(SD_MMC, "/music");
    if (fileCnt == 0) {
        Serial.println("No files found in /music");
        return;
    }

    // ES8389 codec over I2C
    if (!codec.begin(ES8389_ADDR, I2C_SDA, I2C_SCL)) {
        Serial.println("ES8389 init failed");
        return;
    }
    codec.setVolume(g_volume);

    // Amplifier enable
    pinMode(PA_ENABLE, OUTPUT);
    digitalWrite(PA_ENABLE, HIGH);

    // MP3 decoder
    mp3.begin();
    mp3.setDataCallback(mp3_data_callback);

    // Start first track (I2S is set up lazily on the first decoded frame)
    startFile(curFile);
}

void loop() {
    // Serial control
    if (Serial.available()) {
        char c = Serial.read();
        if (c == 'n') nextFile();
        else if (c == 'p') prevFile();
        else if (c == '+') { g_volume = min(255, (int)g_volume + 16); codec.setVolume(g_volume); }
        else if (c == '-') { g_volume = max(0, (int)g_volume - 16); codec.setVolume(g_volume); }
    }

    if (!playing) return;

    if (!mp3File || !mp3File.available()) {
        mp3File.close();
        playing = false;
        nextFile();
        return;
    }

    int toRead = min((int)sizeof(mp3buf), (int)mp3File.available());
    int n = mp3File.read(mp3buf, toRead);
    if (n > 0) {
        mp3.write(mp3buf, n);
    }
    delay(1);  // yield so the watchdog / other tasks can run
}
