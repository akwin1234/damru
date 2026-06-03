# Tools and Assets

This directory is for external helper assets used during Android/Redroid research and debugging.

## `magisk.apk`

Normal users do not need to provide Magisk manually. Damru ships `magisk.apk` as a package asset and copies it into the local APK bundle when raw/unbaked Redroid needs a local source for extracting standalone `resetprop`.

Damru does not download Magisk from third-party APK sites at runtime.

## Policy

Do not commit private keys, proxy credentials, account data, private APK URLs, or large unmodified third-party binaries unless they are explicitly required by the build/release pipeline and allowed by license.
