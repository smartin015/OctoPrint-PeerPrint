from enum import Enum

class Keys(Enum):
    SERVER_ADDR = ("peerprint_server_addr", "")
    SERVER_STATUS = ("peerprint_server_status", "Unknown")
    CLIENT_STATUS = ("peerprint_client_status", "Unknown")
    IPFS_STATUS = ("peerprint_ipfs_status", "Unknown")

    def __init__(self, setting, default):
        self.setting = setting
        if setting.endswith("_script") and not default.startswith(";"):
            self.default = GCODE_SCRIPTS[default]["gcode"]
        else:
            self.default = default

PRINT_FILE_DIR = "PeerPrint"

ASSETS = dict(
    js=[],
    css=[],
    less=[],
)

TEMPLATES = [
    dict(
        type="settings",
        name="PeerPrint",
        template="peerprint_settings.jinja2",
        custom_bindings=False,
    ),
]


def update_info(plugin_version):
    return dict(
        octoprint_peerprint=dict(
            displayName="PeerPrint Plugin",
            displayVersion=plugin_version,
            # version check: github repository
            type="github_release",
            user="smartin015",
            repo="OctoPrint-PeerPrint",
            current=plugin_version,
            stable_branch=dict(name="Stable", branch="main", comittish=["main"]),
            prerelease_branches=[
                dict(
                    name="Release Candidate",
                    branch="rc",
                    comittish=["rc", "main"],
                )
            ],
            # update method: pip
            pip="https://github.com/smartin015/OctoPrint-PeerPrint/archive/{target_version}.zip",
        )
    )
