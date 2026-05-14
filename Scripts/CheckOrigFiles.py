import os

Origs = []
for Root, Dirs, Files in os.walk("/mnt/media_tv"):
    for F in Files:
        if F.endswith(".orig"):
            Origs.append(os.path.join(Root, F))

Both = []
OrigOnly = []
for O in Origs:
    Base = O[:-5]  # strip .orig
    if os.path.isfile(Base):
        Both.append(O)
    else:
        OrigOnly.append(O)

print(f"BOTH={len(Both)} ORIG_ONLY={len(OrigOnly)} TOTAL={len(Origs)}")
print()
if OrigOnly:
    print("=== ORIG_ONLY (media file missing, .orig is only copy) ===")
    for P in sorted(OrigOnly):
        print(P)
