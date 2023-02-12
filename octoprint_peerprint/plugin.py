from .data import Keys, PRINT_FILE_DIR
from octoprint.filemanager.destinations import FileDestinations
from octoprint.filemanager import NoSuchStorage
import time
from pathlib import Path
import socket
from peerprint.filesharing import Fileshare
from peerprint.server import P2PServer, P2PServerOpts, RpcError

class Plugin:
    PP_CONNECT_ATTEMPTS = 3
    PP_CONNECT_DELAY = 1
    GET_ADDR_TIMEOUT = 3

    def __init__(self, settings, file_manager, data_folder, logger):
        self._settings = settings
        self._logger = logger
        self.server = None
        self._data_folder = data_folder
        self._file_manager = file_manager

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
        self._fileshare = fs_cls(self.fileshare_dir, self._logger)

    def cleanup_fileshare(self):
        if not os.path.exists(self.fileshare_dir):
            return n

        # This cleans up all non-useful fileshare files across all network queues, so they aren't just taking up space.
        # First we collect all non-local queue items hosted by us - these are excluded from cleanup as someone may need to fetch them.
        keep_hashes = set()
        for name, q in self.q.queues.items():
            if name == ARCHIVE_QUEUE or name == DEFAULT_QUEUE:
                continue
            for j in q.as_dict()["jobs"]:
                if j["peer_"] == q.addr or j["acquired_by_"] == q.addr:
                    keep_hashes.add(j["hash"])

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
        addr = self._get_key(Keys.SERVER_ADDR)
        start_proc = False
        if addr == "":
            addr = self.get_local_addr()
            start_proc = True
        self._logger.debug(f"Init P2P server (addr={addr}, start_proc={start_proc}))")

        certsDir = Path(self._data_folder) / "peerprint_certs"
        if not certsDir.exists():
            certsDir.mkdir()

        self.server = P2PServer(
            P2PServerOpts(
                addr=addr,
                www="0.0.0.0:8334",
                cfg=str(Path(self._data_folder) / "peerprint.cfg"),
                certsDir=str(certsDir),
                serverCert="server.crt",
                serverKey="server.key",
                rootCert="rootCA.crt",
            ),
            self._logger,
            start_proc=start_proc,
        )

        for i in range(self.PP_CONNECT_ATTEMPTS):
            self._logger.debug("Waiting for P2P server...")
            if self.server.ping():
                self._logger.debug("P2P server ready")
                break
            time.sleep(self.PP_CONNECT_DELAY)

