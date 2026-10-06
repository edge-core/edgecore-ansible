# edgecore.edgecos — Ansible network platform plugins for Edge-core Enterprise Switches

> **This is the standalone `edgecore.edgecos` collection repo** (plugins + CI).
> The full teaching project — inventory, roles, playbooks, examples, and docs —
> lives on `master` / https://github.com/edge-core/edgecore-ansible.

This collection provides the two plugins that make Ansible's generic
`ansible.netcommon` modules understand the Edge-core Enterprise Switch (ECS
series) IOS-like CLI:

| Plugin | File | Responsibility |
|--------|------|----------------|
| terminal | `plugins/terminal/edgecore.py` | Prompt regexes, enter/leave enable mode, disable paging, error detection |
| cliconf  | `plugins/cliconf/edgecore.py` | `get_config` / `edit_config` / `get()` / capabilities / save |

Once installed, set `ansible_network_os: edgecore.edgecos.edgecore` and the standard
modules `ansible.netcommon.cli_command` and `ansible.netcommon.cli_config` work
against Edge-core switches — no per-command custom modules required.

## Why plugins instead of custom modules?

`network_cli` picks a terminal + cliconf plugin at runtime from
`ansible_network_os`. Those two plugins encode all the device-specific behavior.
Writing them is far less work than maintaining a full set of resource modules,
and it is the same pattern vendors like Nokia use for their SR OS integration.
(Rephrased from Ansible network developer docs for licensing compliance.)

## Install

```bash
# From this directory (the one containing galaxy.yml):
ansible-galaxy collection build
ansible-galaxy collection install edgecore-edgecos-0.1.0.tar.gz

# Or, for development, point ANSIBLE_COLLECTIONS_PATH at the tree:
export ANSIBLE_COLLECTIONS_PATH=/path/to/edgecore-ansible/collection
```

## Use

`group_vars/edgecore_switches.yml`:

```yaml
ansible_connection: ansible.netcommon.network_cli
ansible_network_os: edgecore.edgecos.edgecore # <-- selects the plugins above
ansible_user: admin
ansible_password: "YourPassword"
ansible_become: true
ansible_become_method: ansible.netcommon.enable
ansible_become_password: "YourEnablePassword"
```

Ad-hoc, like your `ios_command` example:

```bash
ansible switches -m ansible.netcommon.cli_command -a "command='show interface brief'"
```

Push config with the generic config module:

```yaml
- name: Configure VLAN 10
  ansible.netcommon.cli_config:
    config: |
      vlan database
      vlan 10 name Production_LAN media ethernet
      exit
```

## IMPORTANT — this is a starter, tune it to your firmware

The regexes and commands are best-effort defaults for a typical IOS-like ECS
CLI. Before relying on it, capture a real session and adjust:

1. **Prompt regex** (`terminal_stdout_re`) — must match your actual prompt.
2. **Error patterns** (`terminal_stderr_re`) — trigger a bad command and copy the
   exact `% ...` wording.
3. **Paging disable** (`on_open_shell`) — confirm `terminal length 0` works;
   otherwise change it.
4. **Enable prompt** (`on_become`) — confirm the enable password prompt wording.
5. **Config/save commands** (`edit_config`, `save_config`) — confirm `configure`
   / `end` / `copy running-config startup-config` match your firmware.

Debug with maximum verbosity to see exactly what is sent and received:

```bash
ansible-playbook site.yml -vvvv
# or set ANSIBLE_LOG_PATH and ANSIBLE_DEBUG=1
```

## Decision guide: do you need this?

- **Small / one-off / teaching example** → stay on `cli_command` in playbooks (no plugin).
- **Many switches, many task types, want idempotency + clean playbooks** → use these plugins.
- **Publishing an officially supported collection with resource modules** → extend
  this into full `edgecore_vlan`, `edgecore_l2_interfaces`, etc. (much more effort).
