# Remount T: / Z: as NFS hard mounts. Plain `net use` defaults to mtype=soft + timeout=0.8s
# + retry=1, which causes intermittent FFmpeg "Error opening output file: Invalid argument"
# failures when the NFS server is briefly slow.
mount.exe -o mtype=hard -o timeout=30 -o rsize=1024 -o wsize=1024 -o anon \\10.0.0.61\volume2\XXX Z:

mount.exe -o mtype=hard -o timeout=30 -o rsize=1024 -o wsize=1024 -o anon \\10.0.0.43\srv\nfs-media-_tv T:
