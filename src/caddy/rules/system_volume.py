"""Rule-Aktion "Set System Volume": Windows-Lautstaerke setzen (intern#222).

Ziel ist das in der Statusleiste gewaehlte Ausgabegeraet (Abgleich ueber den
Namen), sonst das Windows-Standardgeraet. Die Stummschaltung wird immer
aufgehoben. pycaw wird erst beim Ausfuehren geladen; ausserhalb von Windows
oder ohne pycaw passiert nichts.
"""
import re
import sys

QT_FREE = True

MODE_AT_LEAST = "at_least"   # nur anheben, hoeheren Pegel stehen lassen
MODE_EXACT = "exact"
MODES = [MODE_AT_LEAST, MODE_EXACT]


def target_level(current: float, percent, mode: str) -> float | None:
    """Neuer Pegel (0.0-1.0) oder None, wenn nichts zu tun ist."""
    wanted = max(0, min(100, int(percent))) / 100.0
    if mode != MODE_EXACT and current >= wanted:
        return None
    if abs(current - wanted) < 0.005:
        return None
    return wanted


def _norm(name) -> str:
    """Vergleichsform: ohne Gross/Klein und ohne Windows-Nummer ("(3- Samson"),
    die WDM-KS im Namen weglaesst."""
    return re.sub(r"\(\d+- ", "(", (name or "").strip()).casefold()


def pick_endpoint(device_name: str | None, endpoints):
    """Endpunkt zum Geraetenamen aus sounddevice, sonst None.

    endpoints: Liste (FriendlyName, Endpunkt). MME kuerzt Namen auf 31 Zeichen,
    daher zaehlt nach dem exakten Treffer auch ein gemeinsamer Anfang.
    """
    name = _norm(device_name)
    if not name:
        return None
    named = [(_norm(n), ep) for n, ep in endpoints]
    for n, ep in named:
        if n == name:
            return ep
    for n, ep in named:
        if n and (n.startswith(name) or name.startswith(n)):
            return ep
    return None


def set_system_volume(percent, mode: str = MODE_AT_LEAST,
                      device_name: str | None = None) -> str:
    """Setzt die Systemlautstaerke; liefert eine Zeile fuers Rules-Log."""
    if sys.platform != "win32":
        return "Set System Volume: nur unter Windows, uebersprungen"
    try:
        from pycaw.pycaw import AudioUtilities
        from pycaw.constants import DEVICE_STATE, EDataFlow
    except ImportError:
        return "Set System Volume: pycaw fehlt, uebersprungen"

    device = None
    if device_name:
        active = AudioUtilities.GetAllDevices(EDataFlow.eRender.value,
                                              DEVICE_STATE.ACTIVE.value)
        device = pick_endpoint(device_name,
                               [(d.FriendlyName, d) for d in active if d])
    if device is None:
        device = AudioUtilities.GetSpeakers()
    if device is None:
        return "Set System Volume: kein Ausgabegeraet gefunden"

    vol = device.EndpointVolume
    if vol.GetMute():
        vol.SetMute(0, None)
    new = target_level(vol.GetMasterVolumeLevelScalar(), percent, mode)
    if new is not None:
        vol.SetMasterVolumeLevelScalar(new, None)
    level = "unveraendert" if new is None else f"{round(new * 100)} %"
    return f"Set System Volume: {device.FriendlyName} -> {level}"
