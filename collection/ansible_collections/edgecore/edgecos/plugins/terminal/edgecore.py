# (c) Your Company
# GNU General Public License v3.0+
#
# Terminal plugin for Edge-core Enterprise Switch (ECS series, IOS-like CLI).
#
# The terminal plugin hooks the CLI session: it declares what the prompts look
# like, how to move into privileged (enable) mode, how to disable paging, and
# which output patterns indicate an error. network_cli selects this plugin via
#   ansible_network_os: edgecore.edgecos.edgecore
#
# Adjust the regexes below to match the exact prompts/messages on YOUR firmware
# (capture them from a real session; use `show ?` and trigger an error to see
# the exact wording).
from __future__ import absolute_import, division, print_function
__metaclass__ = type

DOCUMENTATION = """
author: Macauley Cheng (@macauleycheng)
name: edgecore
short_description: Terminal plugin for Edge-core Enterprise Switches (ECS series)
description:
- This terminal plugin defines the prompt and error regexes, enable-mode entry, and
  paging-disable behavior for the Edge-core Enterprise Switch IOS-like CLI, selected by
  setting the ansible_network_os value to edgecore.edgecos.edgecore.
version_added: "0.1.0"
"""

import json
import re

from ansible.errors import AnsibleConnectionFailure
from ansible.module_utils.common.text.converters import to_text, to_bytes
from ansible.plugins.terminal import TerminalBase


class TerminalModule(TerminalBase):

    # Prompts shown when the CLI is ready for input.
    #   hostname>          user EXEC
    #   hostname#          privileged EXEC
    #   hostname(config)#  config modes
    terminal_stdout_re = [
        re.compile(br"[\r\n]?[\w.\-]+(?:\([^)]+\))?[>#]\s*$"),
    ]

    # Patterns that mean the last command failed. Tune to your firmware wording.
    terminal_stderr_re = [
        re.compile(br"% ?Error", re.I),
        re.compile(br"% ?Invalid( input)?", re.I),
        re.compile(br"% ?Incomplete command", re.I),
        re.compile(br"% ?Ambiguous command", re.I),
        re.compile(br"% ?Unknown command", re.I),
        re.compile(br"connection timed out", re.I),
    ]

    # Prompt shown when the device asks for the enable password.
    terminal_initial_prompt = br"[Pp]assword:"

    def on_open_shell(self):
        """Runs right after the shell opens: disable output paging so Ansible
        gets the full command output instead of a --More-- pager."""
        try:
            # Most Edge-core/IOS-like firmware accept 'terminal length 0'.
            self._exec_cli_command(b"terminal length 0")
        except AnsibleConnectionFailure:
            # Some firmware use a different command; try a common alternative.
            try:
                self._exec_cli_command(b"terminal datadump")
            except AnsibleConnectionFailure:
                raise AnsibleConnectionFailure(
                    "unable to disable terminal paging (adjust on_open_shell "
                    "in the edgecore terminal plugin for your firmware)"
                )

    def on_become(self, passwd=None):
        """Enter privileged EXEC (enable) mode if we are not already in it."""
        if self._get_prompt().endswith(b"#"):
            return

        cmd = {u"command": u"enable"}
        if passwd:
            # Prompt shown when the device asks for the enable password.
            cmd[u"prompt"] = to_text(r"[\r\n]?(?:enable )?[Pp]assword:\s?$",
                                     errors="surrogate_or_strict")
            cmd[u"answer"] = passwd
            cmd[u"prompt_retry_check"] = True

        try:
            self._exec_cli_command(
                to_bytes(json.dumps(cmd), errors="surrogate_or_strict")
            )
            prompt = self._get_prompt()
            if prompt is None or not prompt.strip().endswith(b"#"):
                raise AnsibleConnectionFailure(
                    "failed to enter privileged mode, got prompt: %s" % prompt
                )
        except AnsibleConnectionFailure as e:
            raise AnsibleConnectionFailure(
                "unable to enter privileged mode: %s" % to_text(e)
            )

    def on_unbecome(self):
        """Leave privileged/config mode back to a base prompt."""
        prompt = self._get_prompt()
        if prompt is None:
            return
        if b"(config" in prompt:
            self._exec_cli_command(b"end")
            self._exec_cli_command(b"disable")
        elif prompt.endswith(b"#"):
            self._exec_cli_command(b"disable")
