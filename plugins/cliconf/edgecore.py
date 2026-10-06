# (c) Your Company
# GNU General Public License v3.0+
#
# Cliconf plugin for Edge-core Enterprise Switch (ECS series, IOS-like CLI).
#
# The cliconf plugin is the abstraction the generic ansible.netcommon modules
# (cli_command, cli_config) use to talk to the device. It knows how to:
#   - run a command and return output          -> get()
#   - read the running/startup config          -> get_config()
#   - push config lines into config mode        -> edit_config()
#   - describe the device's capabilities        -> get_device_operations()/get_capabilities()
#
# network_cli selects this plugin via:
#   ansible_network_os: edgecore.edgecos.edgecore
from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = """
author: Macauley Cheng (@macauleycheng)
name: edgecore
short_description: Cliconf plugin for Edge-core Enterprise Switches (ECS series)
description:
- This cliconf plugin provides low-level abstractions (get, get_config, edit_config,
  get_capabilities, save_config) for Edge-core Enterprise Switch IOS-like CLI, used by
  the generic ansible.netcommon cli_command / cli_config modules.
version_added: "0.1.0"
"""

import json
import re

from ansible.module_utils.common.text.converters import to_text
from ansible.plugins.cliconf import CliconfBase


class Cliconf(CliconfBase):

    def get_device_info(self):
        device_info = {"network_os": "edgecore"}
        try:
            reply = self.get("show version")
            data = to_text(reply, errors="surrogate_or_strict").strip()

            # Best-effort parsing. Adjust regexes to your firmware's
            # "show version" layout.
            m = re.search(r"[Vv]ersion[:\s]+(\S+)", data)
            if m:
                device_info["network_os_version"] = m.group(1)

            m = re.search(r"(?:Model|Hardware)[:\s]+(\S+)", data)
            if m:
                device_info["network_os_model"] = m.group(1)
        except Exception:
            # Never fail device discovery just because parsing failed.
            pass
        return device_info

    def get_config(self, source="running", flags=None, format="text"):
        if source not in ("running", "startup"):
            raise ValueError(
                "fetching configuration from %s is not supported" % source
            )
        cmd = "show running-config" if source == "running" else "show startup-config"
        if flags:
            cmd += " " + " ".join(flags)
        return self.send_command(cmd)

    def edit_config(self, candidate=None, commit=True, replace=None, comment=None):
        """Push a list of config lines: enter config mode, send each line, exit."""
        resp = {}
        results = []
        requests = []

        if not candidate:
            raise ValueError("must provide a candidate config to load")

        if isinstance(candidate, str):
            candidate = candidate.splitlines()

        # Enter global config mode.
        self.send_command("configure")
        try:
            for line in (to_text(c).strip() for c in candidate):
                if not line or line == "configure":
                    continue
                requests.append(line)
                results.append(self.send_command(line))
        finally:
            # Always return to privileged EXEC even if a line errored.
            self.send_command("end")

        resp["request"] = requests
        resp["response"] = results
        return resp

    def get(self, command=None, prompt=None, answer=None, sendonly=False,
            newline=True, output=None, check_all=False):
        if not command:
            raise ValueError("must provide value of command to execute")
        if output:
            raise ValueError(
                "'output' value %s is not supported for get" % output
            )
        return self.send_command(
            command=command, prompt=prompt, answer=answer, sendonly=sendonly,
            newline=newline, check_all=check_all,
        )

    def get_device_operations(self):
        return {
            "supports_diff_replace": False,
            "supports_commit": False,
            "supports_rollback": False,
            "supports_defaults": False,
            "supports_onbox_diff": False,
            "supports_commit_comment": False,
            "supports_multiline_delimiter": False,
            "supports_diff_match": True,
            "supports_diff_ignore_lines": True,
            "supports_generate_diff": True,
            "supports_replace": False,
        }

    def get_capabilities(self):
        result = super(Cliconf, self).get_capabilities()
        result["rpc"] += [
            "get_config", "edit_config", "get_device_info", "get_device_operations",
        ]
        result["device_operations"] = self.get_device_operations()
        return json.dumps(result)

    # ---- persist config (running -> startup) --------------------------------
    def save_config(self):
        """Convenience helper: persist running-config, auto-answering [y/n]."""
        return self.send_command(
            command="copy running-config startup-config",
            prompt=[r"(?i)\[y/n\]", r"(?i)startup-config", r"(?i)continue"],
            answer=["y", "y", "y"],
            check_all=True,
        )
