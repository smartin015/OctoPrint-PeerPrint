# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from .plugin import Plugin
from .data import ASSETS, update_info, Keys, TEMPLATES

class PeerprintPlugin(octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.StartupPlugin
):

    def on_after_startup(self):
        self._plugin = Plugin(
            self._settings,
            self._file_manager,
            self.get_plugin_data_folder(),
            self._logger,
        )
        self._plugin.start()
    
    ##~~ SettingsPlugin mixin

    def get_settings_defaults(self):
        return dict(
            [(member.setting, member.default) for member in Keys.__members__.values()]
        )

    def get_assets(self):
        return ASSETS

    def get_template_configs(self):
        return TEMPLATES

    def get_update_information(self):
        return update_info(self._plugin_version)

# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "Octoprint_peerprint Plugin"


# Set the Python version your plugin is compatible with below. Recommended is Python 3 only for all new plugins.
# OctoPrint 1.4.0 - 1.7.x run under both Python 3 and the end-of-life Python 2.
# OctoPrint 1.8.0 onwards only supports Python 3.
__plugin_pythoncompat__ = ">=3,<4"  # Only Python 3

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = PeerprintPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
