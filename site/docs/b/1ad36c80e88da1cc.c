/** SPDX-License-Identifier: GPL-2.0-only */
#include "ft_sd_probe.h"

#include <string.h>

void ft_sd_probe_run(const ft_sd_probe_ops_t *ops, ft_sd_probe_report_t *report)
{
    if (ops == NULL || report == NULL) {
        return;
    }

    memset(report, 0, sizeof(*report));
    report->status = FT_SD_STATUS_UNAVAILABLE;

    if (ops->query_mounted == NULL || ops->mount == NULL || ops->verify == NULL) {
        return;
    }

    bool mounted = false;
    int ret = ops->query_mounted(ops->context, &mounted);
    if (ret != 0) {
        report->last_error = ret;
        return;
    }
    report->mounted_before = mounted;

    if (!mounted) {
        ret = ops->mount(ops->context);
        if (ret != 0) {
            report->last_error = ret;
            report->status = FT_SD_STATUS_MOUNT_FAILED;
            return;
        }
        report->mounted_by_probe = true;
    }

    /** A boot-time handle stays registered even after the card is pulled out, so ask the card itself
     *  instead of treating "already mounted" as a pass. */
    ret = ops->verify(ops->context);
    if (ret != 0) {
        report->last_error = ret;
        report->status = FT_SD_STATUS_COMM_FAILED;
        return;
    }

    report->last_error = 0;
    report->status = FT_SD_STATUS_OK;
}

void ft_sd_probe_release(const ft_sd_probe_ops_t *ops, ft_sd_probe_report_t *report)
{
    if (ops == NULL || report == NULL || !report->mounted_by_probe) {
        return;
    }
    /** Resolve ownership once, so repeated calls cannot unmount twice. */
    report->mounted_by_probe = false;

    /** /sdcard is a system-wide mount shared by the music, photo and web apps. Keep a healthy
     *  mount created here, and only roll back one that failed the communication check. */
    if (report->status == FT_SD_STATUS_OK) {
        return;
    }
    if (ops->unmount != NULL) {
        (void)ops->unmount(ops->context);
    }
}

#ifndef FT_SD_PROBE_HOST_TEST

#include "esp_board_device.h"
#include "esp_board_manager.h"
#include "esp_err.h"
#include "dev_fs_fat.h"
#include "sdmmc_cmd.h"

/** @brief Device name declared by components/gen_bmgr_codes and board_devices.yaml. */
#define FT_SD_DEVICE_NAME "fs_sdcard"

static int sd_probe_query_mounted(void *context, bool *mounted)
{
    (void)context;
    if (mounted == NULL) {
        return (int)ESP_ERR_INVALID_ARG;
    }

    /** A handle only tells us the device was initialized; sd_probe_verify() checks the card itself. */
    void *handle = NULL;
    *mounted = esp_board_manager_get_device_handle(FT_SD_DEVICE_NAME, &handle) == ESP_OK &&
               handle != NULL;
    return 0;
}

static int sd_probe_mount(void *context)
{
    (void)context;
    return (int)esp_board_device_init(FT_SD_DEVICE_NAME);
}

static int sd_probe_unmount(void *context)
{
    (void)context;
    return (int)esp_board_device_deinit(FT_SD_DEVICE_NAME);
}

/**
 * @brief Talk to the card itself instead of trusting the board-manager handle.
 *
 * CMD13 needs a live response from the card and does not touch the filesystem, which makes
 * it safe while other tasks are using /sdcard. The card pointer is the first member of the
 * dev_fs_fat handle published by esp_board_manager_get_device_handle("fs_sdcard").
 */
static int sd_probe_verify(void *context)
{
    (void)context;
    void *handle = NULL;
    esp_err_t ret = esp_board_manager_get_device_handle(FT_SD_DEVICE_NAME, &handle);
    if (ret != ESP_OK) {
        return (int)ret;
    }
    if (handle == NULL) {
        return (int)ESP_ERR_NOT_FOUND;
    }

    const dev_fs_fat_handle_t *fat = (const dev_fs_fat_handle_t *)handle;
    if (fat->card == NULL) {
        return (int)ESP_ERR_INVALID_STATE;
    }
    return (int)sdmmc_get_status(fat->card);
}

const ft_sd_probe_ops_t *ft_sd_probe_default_ops(void)
{
    static const ft_sd_probe_ops_t s_ops = {
        .context = NULL,
        .query_mounted = sd_probe_query_mounted,
        .mount = sd_probe_mount,
        .verify = sd_probe_verify,
        .unmount = sd_probe_unmount,
    };
    return &s_ops;
}

#endif
