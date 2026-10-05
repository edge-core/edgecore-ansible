# Read-only running-config backup example (Edge-core Enterprise Switch)

A self-contained, variable-driven Ansible example you can copy and adapt to
**back up the full running-config of a group of Edge-core Enterprise Switches
without changing anything on them**. For every switch in the inventory group it
runs `show running-config` and saves the raw output **verbatim** to a
timestamped per-host **`.cfg`** file.

All files are written **locally on the control node** (under `./output/` by
default). It uses this project's own collection
(`ansible_network_os: edgecore.edgecos.edgecore`) and the generic
`ansible.netcommon.cli_command` module, following the same conventions as the
sibling `examples/facts-audit/`, `examples/mlag/`, and `examples/vxlan-evpn/`.

> **STRICTLY READ-ONLY.** Every device command is a `show` command with
> `changed_when: false`. There is **no** `configure`, **no**
> `copy running-config startup-config`, and **no** change of any kind. This
> example never modifies a device, so it is safe to run against production.

## Snapshot backup, not live monitoring

Ansible is a **pull/snapshot** tool: this playbook connects, runs
`show running-config`, and writes what it saw at that moment. That is exactly
what you want for a config backup, a compliance archive, or a pre/post-change
diff.

It is **not** a monitoring system. For continuous, real-time visibility (alerts
when a config changes) use SNMP, streaming telemetry, or gNMI dial-out into a
time-series/monitoring stack. Think of this example as "take a photo", not
"watch the live feed".

## What it produces

One timestamped file per host:

```
<host>_running-config_<ts>.cfg
```

`<host>` is the inventory hostname and `<ts>` is one run-wide timestamp
(`YYYYmmdd-HHMMSS`) shared by every host in a single run. The `.cfg` is the raw
`show running-config` output saved verbatim (no parsing), so it is a faithful
snapshot of the device config.

With the default `backup_output_dir: "./output"`, a run against two switches
produces something like:

```
output/
├── edgecore_sw01_running-config_20250105-120000.cfg
└── edgecore_sw02_running-config_20250105-120000.cfg
```

## Use cases

- **Compliance / rollback reference** — keep timestamped snapshots of each
  device's full config to satisfy audits or to restore known-good settings.
- **Diff successive backups** — compare today's `.cfg` with yesterday's to see
  exactly what changed on a device.
- **Before/after a provisioning run** — snapshot the config before and after
  running the `mlag/` or `vxlan-evpn/` example to verify what was applied.

## Security: the `.cfg` files are sensitive

> **A running-config backup can contain real device secrets.** A
> `show running-config` dump may include enable-password hashes
> (e.g. `password 7 ...`), SNMP community strings, RADIUS/TACACS keys, and real
> management IPs. Treat every `.cfg` under `output/` as sensitive:
>
> - `output/` is **gitignored** on purpose — do not commit the `.cfg` files,
>   paste them into tickets, or share them casually.
> - Backups are written with **`mode 0600`** (owner read/write only).
> - If you must archive backups, put them somewhere access-controlled.

This repo ships **no** real backups — `output/` holds only a `.gitkeep`
placeholder, and the inventory/credentials are placeholders (RFC 5737
`192.0.2.x` IPs, `admin` / `YourPassword`).

> Running-config format can vary by switch **model and firmware**, but the
> backup is unaffected because it is saved verbatim.

## What you must change to use this

1. **`inventory.yml`** — set `ansible_host` for each switch to its real
   **management** IP, and add/remove hosts in the `edgecore_switches` group.
2. **`group_vars/edgecore_switches.yml`** — set `ansible_user` /
   `ansible_password` / `ansible_become_password` (prefer **Ansible Vault**, see
   the main README Security section). Optionally change `backup_output_dir`.

## Prerequisites and collection setup

See the main project [README](../../README.md) for prerequisites (Python venv,
`ansible-core`, `ansible.netcommon`) and for how Ansible finds the
`edgecore.edgecos` collection and `ansible_network_os`. This example's
`ansible.cfg` already points `collections_paths` at the bundled `collection/`
directory, so running from this folder works out of the box within the repo.

## How to run

From this directory (`examples/config-backup/`):

```bash
# 1) Syntax check (no device needed)
ansible-playbook site.yml --syntax-check

# 2) Back up the WHOLE group once inventory IPs and credentials are set
ansible-playbook site.yml

# 3) Back up a SINGLE host
ansible-playbook site.yml --limit edgecore_sw01
```

Because every task is read-only, running `site.yml` against real switches only
reads from them and writes the resulting `.cfg` files locally under `output/`.
