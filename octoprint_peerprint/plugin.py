from .data import Keys, PRINT_FILE_DIR
import shutil
from octoprint.filemanager.destinations import FileDestinations
from octoprint.filemanager import NoSuchStorage
import os
import time
from pathlib import Path
import socket
from peerprint.filesharing import Fileshare
from peerprint.server import P2PServer, P2PServerOpts
from peerprint.client import RpcError, P2PClient

class Plugin:
    PP_CONNECT_ATTEMPTS = 3
    PP_CONNECT_DELAY = 1
    GET_ADDR_TIMEOUT = 3

    def __init__(self, settings, file_manager, data_folder, logger):
        self._settings = settings
        self._logger = logger
        self.server = None
        self.client = None
        self.fileshare = None
        self._data_folder = data_folder
        self._file_manager = file_manager

    def _set_key(self, k, v):
        return self._settings.set([k.setting], v)

    def _get_key(self, k, default=None):
        v = self._settings.get([k.setting])
        return v if v is not None else default

    def _path_on_disk(self, path: str, sd: bool):
        try:
            return self._file_manager.path_on_disk(
                FileDestinations.SDCARD if sd else FileDestinations.LOCAL, path
            )
        except NoSuchStorage:
            return None

    def start(self):
        self._init_server()
        self._init_fileshare()
        self.tick() # update statuses

    def tick(self):
        # Forward statuses to settings page
        if self.client is None:
            self._set_key(Keys.CLIENT_STATUS, "Not initialized")
        elif self.client.is_ready():
            self._set_key(Keys.CLIENT_STATUS, "Connected to server")
        else:
            self._set_key(Keys.CLIENT_STATUS, "Not connected")

        if self.server is None:
            self._set_key(Keys.SERVER_STATUS, "Not initialized (possibly remote)")
        elif self.server.is_ready():
            self._set_key(Keys.SERVER_STATUS, "Running")
        else:
            self._set_key(Keys.SERVER_STATUS, "Not running")

        if self.fileshare is None:
            self._set_key(Keys.IPFS_STATUS, "Not initialized")
        elif self.fileshare.is_ready():
            self._set_key(Keys.IPFS_STATUS, "Running")
        else:
            self._set_key(Keys.IPFS_STATUS, "Not Running")


    def _can_bind_addr(self, addr):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(addr)
        except OSError:
            return False
        finally:
            s.close()
        return True

    def get_local_addr(self):
        # https://stackoverflow.com/a/2838309
        # Note that this is vulnerable to race conditions in that
        # the port is open when it's assigned, but could be reassigned
        # before the caller can use it.
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(self.GET_ADDR_TIMEOUT)
        checkaddr = tuple(
            [
                self._settings.global_get(["server", "onlineCheck", v])
                for v in ("host", "port")
            ]
        )
        try:
            s.connect(checkaddr)
            result = s.getsockname()
        finally:
            # Note: close has no effect on already closed socket
            s.close()

        if self._can_bind_addr(result):
            return f"{result[0]}:{result[1]}"

        # For whatever reason, client-based local IP resolution can sometimes still fail to bind.
        # In this case, fall back to MDNS based resolution
        # https://stackoverflow.com/a/57355707
        self._logger.warning(
            "Online check based IP resolution failed to bind; attempting MDNS local IP resolution"
        )
        hostname = socket.gethostname()
        try:
            local_ip = socket.gethostbyname(f"{hostname}.local")
        except socket.gaierror:
            local_ip = socket.gethostbyname(hostname)

        # Find open port: https://stackoverflow.com/a/2838309
        # This will raise OSError if it cannot bind to that address either
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((local_ip, 0))
            s.listen(1)
            port = s.getsockname()[1]
        finally:
            s.close()
        return f"{local_ip}:{port}"


    def _init_fileshare(self, fs_cls=Fileshare):
        # Note: fileshare_dir referenced when cleaning up old files
        self.fileshare_dir = self._path_on_disk(
            f"{PRINT_FILE_DIR}/fileshare/", sd=False
        )
        self._logger.info("Starting fileshare")
        self._set_key(Keys.IPFS_STATUS, "Initializing")
        self.fileshare = fs_cls(self.fileshare_dir, self._logger)

    def cleanup_fileshare(self, keep_hashes):
        if not os.path.exists(self.fileshare_dir):
            return n

        # Loop through all .gjob and .gcode files in base directory and delete them if they aren't referenced or acquired by us
        n = 0
        for d in os.listdir(self.fileshare_dir):
            name, suffix = os.path.splitext(d)
            if suffix not in ("", ".gjob", ".gcode", ".gco"):
                self._logger.debug(
                    f"Fileshare cleanup ignoring non-printable file: {os.path.join(self.fileshare_dir, name)}"
                )
                continue
            if name not in keep_hashes:
                p = Path(self.fileshare_dir) / d
                if p.is_dir():
                    # Have to use shutil instead of p.rmdir() as the directory will likely not be empty
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink()
                n += 1
        return n


    def _init_server(self):
        self._set_key(Keys.CLIENT_STATUS, "Initializing")
        addr = self._get_key(Keys.SERVER_ADDR)
        start_proc = False
        if addr == "":
            addr = self.get_local_addr()
            start_proc = True
            self._set_key(Keys.SERVER_STATUS, f"Initializing ({addr})")
        else:
            self._set_key(Keys.SERVER_STATUS, f"Remove ({addr})")
        self._logger.debug(f"Init P2P server (addr={addr}, start_proc={start_proc}))")

        certsDir = Path(self._data_folder) / "certs"
        if not certsDir.exists():
            certsDir.mkdir()
        connDir = Path(self._data_folder) / "connections"
        if not connDir.exists():
            connDir.mkdir()

        if start_proc:
            self.server = P2PServer(
                P2PServerOpts(
                    addr=addr,
                    www="0.0.0.0:8334",
                    driverCfg=str(Path(self._data_folder) / "driver.yaml"),
                    wwwCfg=str(Path(self._data_folder) / "www.yaml"),
                    regDBWorld=str(Path(self._data_folder) / "registry_world.sqlite3"),
                    regDBLocal=str(Path(self._data_folder) / "registry_local.sqlite3"),
                    certsDir=str(certsDir),
                    connDir=str(connDir),
                    serverCert="server.crt",
                    serverKey="server.key",
                    rootCert="rootCA.crt",
                ),
                self._logger,
            )
        self.client = P2PClient(addr, str(certsDir), self._logger)

        for i in range(self.PP_CONNECT_ATTEMPTS):
            self._set_key(Keys.CLIENT_STATUS, f"Waiting for P2P server...")
            self._logger.debug("Waiting for P2P server...")
            if self.client.ping():
                self._logger.debug("P2P server ready")
                break
            time.sleep(self.PP_CONNECT_DELAY)

