# Read-only fact-collection example (Edge-core Enterprise Switch audit)

A self-contained, variable-driven Ansible example you can copy and adapt to
**collect facts from a group of Edge-core Enterprise Switches without changing
anything on them**. For every switch in the inventory group it runs
`show mac-address-table` and `show arp`, parses the raw text into structured
records, and writes a timestamped per-host **JSON + CSV** for each table.

> To back up full device configs, see
> [`examples/config-backup/`](../config-backup/).

All files are written **locally on the control node** (under `./output/` by
default). It uses this project's own collection
(`ansible_network_os: edgecore.edgecos.edgecore`) and the generic
`ansible.netcommon.cli_command` module, following the same conventions as the
sibling `examples/mlag/` and `examples/vxlan-evpn/`.

> **STRICTLY READ-ONLY.** Every device command is a `show` command with
> `changed_when: false`. There is **no** `configure`, **no**
> `copy running-config startup-config`, and **no** change of any kind. This
> example never modifies a device, so it is safe to run against production.

## Snapshot audit, not live monitoring

Ansible is a **pull/snapshot** tool: this playbook connects, runs a few `show`
commands, and writes what it saw at that moment. That is exactly what you want
for an audit, an inventory, or a pre/post-change diff. (For a full-config
backup snapshot, see the sibling [`examples/config-backup/`](../config-backup/).)

It is **not** a monitoring system. For continuous, real-time visibility (alerts
when a MAC moves, a port flaps, or a neighbor drops) use SNMP, streaming
telemetry, or gNMI dial-out into a time-series/monitoring stack. Think of this
example as "take a photo", not "watch the live feed".

## The two tables

| Collection | Command | Output files (per host) |
|------------|---------|--------------------------|
| MAC address table | `show mac-address-table` | `<host>_mac_<ts>.json`, `<host>_mac_<ts>.csv` |
| ARP table | `show arp` | `<host>_arp_<ts>.json`, `<host>_arp_<ts>.csv` |

`<host>` is the inventory hostname and `<ts>` is one run-wide timestamp
(`YYYYmmdd-HHMMSS`) shared by every host in a single run.

### Parsed record schemas

- **MAC** — array of `{ interface, mac, vlan, type, life_time }`
- **ARP** — array of `{ ip, mac, type, interface }`

Example (`edgecore_sw01_mac_20250105-120000.json`):

```json
[
  { "interface": "CPU", "mac": "00-E0-0C-00-00-FD", "vlan": "1", "type": "CPU", "life_time": "Delete on Reset" },
  { "interface": "Eth 1/ 1", "mac": "00-90-9E-9D-A0-3A", "vlan": "1", "type": "Learn", "life_time": "Delete on Timeout" }
]
```

## Parsing approach (dependency-free)

The CLI tables are parsed with plain Jinja2 `regex_findall` (Python `re`,
`(?m)` multiline) — **no** `ntc-templates`, TextFSM, or pyATS, so there are no
extra dependencies to install. `regex_findall` with multiple capture groups
returns a list of tuples (one per matched row); the playbook turns each tuple
into a dict with a small `set_fact` loop.

The two regexes live in **one place** — `group_vars/edgecore_switches.yml`
(`facts_mac_regex`, `facts_arp_regex`) — and the offline self-test
(`tests/parse_selftest.yml`) uses the identical expressions, so the play and the
test can never silently drift.

The MAC regex deliberately captures the interface non-greedily so it tolerates
the embedded space Edge-core prints for some ports (e.g. `Eth 1/ 1`), and
captures the trailing life-time text as a whole (`Delete on Reset` /
`Delete on Timeout`). The ARP regex anchors on a dotted-quad IP, so the
`ARP Cache Timeout` header, the column header, the dashes line, and the
`Total entry : N` footer are all skipped automatically.

### Adapting the regexes if a firmware's columns differ

Table layouts can vary by model and firmware. If your switch prints different or
extra columns:

1. Capture a real `show mac-address-table` / `show arp` sample.
2. Edit `facts_mac_regex` / `facts_arp_regex` in
   `group_vars/edgecore_switches.yml`, keeping the **capture-group order** the
   play expects (MAC: interface, mac, vlan, type, life_time; ARP: ip, mac, type,
   interface). Widen or narrow individual groups to match the new spacing.
3. Paste your sample into `tests/parse_selftest.yml` and update the asserts,
   then run the self-test (below) until it passes — no device needed.

## Files

| File | Purpose |
|------|---------|
| `inventory.yml` | The switch group `edgecore_switches` with placeholder mgmt IPs. |
| `ansible.cfg` | Points `collections_paths` at the bundled collection. |
| `group_vars/edgecore_switches.yml` | Connection settings, `facts_output_dir`, and the shared parsing regexes. |
| `site.yml` | Read-only play: collect → parse → write JSON/CSV. |
| `templates/mac_table.csv.j2` | Dependency-free CSV renderer for the MAC table. |
| `templates/arp_table.csv.j2` | Dependency-free CSV renderer for the ARP table. |
| `tests/parse_selftest.yml` | Offline self-test of the parsing (localhost, no device). |
| `output/` | Where collected files are written (gitignored; keeps `.gitkeep`). |

## Output file layout

With the default `facts_output_dir: "./output"`, a run against two switches
produces something like:

```
output/
├── edgecore_sw01_mac_20250105-120000.json
├── edgecore_sw01_mac_20250105-120000.csv
├── edgecore_sw01_arp_20250105-120000.json
├── edgecore_sw01_arp_20250105-120000.csv
├── edgecore_sw02_mac_20250105-120000.json
├── edgecore_sw02_mac_20250105-120000.csv
├── edgecore_sw02_arp_20250105-120000.json
└── edgecore_sw02_arp_20250105-120000.csv
```

## Sensitivity of collected data

> **Collected files may expose real topology.** The MAC/ARP outputs reveal real
> host MAC/IP addresses, the ports and VLANs they are learned on, and the
> management IPs of your switches. Treat everything under `output/` as
> sensitive: it is **gitignored** on purpose. Do not commit it, paste it into
> tickets, or share it casually. If you must archive the data, put it somewhere
> access-controlled.

This repo ships **no** real collected data — only placeholder credentials and
RFC 5737 (`192.0.2.x`) management IPs.

## Use cases

- **Audit / inventory** — snapshot which MACs and IPs each switch currently
  sees, on which port and VLAN.
- **Troubleshooting** — find which physical port and VLAN a given MAC is learned
  on, or confirm an ARP binding for a host IP.
- **Post-provision verification** — after running the `mlag/` or `vxlan-evpn/`
  example, confirm the result: e.g. that the expected VXLAN/EVPN **learned MACs**
  show up in the MAC table and ARP bindings resolve across the fabric.

## What you must change to use this

1. **`inventory.yml`** — set `ansible_host` for each switch to its real
   **management** IP, and add/remove hosts in the `edgecore_switches` group.
2. **`group_vars/edgecore_switches.yml`** — set `ansible_user` /
   `ansible_password` / `ansible_become_password` (prefer **Ansible Vault**, see
   the main README Security section). Optionally change `facts_output_dir`.

## Model / firmware caveat

Table formats can vary by switch model and firmware. If a collection looks
wrong, capture a real sample and adjust the regexes as described above.

## Prerequisites and collection setup

See the main project [README](../../README.md) for prerequisites (Python venv,
`ansible-core`, `ansible.netcommon`) and for how Ansible finds the
`edgecore.edgecos` collection and `ansible_network_os`. This example's
`ansible.cfg` already points `collections_paths` at the bundled `collection/`
directory, so running from this folder works out of the box within the repo.

## How to run

From this directory (`examples/facts-audit/`):

```bash
# 1) Syntax check (no device needed)
ansible-playbook site.yml --syntax-check

# 2) Prove the parsing offline (no device, no inventory needed)
ansible-playbook tests/parse_selftest.yml

# 3) Collect from the WHOLE group once inventory IPs and credentials are set
ansible-playbook site.yml

# 4) Collect from a SINGLE host
ansible-playbook site.yml --limit edgecore_sw01
```

Because every task is read-only, running `site.yml` against real switches only
reads from them and writes the resulting files locally under `output/`.
