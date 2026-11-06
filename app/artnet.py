"""Protocole Art-Net : en-tetes de paquets, ArtDmx, requetes RDM, adresses du PC."""
import socket
import struct

OP_POLL, OP_POLL_REPLY, OP_DMX = 0x2000, 0x2100, 0x5000
OP_TOD_REQUEST, OP_TOD_DATA, OP_TOD_CONTROL, OP_RDM = 0x8000, 0x8100, 0x8200, 0x8300

PID_DEVICE_INFO = 0x0060
PID_MODEL_DESCRIPTION = 0x0080
PID_MANUFACTURER_LABEL = 0x0081
PID_DEVICE_LABEL = 0x0082
PID_PERSONALITY_DESCRIPTION = 0x00E1
PID_SLOT_INFO = 0x0120
PID_DEFAULT_SLOT_VALUE = 0x0121


def art_header(op):
    return b"Art-Net\x00" + struct.pack("<H", op) + b"\x00\x0e"


def port_bytes(universe):
    return bytes([(universe >> 8) & 0x7F]), bytes([universe & 0xFF])


def rdm_get(dest, src, tn, pid, pd=b""):
    """Requete RDM GET, sans le start code 0xCC (comme l'attend ArtRdm), checksum inclus."""
    msg = (bytes([0xCC, 0x01, 24 + len(pd)]) + dest + src + bytes([tn, 1, 0]) + b"\x00\x00"
           + bytes([0x20]) + struct.pack(">H", pid) + bytes([len(pd)]) + pd)
    return msg[1:] + struct.pack(">H", sum(msg) & 0xFFFF)


def artdmx(universe, data, seq):
    return (art_header(OP_DMX) + bytes([seq, 0]) + struct.pack("<H", universe & 0x7FFF)
            + struct.pack(">H", len(data)) + bytes(data))


def local_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    for probe in ("2.255.255.255", "10.255.255.255", "192.168.1.1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((probe, 6454))
            ips.add(s.getsockname()[0])
            s.close()
        except OSError:
            pass
    ips.discard("0.0.0.0")
    return sorted(ips)


def broadcast_targets(target_ip, own_ips):
    """Adresses ou envoyer un ArtPoll : la cible choisie, les broadcasts usuels et ceux des reseaux du PC."""
    out = [target_ip, "255.255.255.255", "2.255.255.255", "10.255.255.255"]
    for ip in own_ips:
        if not ip.startswith("127."):
            out.append(ip.rsplit(".", 1)[0] + ".255")
    return list(dict.fromkeys(t for t in out if t))
