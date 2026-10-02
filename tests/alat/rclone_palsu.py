#!/usr/bin/env python3
"""rclone tiruan untuk pengujian: remote "nama:" = folder $RCLONE_PALSU/<nama>."""
import fnmatch
import os
import shutil
import sys

AKAR = os.environ["RCLONE_PALSU"]


def lokasi(arg):
    if ":" in arg and not os.path.isabs(arg):
        nama, jalur = arg.split(":", 1)
        return os.path.join(AKAR, nama, jalur)
    return arg


def opsi(args, nama):
    return args[args.index(nama) + 1] if nama in args else None


def main(a):
    perintah = a[0]
    os.makedirs(AKAR, exist_ok=True)
    if os.environ.get("RCLONE_PALSU_GAGAL") == perintah:
        print("gagal tiruan", file=sys.stderr)
        return 1
    if perintah == "listremotes":
        print("\n".join(f"{n}:" for n in sorted(os.listdir(AKAR))))
    elif perintah == "config":
        os.makedirs(os.path.join(AKAR, a[2]), exist_ok=True)
        with open(os.path.join(AKAR, a[2] + ".conf"), "w") as f:
            f.write(" ".join(a))
    elif perintah == "copy":
        src, dst = lokasi(a[1]), lokasi(a[2])
        os.makedirs(dst, exist_ok=True)
        pola = opsi(a, "--include") or "*"
        for f in os.listdir(src):
            if fnmatch.fnmatch(f, pola):
                shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
    elif perintah == "copyto":
        dst = lokasi(a[2])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(lokasi(a[1]), dst)
    elif perintah == "lsf":
        d = lokasi(a[1])
        pola = opsi(a, "--include") or "*"
        if os.path.isdir(d):
            print("\n".join(sorted(f for f in os.listdir(d) if fnmatch.fnmatch(f, pola))))
    elif perintah == "delete":
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
