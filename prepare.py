"""Get this PC ready to play, whichever client it has: run by play.bat and play_dotnet.bat.

    1. find the client (fo3conf.py: FO3_GAME, fo3.local.env, or a search) and keep it in
       fo3.local.env, so the next start does not search again
    2. gamedata/fifadb.sqlite: extract it when it is missing or came from another client;
       gamedata/cdn: unpack cdn/fo3id-cdn.zip when the client has no CDN copy of its own (3Sea)
    3. certs/server.pem: make a self-signed certificate for APSEODESK172 when there is none
    4. launcher/fifalauncher.exe: build it when it is missing or older than its source
    5. the hosts entry for APSEODESK172: only checked (writing it needs an administrator)

The client folder is only read. Status goes to stderr; stdout is the `NAME=value` lines the
launcher needs, for play.bat's `for /f`. Exit code 1 when the game cannot start.
"""
import datetime, ipaddress, os, subprocess, sys

import fo3conf

HERE = fo3conf.HERE
HOST = "APSEODESK172"
FIFADB = os.path.join(HERE, "gamedata", "fifadb.sqlite")
CERT = os.path.join(HERE, "certs", "server.pem")
LAUNCHER_SRC = os.path.join(HERE, "launcher", "fifalauncher.cs")
LAUNCHER_EXE = os.path.join(HERE, "launcher", "fifalauncher.exe")
CSC = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Microsoft.NET", f, "v4.0.30319", "csc.exe")
       for f in ("Framework", "Framework64")]
HOSTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "drivers", "etc", "hosts")


def say(msg):
    print(msg, file=sys.stderr, flush=True)


def same_dir(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def ensure_fifadb():
    src = fo3conf.fifadb_source().get("game")
    if os.path.isfile(FIFADB) and src and same_dir(src, fo3conf.GAME):  # no record: extract once to be sure
        return True
    say(f"extracting the player database from {fo3conf.GAME} ...")
    return subprocess.call([sys.executable, os.path.join(HERE, "extract_fifadb.py"), fo3conf.GAME],
                           stdout=sys.stderr) == 0


def ensure_cdn():
    """gamedata/cdn from cdn/fo3id-cdn.zip (in git) when the client has no CDN copy of its own."""
    if fo3conf.ASSETS_OWN or os.path.isdir(os.path.join(fo3conf.SERVER_CDN, "externalAssets")):
        return True
    sys.path.insert(0, os.path.join(HERE, "tools"))
    import cdn_zip
    if os.path.isfile(cdn_zip.ZIP):
        say(f"unpacking {cdn_zip.ZIP} into {fo3conf.SERVER_CDN} ...")
        say(f"  {cdn_zip.unpack()} files")
    return True


def ensure_cert():
    if os.path.isfile(CERT):
        return True
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOST)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(HOST),
                                                        x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
                           critical=False)
            .sign(key, hashes.SHA256()))
    os.makedirs(os.path.dirname(CERT), exist_ok=True)
    with open(CERT, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    say(f"made {CERT} for {HOST}")
    return True


def ensure_launcher():
    if os.path.isfile(LAUNCHER_EXE) and os.path.getmtime(LAUNCHER_EXE) >= os.path.getmtime(LAUNCHER_SRC):
        return True
    csc = next((c for c in CSC if os.path.isfile(c)), None)
    if not csc:
        say("no .NET Framework csc.exe to build launcher/fifalauncher.exe")
        return os.path.isfile(LAUNCHER_EXE)
    say("building launcher/fifalauncher.exe ...")
    ok = subprocess.call([csc, "/nologo", "/target:winexe", f"/out:{LAUNCHER_EXE}", LAUNCHER_SRC],
                         stdout=sys.stderr) == 0
    return ok or os.path.isfile(LAUNCHER_EXE)


def hosts_ok():
    want = fo3conf.HTTP_BIND if fo3conf.HTTP_BIND not in ("0.0.0.0", "") else None
    try:
        with open(HOSTS, encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split("#", 1)[0].split()
                if len(parts) >= 2 and HOST.lower() in (p.lower() for p in parts[1:]):
                    if want and parts[0] != want:
                        say(f"WARNING: hosts maps {HOST} to {parts[0]}, but FO3_HTTP_BIND is {want}")
                    return True
    except OSError:
        pass
    say(f"MISSING: the hosts entry. As administrator, add this line to {HOSTS}:\n"
        f"    {fo3conf.HTTP_BIND if fo3conf.HTTP_BIND not in ('0.0.0.0', '') else '127.0.0.1'} {HOST}")
    return False


def main():
    say(fo3conf.summary())
    if fo3conf.GAME_FROM == "missing":
        return 1
    if fo3conf.GAME_FROM == "found" and not os.environ.get("FO3_GAME", "").strip():
        fo3conf.write_local({"FO3_GAME": fo3conf.GAME})
        say(f"kept this client in {fo3conf.LOCAL_FILE}")
    ok = ensure_fifadb() & ensure_cdn() & ensure_cert() & ensure_launcher()
    hosts = hosts_ok()
    if not os.path.isfile(os.path.join(HERE, "gamedata", "state.json")):
        say("note: no gamedata/state.json yet, so the game starts with a new account "
            "(copy it from your other PC to keep your save)")
    for k, v in fo3conf.resolved().items():
        print(f"{k}={v}")
    return 0 if ok and hosts else 1


if __name__ == "__main__":
    sys.exit(main())
