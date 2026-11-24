#!/bin/bash
# E6 on a real disk: a shared Linux host (OpenStack VM, virtio disk on network block
# storage), started from Windows with
#   ssh ubuntu@HOST 'sudo bash ~/fpstudy-e6/code/study/bin/remote_batch_e6.sh'
# after the code was copied to ~/fpstudy-e6/code. Everything lives under /root/fpstudy.
#   - The host had no psutil, which the fork's parallel code imports unconditionally;
#     with the owner's permission python3-psutil was installed with apt for this run and
#     is purged afterwards (with /root/fpstudy and ~/fpstudy-e6).
#   - The host serves other programs, so there is no global drop_caches
#     (FPSTUDY_GENTLE_DROP=1, see fsimg.drop_caches), and every step runs alone.
# The disk serves about 8 random 4 KiB reads per second one at a time (E12 smoke run),
# so the configurations are smaller than on WSL. Output files are named e6_*.
set -u
export FPSTUDY_CODE=/root/fpstudy/code FPSTUDY_DATA=/root/fpstudy/data
export FPSTUDY_IMG=/root/fpstudy/img FPSTUDY_WORK=/root/fpstudy/work FPSTUDY_GENTLE_DROP=1
# file creation (fsync after every block for fragmented files) takes minutes per hundred
# files when every fsync waits for this disk's flush; create without barriers, measure
# with the default mount (see fsimg.TestFS)
export FPSTUDY_CREATE_MOUNT_OPTS=barrier=0
mkdir -p /root/fpstudy/data /root/fpstudy/img /root/fpstudy/work
rm -rf /root/fpstudy/code && cp -r /home/ubuntu/fpstudy-e6/code /root/fpstudy/code
chmod +x /root/fpstudy/code/*/src/analysis/*.sh /root/fpstudy/code/study/bin/*.sh 2>/dev/null
log=/root/fpstudy/e6.log
NS=/root/fpstudy/code/study/bin/run_in_ns.sh
X=/root/fpstudy/code/study/experiments
echo "e6 start $(date -u +%FT%TZ) $(uname -r) $(python3 --version) psutil $(python3 -c 'import psutil; print(psutil.__version__)')" >> $log
step() { echo "=== $(date -u +%FT%TZ) $*" >> $log; (cd /root/fpstudy && bash $NS python3 $X/"$@") >> $log 2>&1; echo "=== rc=$? $(date -u +%FT%TZ)" >> $log; }
step e12_device.py --reads 600 --out e6_device.jsonl
step e8_gil.py --devices plain --variants fork,big,small,big_mp --reps 3 --out e6_gil.jsonl
step e2_ladder.py --T 10000 --F 1000 --cache cold --rungs a,c,d1,d8,e8,m8 --reps 3 --budget-s 600 --out e6_ladder.jsonl
step e5_latency.py --models plain --workers 0,16 --reps 3 --out e6_latency.jsonl
step e10_walk.py --models plain --walkers find,scandir/1,scandir/16 --reps 3 --out e6_walk.jsonl
step e9_calls.py --fs ext4 --classes 1:200,32:200 --reps 3 --out e6_calls.jsonl
step e12_device.py --reads 600 --out e6_device_after.jsonl
echo "e6 end $(date -u +%FT%TZ)" >> $log
