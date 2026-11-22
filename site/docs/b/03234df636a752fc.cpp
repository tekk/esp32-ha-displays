// ----------------------------------------------------------------------------
// WiFi scan screen for the JC1060F570C (ESP32-S3) with LVGL 8.
// Scans for nearby WiFi networks and shows them as a scrollable list with
// SSID, signal strength (bar), encryption and RSSI.
// ----------------------------------------------------------------------------
#include "wifi_screen.h"
#include <WiFi.h>

// Board resolution (keep in sync with WiFi_scan.ino).
#define SCR_W 1024
#define SCR_H 600

static lv_obj_t *g_list   = NULL;
static lv_obj_t *g_status = NULL;
static bool      g_scanning = false;

// Map an RSSI (dBm) to a 0..100 percentage.
static int rssi_to_pct(int32_t rssi)
{
    if (rssi <= -100) return 0;
    if (rssi >=  -50) return 100;
    return (rssi + 100) * 2;
}

static const char *enc_name(wifi_auth_mode_t m)
{
    switch (m) {
        case WIFI_AUTH_OPEN:        return "Open";
        case WIFI_AUTH_WEP:         return "WEP";
        case WIFI_AUTH_WPA_PSK:     return "WPA";
        case WIFI_AUTH_WPA2_PSK:    return "WPA2";
        case WIFI_AUTH_WPA_WPA2_PSK:return "WPA/WPA2";
        case WIFI_AUTH_WPA3_PSK:    return "WPA3";
        case WIFI_AUTH_WPA2_WPA3_PSK:return "WPA2/WPA3";
        case WIFI_AUTH_WAPI_PSK:    return "WAPI";
        default:                    return "?";
    }
}

static void start_scan(void)
{
    if (g_scanning) return;
    g_scanning = true;
    if (g_status) lv_label_set_text(g_status, "Scanning WiFi networks...");
    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    WiFi.scanNetworks(true);   // async scan
}

static void build_list(int n)
{
    lv_obj_clean(g_list);

    if (g_status) {
        char buf[64];
        snprintf(buf, sizeof(buf), "Found %d WiFi networks", n);
        lv_label_set_text(g_status, buf);
    }

    for (int i = 0; i < n; i++) {
        String           ssid = WiFi.SSID(i);
        int32_t          rssi = WiFi.RSSI(i);
        wifi_auth_mode_t enc  = WiFi.encryptionType(i);
        int              pct  = rssi_to_pct(rssi);

        lv_obj_t *row = lv_obj_create(g_list);
        lv_obj_set_size(row, lv_pct(100), 72);
        lv_obj_clear_flag(row, LV_OBJ_FLAG_SCROLLABLE);   // let the list handle swipe-down
        lv_obj_set_layout(row, LV_LAYOUT_FLEX);
        lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
        lv_obj_set_flex_align(row, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
        lv_obj_set_style_pad_all(row, 10, 0);
        lv_obj_set_style_radius(row, 8, 0);

        // SSID (or placeholder for hidden networks).
        lv_obj_t *name = lv_label_create(row);
        lv_label_set_text(name, ssid.length() ? ssid.c_str() : "<Hidden network>");
        lv_obj_set_flex_grow(name, 1);
        lv_label_set_long_mode(name, LV_LABEL_LONG_DOT);

        // Signal strength bar.
        lv_obj_t *bar = lv_bar_create(row);
        lv_obj_set_size(bar, 130, 14);
        lv_bar_set_range(bar, 0, 100);
        lv_bar_set_value(bar, pct, LV_ANIM_OFF);
        lv_color_t col = pct > 60 ? lv_color_make(0x2E, 0xCC, 0x40)
                        : pct > 30 ? lv_color_make(0xF1, 0xC4, 0x0F)
                                   : lv_color_make(0xE7, 0x4C, 0x3C);
        lv_obj_set_style_bg_color(bar, col, LV_PART_INDICATOR);

        // RSSI text.
        lv_obj_t *rssi_lbl = lv_label_create(row);
        char rb[32];
        snprintf(rb, sizeof(rb), "%ld dBm", (long)rssi);
        lv_label_set_text(rssi_lbl, rb);
        lv_obj_set_width(rssi_lbl, 90);

        // Encryption name (small).
        lv_obj_t *enc_lbl = lv_label_create(row);
        lv_label_set_text(enc_lbl, enc_name(enc));
        lv_obj_set_width(enc_lbl, 90);
    }

    WiFi.scanDelete();
}

// Polls the async scan result; called by an LVGL timer.
static void scan_poll_cb(lv_timer_t *)
{
    if (!g_scanning) return;
    int16_t res = WiFi.scanComplete();
    if (res == -1) {
        // still scanning
    } else if (res == -2) {
        if (g_status) lv_label_set_text(g_status, "Scan failed, please retry");
        g_scanning = false;
    } else {
        build_list(res);
        g_scanning = false;
    }
}

// Periodic auto-refresh (every 15 s) when idle.
static void auto_refresh_cb(lv_timer_t *)
{
    start_scan();
}

void wifi_screen_init(void)
{
    lv_obj_t *scr = lv_obj_create(NULL);
    lv_obj_set_size(scr, SCR_W, SCR_H);

    // ---------- Header ----------
    lv_obj_t *header = lv_obj_create(scr);
    lv_obj_set_size(header, SCR_W, 70);
    lv_obj_align(header, LV_ALIGN_TOP_MID, 0, 0);
    lv_obj_set_flex_flow(header, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(header, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_hor(header, 16, 0);
    lv_obj_set_style_border_width(header, 0, 0);

    lv_obj_t *title = lv_label_create(header);
    lv_label_set_text(title, "WiFi Scan");

    lv_obj_t *refresh = lv_btn_create(header);
    lv_obj_t *rl = lv_label_create(refresh);
    lv_label_set_text(rl, LV_SYMBOL_REFRESH " Refresh");
    lv_obj_add_event_cb(refresh, [](lv_event_t *) { start_scan(); }, LV_EVENT_CLICKED, NULL);

    // ---------- Status ----------
    g_status = lv_label_create(scr);
    lv_obj_align(g_status, LV_ALIGN_TOP_MID, 0, 84);
    lv_label_set_text(g_status, "Preparing to scan...");

    // ---------- List ----------
    g_list = lv_obj_create(scr);
    lv_obj_set_size(g_list, SCR_W, SCR_H - 70 - 110);
    lv_obj_align(g_list, LV_ALIGN_TOP_MID, 0, 120);
    lv_obj_set_flex_flow(g_list, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_all(g_list, 8, 0);
    lv_obj_set_style_pad_row(g_list, 8, 0);
    lv_obj_set_scroll_dir(g_list, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(g_list, LV_SCROLLBAR_MODE_AUTO);

    lv_scr_load(scr);

    lv_timer_create(scan_poll_cb, 200, NULL);
    lv_timer_create(auto_refresh_cb, 15000, NULL);
    start_scan();
}
