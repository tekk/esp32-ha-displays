/** SPDX-License-Identifier: GPL-2.0-only */
/** SD card mount and communication test. A healthy mount created by the probe stays mounted for the rest of the system;
 *  only a mount that fails the communication check is rolled back by ft_sd_probe_release(). */
#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** @brief SD mount and communication probe result. */
typedef enum {
    FT_SD_STATUS_OK = 0,
    FT_SD_STATUS_UNAVAILABLE,   /**< No fs_sdcard device, or an incomplete probe ops table. */
    FT_SD_STATUS_MOUNT_FAILED,  /**< No card inserted, or the mount was rejected. */
    FT_SD_STATUS_COMM_FAILED,   /**< Mounted, but the card did not answer the communication check. */
} ft_sd_probe_status_t;

/** @brief SD probe outcome and mount ownership. */
typedef struct {
    ft_sd_probe_status_t status;
    bool mounted_before;    /**< Already mounted when the test started. */
    bool mounted_by_probe;  /**< This probe performed the mount (ownership is resolved by ft_sd_probe_release()). */
    uint64_t capacity_bytes;
    char card_name[16];
    int last_error;         /**< Raw driver/board error of the failing step. */
} ft_sd_probe_report_t;

/** @brief Board operations and context used throughout an SD probe. */
typedef struct {
    void *context;
    /** true when esp_board_manager holds an initialized fs_sdcard handle; not proof the card is present. */
    int (*query_mounted)(void *context, bool *mounted);
    /** esp_board_device_init("fs_sdcard"). */
    int (*mount)(void *context);
    /** Real communication check on the current mount; 0 when the card answers. */
    int (*verify)(void *context);
    /** esp_board_device_deinit("fs_sdcard"), used only to roll back a failed probe mount. */
    int (*unmount)(void *context);
} ft_sd_probe_ops_t;

/**
 * @brief Run the chain and fill `report`. The ops table must stay valid until ft_sd_probe_release() has been called.
 * @param ops Operations to use.
 * @param report Report data.
 */
void ft_sd_probe_run(const ft_sd_probe_ops_t *ops, ft_sd_probe_report_t *report);

/**
 * @brief Resolve the mount created by this probe. A healthy mount stays mounted because other apps share
 *        /sdcard; only a mount that failed the communication check is rolled back. Repeated calls are safe.
 * @param ops Operations to use.
 * @param report Report data.
 */
void ft_sd_probe_release(const ft_sd_probe_ops_t *ops, ft_sd_probe_report_t *report);

/**
 * @brief Return the board-manager-backed SD operations table.
 * @return Board-manager-backed SD operations table.
 */
const ft_sd_probe_ops_t *ft_sd_probe_default_ops(void);

#ifdef __cplusplus
}
#endif
