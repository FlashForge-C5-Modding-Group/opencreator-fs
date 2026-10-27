# USB Ethernet

The Creator 5 has Wi-Fi only, and FlashForge's kernels (2.0.7 and 2.0.8)
have no USB network drivers. LoopScript's `07-usb-ethernet.sh` loads them at
boot, so a USB Ethernet adapter (or Android USB tethering) works like a wired
port.

## Modules

`startup/usb-ethernet/` holds the modules, built by the
`c5-usb-serial-modules` project from Ingenic's X2600 kernel source with the stock vermagic, and checked
against both stock kernels' export tables:

| Module | Adapters |
|---|---|
| `r8152.ko` | Realtek RTL8152/8153/8156 (most USB Ethernet adapters) |
| `asix.ko` | ASIX AX88772 and similar (100 Mbit) |
| `ax88179_178a.ko` | ASIX AX88179/178A (gigabit) |
| `cdc_ether.ko`, `cdc_ncm.ko` | adapters using the standard CDC ECM / NCM class |
| `rndis_host.ko` | Android USB tethering |
| `usbnet.ko`, `mii.ko` | needed by the others |

They load only on kernel 5.10.186+ with FlashForge kernel package 2.0.7 or
2.0.8 (the kernels they were checked against), and only if they match
`SHA256SUMS`. `LOAD_ORDER` lists them dependencies first; modules that are
already loaded are skipped.

## Address and routing

A background loop checks every 10 s for an adapter (`eth*`, `enx*`, `usb*`),
brings it up and starts `udhcpc` on it, as the stock startup does for
`wlan0`.

While an adapter has a link and an address, Wi-Fi's routes are moved to
metric 100, so traffic goes over the cable (the stock DHCP script gives every
interface's routes metric 0, and Wi-Fi's would win). The loop re-applies
this, since Wi-Fi's lease renewals put metric 0 back.
`ignore_routes_with_linkdown` is set, so pulling the cable falls back to
Wi-Fi at once. Wi-Fi stays connected either way.

Log: `/usr/data/logs/usb-ethernet.log`. `lsmod` lists the modules, and
`ip addr` / `ip route` show the adapter and the routes.
