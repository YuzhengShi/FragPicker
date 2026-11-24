# E6: the same measurements on a real slow device

E2 (cold), E4 and E5 (model `plain`, i.e. no injected delay) run unchanged on a real
block device when `FPSTUDY_DEVICE` is set. **`mkfs` destroys everything on that device.**

## Option 1: a Linux machine with a spare disk (USB HDD, SD card, second SATA disk)

```bash
sudo apt install bpfcc-tools xfsprogs btrfs-progs f2fs-tools fio sqlite3 nbdkit nbd-client \
     strace python3-numpy python3-matplotlib python3-yaml python3-psutil git
# copy D:\fragpicker-study (upstream/ and fork/ with the storage-study branch) to the machine,
# e.g. to ~/fragpicker-study, then:
export FPSTUDY_DEVICE=/dev/sdX            # the spare disk, NOT the system disk
export FPSTUDY_DEVICE_CONFIRM=wipe-sdX    # must name the same device
sudo -E bash ~/fragpicker-study/fork/study/bin/run_e6.sh ~/fragpicker-study
```

## Option 2: a USB disk on this Windows machine, passed into WSL2

The WSL2 kernel has `usb-storage`, `uas` and `usbip` modules. With
[usbipd-win](https://github.com/dorssel/usbipd-win) (admin PowerShell):

```powershell
usbipd list
usbipd bind --busid <BUSID>
usbipd attach --wsl --busid <BUSID>
```

The disk then appears in WSL as `/dev/sdX`; continue as in option 1. Alternatively
`wsl --mount \\.\PHYSICALDRIVEn --bare` attaches a whole disk (not for USB flash
drives or SD card readers, per Microsoft's documentation).

## Option 3: AWS (needs the owner's account and OK; estimate $10-15)

- `h1.2xlarge` (1 x 2 TB local HDD, about $0.47/h) or `d3.xlarge` (3 x 2 TB local HDD,
  about $0.50/h), Ubuntu 24.04, us-east-1. Check prices on the AWS pricing page first.
- The local HDDs are instance store: they are wiped when the instance stops.
- Optionally an EBS `st1` or `sc1` volume (125 GiB minimum, about $0.045 and $0.015 per
  GB-month): network block storage on HDDs, a different device class from a local disk.
- Terminate the instance and delete the volumes as soon as the run ends.

## What run_e6.sh runs

1. E4 on ext4 and xfs: extent-lookup cost and device reads, warm and cold, 1-16 threads.
2. E5 with model `plain`: the fork's engine against the sequential loop, cold and warm,
   layouts `together` and `scattered`.
3. E2 cold: rungs a, c, d1, d8, d16 for T = 10,000 and F = 100, 1,000.
Results go to `study/data/e6_*.jsonl`; `analysis/report.py` picks them up.
