# USB Ethernet and USB serial

The Creator 5 has Wi-Fi only, and FlashForge's kernels (2.0.7 and 2.0.8)
have no USB network drivers. Kernel 2.0.8 (firmware 2.0.0) also leaves out
usb-serial and `cdc_acm`. LoopScript's `07-usb.sh` loads what the running
kernel lacks at boot, so a USB Ethernet adapter (or Android USB tethering)
works like a wired port and USB serial adapters show up as `/dev/ttyUSB*` /
`/dev/ttyACM*`. Tunneled printers run it too (`tunneled.sh`).

## Modules

`startup/usb-modules/` holds the modules, built by the
`c5-usb-serial-modules` project from Ingenic's X2600 kernel source with the stock vermagic, and checked
against both stock kernels' export tables:

| Module | For |
|---|---|
| `r8152.ko` | Realtek RTL8152/8153/8156 (most USB Ethernet adapters) |
| `asix.ko` | ASIX AX88772 and similar (100 Mbit) |
| `ax88179_178a.ko` | ASIX AX88179/178A (gigabit) |
| `cdc_ether.ko`, `cdc_ncm.ko` | adapters using the standard CDC ECM / NCM class |
| `rndis_host.ko` | Android USB tethering |
| `usbnet.ko`, `mii.ko` | needed by the Ethernet ones |
| `usbserial.ko`, `usb-serial-simple.ko` | usb-serial core, generic and one-port drivers (the tunnel's gadget) |
| `ch341.ko`, `cdc-acm.ko` | CH340/CH341 adapters, CDC ACM devices |

Which load, on FlashForge's kernels:

- **Serial**: on kernel packages 2.0.0 to 2.0.6 and 2.0.8. Kernel 2.0.7
  builds usb-serial in, so it's skipped there.
- **Ethernet**: always; no FlashForge kernel has the drivers.

Custom kernels (OpenCreator's c5-kernel, recognised by `/proc/config.gz`,
which FlashForge's kernels don't have) build both in and load no modules.

Modules load only if they match `SHA256SUMS`. They were built and checked
against kernel packages 2.0.7 and 2.0.8; on another kernel, `insmod` refuses
any that don't match it, and the log says so. `LOAD_ORDER` lists them
dependencies first; modules that are already loaded are skipped.

## Address and routing

On every kernel, a background loop checks every 10 s for an adapter (`eth*`,
`enx*`, `usb*`), brings it up and starts `udhcpc` on it, as the stock startup
does for `wlan0`.

While an adapter has a link and an address, Wi-Fi's routes are moved to
metric 100, so traffic goes over the cable (the stock DHCP script gives every
interface's routes metric 0, and Wi-Fi's would win). The loop re-applies
this, since Wi-Fi's lease renewals put metric 0 back.
`ignore_routes_with_linkdown` is set, so pulling the cable falls back to
Wi-Fi at once. Wi-Fi stays connected either way.

Log: `/usr/data/logs/usb.log` (which modules loaded, or whether the drivers
are built in). `lsmod` lists the modules, and `ip addr` / `ip route` show the
adapter and the routes.
