"""Nach-Build-Pruefung fuer Callers Caddy — neuer Release gegen Vorgaenger.

Aufruf (nach build.py, auf main):
    python check_release.py <alt> <neu>        z. B.  python check_release.py 2.0.15 2.0.16

Release-Ordner wie in build.py: Umgebungsvariable CC_RELEASE_DIR,
Fallback <Ordner ueber dem Repo>/4_Release.

Prueft:
  1. ZIP-Groessen gegen die Vorversion (Alarm ab 3 MB bzw. 3 % Abweichung)
  2. Datei-Differenz im Update-ZIP (neu/weg)
  3. Keine Nutzerdaten im Update-ZIP (DB, INI, music, lyrics, playlists, notes, Logs)
  4. Skins in Voll- und Update-ZIP == src/skins auf main (Git)
  5. __version__ im Code-ZIP == <neu>
  6. LICENSE und licenses/THIRD_PARTY.txt in Voll- und Update-ZIP, keine
     ASIO-DLL von PortAudio (intern#248)
Exit-Code 0 = OK, 1 = bitte pruefen.
"""
import os
import subprocess
import sys
import zipfile
from pathlib import Path

INSTALLER_DIR = Path(__file__).parent
REPO_DIR = INSTALLER_DIR.parent
RELEASES_DIR = (Path(os.environ["CC_RELEASE_DIR"]) if os.environ.get("CC_RELEASE_DIR")
                else REPO_DIR.parent / "4_Release")

FORBIDDEN = ("callers_caddy.db", "callers_caddy.ini", "/music/", "/lyrics/",
             "/playlists/", "/notes/", "/logs/", "/crash", "perf_logs")

ok = True


def bad(msg):
    global ok
    ok = False
    print("  !! " + msg)


def zips(v):
    return {"Voll": RELEASES_DIR / v / f"Callers_Caddy_{v}.zip",
            "Update": RELEASES_DIR / v / f"Callers_Caddy_Update_{v}.zip",
            "Code": RELEASES_DIR / v / f"Callers_Caddy_Code_{v}.zip"}


def git(*args):
    return subprocess.run(["git", "-C", str(REPO_DIR), *args], capture_output=True)


def check_sizes(old, new):
    print(f"== 1. Groessen {old} -> {new}")
    for k, p in zips(new).items():
        q = zips(old)[k]
        if not p.exists() or not q.exists():
            bad(f"{p.name if not p.exists() else q.name} fehlt")
            continue
        a, b = q.stat().st_size / 2**20, p.stat().st_size / 2**20
        d = b - a
        flag = "  <-- auffaellig" if abs(d) > max(3.0, a * 0.03) else ""
        print(f"  {k:7} {a:8.1f} MB -> {b:8.1f} MB  ({d:+.1f} MB){flag}")
        if flag:
            bad(f"{k}-ZIP waechst/schrumpft ungewoehnlich stark")


def check_update_diff(old, new):
    print("== 2. Datei-Differenz Update-ZIP (neu/weg)")
    zo = set(zipfile.ZipFile(zips(old)["Update"]).namelist())
    zn = set(zipfile.ZipFile(zips(new)["Update"]).namelist())
    for tag, s in (("neu", zn - zo), ("weg", zo - zn)):
        for n in sorted(s)[:40]:
            print(f"  {tag}: {n}")
        if len(s) > 40:
            print(f"  {tag}: ... +{len(s) - 40} weitere")
    return zn


def check_no_user_data(names):
    print("== 3. Keine Nutzerdaten im Update-ZIP")
    for n in names:
        low = "/" + n.replace("\\", "/").lower()
        if any(f in low for f in FORBIDDEN):
            bad(f"verbotener Inhalt: {n}")


def check_skins(new):
    print("== 4. Skins in Voll- und Update-ZIP == src/skins auf main (Git)")
    files = git("ls-files", "src/skins").stdout.decode().split()
    # Zeilenenden ignorieren (Git LF, Build evtl. CRLF)
    norm = lambda b: b.replace(b"\r\n", b"\n")
    for k in ("Voll", "Update"):
        z = zipfile.ZipFile(zips(new)[k])
        for f in files:
            name = "Callers_Caddy/" + f[len("src/"):]
            try:
                data = z.read(name)
            except KeyError:
                bad(f"{k}: {name} fehlt")
                continue
            if norm(data) != norm(git("show", f"main:{f}").stdout):
                bad(f"{k}: {name} weicht von main ab")
        print(f"  {k}: {len(files)} Skin-Dateien geprueft")


def check_version(new):
    print("== 5. Version im Code-ZIP")
    src = zipfile.ZipFile(zips(new)["Code"])
    mp = next((n for n in src.namelist() if n.endswith("src/main.py")), None)
    if mp and f'__version__ = "{new}"' in src.read(mp).decode("utf-8", "replace"):
        print(f"  Code-ZIP main.py traegt {new}")
    else:
        bad(f"Code-ZIP: __version__ != {new}")


def check_licenses(new):
    print("== 6. Lizenzen in Voll- und Update-ZIP, keine ASIO-DLL")
    for k in ("Voll", "Update"):
        names = set(zipfile.ZipFile(zips(new)[k]).namelist())
        for f in ("Callers_Caddy/LICENSE", "Callers_Caddy/licenses/THIRD_PARTY.txt"):
            if f not in names:
                bad(f"{k}: {f} fehlt")
        for n in names:
            if "asio" in n.lower() and n.lower().endswith(".dll"):
                bad(f"{k}: ASIO-DLL im ZIP: {n}")


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    old, new = sys.argv[1], sys.argv[2]
    print(f"Release-Ordner: {RELEASES_DIR}")
    check_sizes(old, new)
    names = check_update_diff(old, new)
    check_no_user_data(names)
    check_skins(new)
    check_version(new)
    check_licenses(new)
    print("\nERGEBNIS:", "OK" if ok else "BITTE PRUEFEN")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
