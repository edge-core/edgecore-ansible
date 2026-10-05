# Configuring Edge-core Enterprise Switches with Ansible (CLI) — User Guide

This project teaches you how to use **Ansible** to automate the configuration of Edge-core Enterprise Switches (ECS series) over the **CLI**.
It covers: the Inventory, a Role-based Playbook, real Edge-core CLI configuration examples, saving the config (`copy running-config startup-config`), and auto-answering interactive prompts.

> Configuration commands are based on the Edge-core official FAQ:
> [Enterprise Switch FAQs — Edgecore Help Center](https://support.edge-core.com/hc/en-us/categories/360000061794-Enterprise-Switch-FAQs)
> (for example [VLAN translation on ECS4620](https://support.edge-core.com/hc/en-us/articles/360023573133-How-to-configure-vlan-translation-via-CLI-and-SNMP-on-ECS4620-series))
> The Edge-core Enterprise Switch CLI is IOS-like syntax; commands may vary slightly between models/firmware, so use the `?` help on your device or the CLI Guide as the source of truth. The external information above has been rephrased for compliance with licensing restrictions.

---

## 1. What this is / why it works this way

Edge-core Enterprise Switches do **not** have a dedicated Ansible platform (unlike `cisco.ios`).
So the most portable, generic approach is:

- Connect with **`ansible.netcommon.network_cli`** (SSH + CLI shell)
- Send commands with **`ansible.netcommon.cli_command`** (send CLI lines and collect the responses)

CLI command-mode flow (IOS-like):

```
User EXEC (>)  --enable-->  Privileged EXEC (#)  --configure-->  Global config (config)#
                                                            --interface xxx-->  Interface config (config-if)#
```

Ansible mapping:
- `become: true` + `become_method: ansible.netcommon.enable` → automatically run `enable` to reach privileged mode
- `configure` / `end` → enter / leave config mode
- `copy running-config startup-config` → save (so the config survives a reboot)

---

## 2. Project layout

```
edgecore-ansible/
├── ansible.cfg                     # Project settings (default inventory, timeouts, etc.)
├── requirements.yml                # Collections to install
├── site.yml                        # Main playbook (role-based, recommended for production)
├── inventory/
│   ├── hosts.yml                   # Host list
│   └── group_vars/
│       └── edgecore_switches.yml   # Group connection vars (credentials, connection type)
├── playbooks/
│   └── configure_switch_simple.yml # Single-file simple version (mirrors your original example)
└── roles/
    └── edgecore_cli/
        ├── defaults/main.yml       # Overridable vars: VLANs / interfaces / SVI / save switch
        ├── tasks/main.yml          # The flow: health check → backup → apply → save
        ├── templates/config_lines.j2  # Generates CLI commands from vars
        └── meta/main.yml
```

---

## 3. Prerequisites

The Ansible **control node must run on Linux / macOS / WSL** (Windows cannot natively run `ansible-playbook`; on Windows use **WSL2**).

### Tested with

This project was verified on the following toolchain (installed in an isolated Python virtual environment)
and run end-to-end against a real Edge-core switch:

| Component          | Version   | Notes                                             |
|--------------------|-----------|---------------------------------------------------|
| Python             | 3.13.6    | Control-node Python used for verification         |
| `ansible-core`     | 2.21.4    | Modern collection-aware release                   |
| `ansible.netcommon`| 8.7.1     | Pulls in `ansible.utils` 6.1.1 as a dependency    |
| `paramiko`         | 5.0.0     | SSH transport for `network_cli` (see step 1)      |
| `ansible-lint`     | 26.9.0    | Used for linting playbooks and plugins            |
| `edgecore.edgecos` | 0.1.0 | This project's local collection (terminal/cliconf plugins) |

> The control node needs Python 3.9+ for a current `ansible-core` (2.14+ dropped Python 3.8). On an
> older Python 3.8 node, pin `ansible-core==2.15` instead — the project also works there.

```bash
# 1) Install Ansible + an SSH transport library.
#    network_cli needs an SSH backend; paramiko is the simplest (pure Python).
python3 -m pip install --user ansible paramiko
#    (ansible-pylibssh is a faster alternative to paramiko but needs a compiler.)

# 2) Install the required collections
ansible-galaxy collection install -r requirements.yml

# 3) Confirm you can reach the switch over SSH
ssh admin@192.168.1.10
```

---

## 4. Configure your environment

### 4.1 Inventory — `inventory/hosts.yml`

```yaml
all:
  children:
    edgecore_switches:
      hosts:
        edgecore_switch01:
          ansible_host: 192.168.1.10
        # edgecore_switch02:
        #   ansible_host: 192.168.1.11
```

### 4.2 Connection vars — `inventory/group_vars/edgecore_switches.yml`

```yaml
ansible_connection: ansible.netcommon.network_cli
ansible_network_os: edgecore.edgecos.edgecore   # this project's own terminal/cliconf plugins
ansible_user: admin
ansible_password: "YourPassword"

ansible_become: true
ansible_become_method: ansible.netcommon.enable
ansible_become_password: "YourEnablePassword"   # leave empty if there is no enable password
```

---

## 5. Define the configuration you want (change vars, not the flow)

Edit `roles/edgecore_cli/defaults/main.yml` (or override in `host_vars`):

```yaml
edgecore_cli_vlans:
  - id: 10
    name: "Production_LAN"
  - id: 20
    name: "Guest_WiFi"

edgecore_cli_interfaces:
  - name: "ethernet 1/1"
    description: "Uplink_to_Core"
    mode: "trunk"
    trunk_allowed_vlans: "10,20"
    enabled: true
  - name: "ethernet 1/2"
    description: "PC_Production"
    mode: "access"
    access_vlan: 10
    enabled: true

edgecore_cli_svi:
  - vlan_id: 10
    ipv4: "192.168.10.1/24"
    enabled: true

edgecore_cli_save_config: true      # auto-save after applying
edgecore_cli_backup_before: true    # back up running-config to ./backups before applying
```

These vars are turned by `templates/config_lines.j2` into Edge-core CLI like this:

```
vlan database
vlan 10 name Production_LAN media ethernet
vlan 20 name Guest_WiFi media ethernet
exit
interface ethernet 1/1
description Uplink_to_Core
switchport mode trunk
switchport trunk allowed vlan add 10,20
no shutdown
exit
interface ethernet 1/2
description PC_Production
switchport mode access
switchport access vlan 10
no shutdown
exit
interface vlan 10
ip address 192.168.10.1/24
no shutdown
exit
```

---

## 6. Quick smoke test (one-liner, read-only)

Before running any playbook, confirm the connection and the plugins work with a single ad-hoc
command — no playbook required. This only sends a read-only `show` command, so it never changes
the switch. It is the Edge-core equivalent of `ansible switches -m ios_command -a "commands='...'"`;
here we use the generic `cli_command` module driven by this project's `edgecore.edgecos` plugins.

```bash
# Run one show command against the whole group
ansible edgecore_switches -m ansible.netcommon.cli_command -a "command='show version'"

# Or target a single host
ansible edgecore_switch01 -m ansible.netcommon.cli_command -a "command='show running-config'"

# Other handy read-only checks
ansible edgecore_switches -m ansible.netcommon.cli_command -a "command='show interfaces status'"
ansible edgecore_switches -m ansible.netcommon.cli_command -a "command='show vlan'"
```

A `SUCCESS` result with the device output means SSH, credentials, `ansible_network_os:
edgecore.edgecos.edgecore`, and the terminal/cliconf plugins are all working. If this fails, fix it
before running the playbooks (see [Troubleshooting](#11-troubleshooting)).

> Why not `cisco.ios.ios_command`? That module is bound to Cisco's own terminal/cliconf plugins. It
> may *appear* to work on Edge-core by coincidental CLI similarity, but it breaks as soon as prompts,
> error strings, or the save command differ. Using `cli_command` with `ansible_network_os:
> edgecore.edgecos.edgecore` is the robust, portable equivalent for Edge-core switches.

---

## 7. Run it

```bash
# Enter the project directory
cd edgecore-ansible

# Syntax check first (strongly recommended)
ansible-playbook site.yml --syntax-check

# Preview the commands that would be sent (does not change the device)
ansible-playbook site.yml --check --diff

# Apply for real
ansible-playbook site.yml

# Target a single switch
ansible-playbook site.yml --limit edgecore_switch01

# Use the simple single-file version (mirrors your original example)
ansible-playbook playbooks/configure_switch_simple.yml
```

> Note: this project was generated on a Windows machine that does not have Ansible installed,
> so run `--syntax-check` on your Linux / WSL control node.

---

## 8. Saving and auto-answering `[y/n]` prompts

Some firmware asks `Are you sure? [y/n]` on `copy running-config startup-config`.
Use `cli_command`'s `prompt` / `answer` to respond automatically:

```yaml
- name: "Save running-config to startup-config"
  ansible.netcommon.cli_command:
    command: "copy running-config startup-config"
    prompt:
      - "(?i)\\[y/n\\]"
      - "(?i)startup-config"
    answer:
      - "y"
      - "y"
    check_all: true            # match multiple prompts in order
  vars:
    ansible_command_timeout: 30
```

---

## 9. "Send multiple lines at once" vs "send line by line"

Your original example joined multiple lines with `\n` into one command:

```yaml
command: "configure\ninterface vlan 10\nname Production_LAN\nexit"
```

That works on some firmware, but it is **not guaranteed** that every model accepts a single multi-line
string, and it is hard to pinpoint failures. This project sends commands **line by line** (`loop`)
instead — the state is clear, it is easy to debug, and it is a common network-automation best practice.
If you know your firmware supports it, you can still switch back to the single multi-line form
(see approach B in the comments inside `configure_switch_simple.yml`).

One more note on `ansible_network_os`: the original `ansible.netcommon.generic` is not a valid value,
and the older generic `ansible.netcommon.default` is **no longer supported** on modern `ansible-core`
(it has no terminal plugin and fails with `network os ansible.netcommon.default is not supported`).
This project ships its own platform plugins in the `edgecore.edgecos` collection, so it sets
`ansible_network_os: edgecore.edgecos.edgecore` — that is what lets the generic `cli_command` / `cli_config`
modules drive Edge-core switches (prompt, enable, paging, and save are handled by those plugins).

---

## 10. Security: protect passwords with Ansible Vault

Do not put plaintext passwords in Git. Use Vault instead:

```bash
# Create an encrypted vars file
ansible-vault create inventory/group_vars/edgecore_switches_vault.yml
# Put inside:
#   ansible_password: "the real password"
#   ansible_become_password: "the real enable password"

# Supply the vault password when running
ansible-playbook site.yml --ask-vault-pass
```

Then keep only non-sensitive settings in `group_vars`, and let the vault file provide the secrets.

---

## 11. Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| Cannot connect / timeout | Confirm SSH reachability, firewall, correct `ansible_host`; increase `ansible_connect_timeout` |
| Stuck at password or enable | Check `ansible_password` / `ansible_become_password`; if `enable` has no password, leave it empty |
| Save hangs / times out | Saving can be slow, increase `ansible_command_timeout`; confirm `prompt/answer` matches the real prompt text |
| `% Invalid input` | CLI syntax differs on that model/firmware; compare with `?` on the device and adjust `config_lines.j2` |
| Config not applied | Confirm you entered `configure` mode and ended with `copy running-config startup-config` |

Use `-vvvv` to observe the actual CLI sent and the device responses:

```bash
ansible-playbook site.yml -vvvv
```

---

## 12. Examples

The [`examples/`](examples/) directory holds copy-and-adapt, variable-driven
playbooks derived from real customer deployments (sanitized — no real secrets or
IPs).

- [`examples/mlag/`](examples/mlag/) — provision **MLAG** on an Edge-core leaf
  pair. It uses this project's collection (`ansible_network_os:
  edgecore.edgecos.edgecore`) and sends CLI line by line via
  `ansible.netcommon.cli_command`, modeling the per-leaf uplink asymmetry in
  `host_vars`. See its [README](examples/mlag/README.md) for the sanitized
  topology, the variable→CLI mapping, and what to change.
- [`examples/vxlan-evpn/`](examples/vxlan-evpn/) — provision a 2-VTEP **VXLAN
  BGP-EVPN** fabric (L2 VNI + L3 VNI/VRF) on an Edge-core switch pair. Same
  conventions (collection network_os, line-by-line `cli_command`), modeling the
  per-switch peer-VTEP symmetry in `host_vars`. See its
  [README](examples/vxlan-evpn/README.md) for the sanitized topology, the
  variable→CLI mapping, and the 2-VTEP limitation note.

> MLAG and other feature CLI syntax can vary by switch model and firmware. Treat
> the device CLI guide and context-sensitive `?` help as the source of truth and
> adjust the example's templates if your model differs.

---

## 13. Delivering the collection to customers (no Galaxy required)

You do **not** need Ansible Galaxy to give a customer this collection.

**No build/compile step is required.** The plugins are plain Python (`plugins/terminal/edgecore.py`
and `plugins/cliconf/edgecore.py`); the `.py` source *is* the finished product. There is nothing to
compile — the customer never "builds" the plugins. The only thing that matters is that Ansible can
**find** the collection on disk and that `ansible_network_os` is set to the collection's FQCN
`edgecore.edgecos.edgecore` (already set in `inventory/group_vars/edgecore_switches.yml`).

### How Ansible finds the plugins

Ansible loads a collection from a *collections path* — a directory that contains an
`ansible_collections/<namespace>/<name>/` tree. In this project the collection lives at:

```
collection/ansible_collections/edgecore/edgecos/
```

so the collections path is the `collection/` directory. Point Ansible at it in any one of these
equivalent ways (highest precedence first):

```bash
# a) Environment variable (one-off, current shell)
export ANSIBLE_COLLECTIONS_PATH=/path/to/edgecore-ansible/collection
```

```ini
# b) ansible.cfg next to the playbooks (persistent, recommended for customers)
[defaults]
collections_paths = ./collection
```

```text
# c) Default location — install into ~/.ansible/collections (see Option 2 below)
```

Once Ansible can see the collection via any of these, setting
`ansible_network_os: edgecore.edgecos.edgecore` makes the generic `cli_command` / `cli_config`
modules use these plugins. Pick one of the three delivery paths below.

### Option 1 — Ship the whole project directory (simplest)

Hand the customer this entire project folder and point Ansible at the bundled `collection/` tree.
No build, no install step.

```bash
# One-off, in the shell:
export ANSIBLE_COLLECTIONS_PATH=/path/to/edgecore-ansible/collection
```

Or make it permanent in `ansible.cfg` next to the playbooks:

```ini
[defaults]
collections_paths = ./collection
```

Ansible then resolves `edgecore.edgecos.edgecore` straight from
`collection/ansible_collections/edgecore/edgecos/`.

### Option 2 — Build a tarball and have the customer install it

Build a single distributable artifact and let the customer install it into their own
collections path:

```bash
# You (the maintainer), from the collection directory:
cd collection/ansible_collections/edgecore/edgecos
ansible-galaxy collection build --force      # produces edgecore-edgecos-0.1.0.tar.gz

# The customer, on their control node:
ansible-galaxy collection install edgecore-edgecos-0.1.0.tar.gz
```

After install, `edgecore.edgecos.edgecore` is available system-wide (under
`~/.ansible/collections`) with no further configuration.

### Option 3 — Clone or unzip the repository

If the project lives in a Git repository or a zip archive, the customer can clone/unzip it and
use Option 1's `ANSIBLE_COLLECTIONS_PATH` / `collections_paths` setup against the checked-out
`collection/` tree. This is the same as Option 1 but sourced from version control.

In every case, confirm it works with the read-only smoke test:

```bash
ansible edgecore_switches -m ansible.netcommon.cli_command -a "command='show version'"
```

---

## 14. References

- Edge-core Enterprise Switch FAQ: <https://support.edge-core.com/hc/en-us/categories/360000061794-Enterprise-Switch-FAQs>
- `ansible.netcommon.cli_command` module docs: <https://docs.ansible.com/projects/ansible/latest/collections/ansible/netcommon/cli_command_module.html>
- `ansible.netcommon.network_cli` connection docs: <https://docs.ansible.com/projects/ansible/latest/collections/ansible/netcommon/network_cli_connection.html>

> The external information in this guide has been rephrased and summarized for compliance with licensing restrictions. Use your device's CLI Guide as the source of truth for actual commands.
