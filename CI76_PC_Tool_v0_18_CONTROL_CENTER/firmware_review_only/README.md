# FOR REVIEW ONLY — DO NOT FLASH AS PRODUCTION FIRMWARE

`ctl.c` and `ctl_learn_guard_review.patch` are minimal candidate learning guards
based on `2026110405 LAC2_TEST.zip`, NOT the user's newer unprovided firmware.

They are deliberately separated from the Windows PC Tool and have NOT been
compiled with MDK-ARM or validated on a real actuator. Review each hunk,
calibrate thresholds for the actual Hall/POT units, add sensor plausibility
and timeout protections, and follow `../LEARNING_REPAIR_GUIDE.md`.

The UART PC Tool requires **no** firmware patch for its v0.16 dark UI changes.
