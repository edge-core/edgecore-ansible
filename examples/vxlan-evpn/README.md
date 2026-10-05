# VXLAN BGP-EVPN provisioning example (Edge-core Enterprise Switch VTEP pair)

A self-contained, variable-driven Ansible example you can copy and adapt to
provision a **2-VTEP VXLAN BGP-EVPN fabric** (an L2 VNI plus an L3 VNI/VRF) on a
pair of Edge-core Enterprise Switches (ECS series). It uses this project's own
collection (`ansible_network_os: edgecore.edgecos.edgecore`) and the generic
`ansible.netcommon.cli_command` module, and sends CLI line by line following the
same conventions as the rest of this project (and the sibling `examples/mlag/`).

Everything here is **placeholder data** for the management plane (RFC 5737 lab
IPs for `ansible_host`, generic names, no secrets). The data-plane addresses
(`19.19.19.x` / `17.17.17.x` / `20.20.20.x`) are kept from the real design as
illustrative example values. Change the variables to match your site.

> **DISRUPTIVE CHANGE.** Enabling VXLAN and BGP-EVPN reprograms forwarding and
> starts a BGP session. Run inside a **maintenance window** and preview with
> `--check` first.

> VXLAN / EVPN command syntax can vary by switch model and firmware. Treat your
> device's CLI guide and the context-sensitive `?` help as the source of truth;
> adjust the keywords in `templates/vxlan_config_lines.j2` if your model differs.

## What is VXLAN BGP-EVPN?

VXLAN (Virtual Extensible LAN) tunnels Layer-2 frames inside UDP/IP so two
switches can share VLANs across a routed **underlay**. Each switch is a **VTEP**
(VXLAN Tunnel Endpoint) identified by a source IP (here the SVI of underlay
`VLAN 20`). BGP-EVPN is the control plane that advertises MAC/IP reachability
between the VTEPs so they do not rely on flood-and-learn alone.

- **Underlay** — the plain routed network between the VTEPs (underlay `VLAN 20`,
  VTEP IPs `19.19.19.1` / `19.19.19.2`). This is what the tunnel rides on.
- **Overlay** — the tenant traffic carried inside the tunnel (the access VLANs
  and host subnets `17.17.17.0/24` / `20.20.20.0/24`).
- **L2 VNI (`2000`)** — bridges the access VLAN across the tunnel: a host on
  VLAN 10 behind Switch A shares a broadcast domain with hosts reached via the
  L2 VNI. Flooding to the remote VTEP is set with `flood r-vtep <peer>`.
- **L3 VNI (`3000`, VRF `even`)** — provides routing *between* subnets across
  the fabric. It floods via `protocol bgp-evpn`, i.e. reachability is learned
  from the EVPN control plane rather than a static remote-VTEP list.

## Topology (sanitized)

```
   [Host C]                                                   [Host D]
   17.17.17.2                                                 20.20.20.2
      │ VLAN 10                                                  │ VLAN 30
      │ (VRF: even)                                              │ (VRF: even)
      │                                                          │
 +------------+                                            +------------+
 |  SWITCH A  |===== VXLAN Tunnel (underlay VLAN 20) ======|  SWITCH B  |
 |  (vtep_a)  |                                            |  (vtep_b)  |
 +------------+                                            +------------+
  VTEP: 19.19.19.1                                          VTEP: 19.19.19.2
  L2 VNI 2000 (VLAN 10)                                     L2 VNI 2000 (VLAN 30)
  L3 VNI 3000 (VRF even)                                    L3 VNI 3000 (VRF even)
```

- **Underlay VLAN 20** carries the VTEP source IPs (`19.19.19.1` / `19.19.19.2`).
- **L2 VNI 2000** bridges each switch's access VLAN (10 on A, 30 on B) over the
  tunnel; the remote flood target (`r-vtep`) is the peer's VTEP IP.
- **L3 VNI 3000** in **VRF `even`** routes between the subnets via BGP-EVPN
  (iBGP, both switches in ASN `65100`).
- Access port **`ethernet 1/1`** on each switch is the customer-facing port
  mapped into the L2 VNI.

### Per-switch symmetry (important)

The two switches are symmetric; only four values differ per switch. The key
idea is that **`remote_vtep_ip` is always the *peer's* VTEP IP** — it is used
*both* as the L2 VNI flood target (`r-vtep`) *and* as the BGP-EVPN neighbor.

| Variable | `vtep_a` (Switch A) | `vtep_b` (Switch B) |
|----------|---------------------|---------------------|
| `vtep_ip` (underlay SVI) | `19.19.19.1` | `19.19.19.2` |
| `access_vlan` | `10` | `30` |
| `access_svi_ip` | `17.17.17.1 255.255.255.0` | `20.20.20.1 255.255.255.0` |
| `remote_vtep_ip` (= peer VTEP) | `19.19.19.2` | `19.19.19.1` |

Everything else (underlay VLAN, L2/L3 VNIs, VRF, BGP ASN, access port, save
toggle) is shared in `group_vars/vxlan_vteps.yml`.

## Management IP vs data-plane IP

Keep these two planes clearly separate:

- **Management IP** — `ansible_host` in `inventory.yml` (`192.0.2.11` /
  `192.0.2.12`, RFC 5737 placeholders). This is the out-of-band address Ansible
  SSHes to. **Replace it** with your switches' real management addresses.
- **Data-plane IPs** — the VTEP/underlay/overlay addresses (`19.19.19.x`,
  `17.17.17.x`, `20.20.20.x`) configured *by* the playbook via `host_vars`.
  These come from the real design and serve as example values; adapt them to
  your addressing plan.

## Files

| File | Purpose |
|------|---------|
| `inventory.yml` | The VTEP pair (`vtep_a`, `vtep_b`) with placeholder mgmt IPs. |
| `ansible.cfg` | Points `collections_paths` at the bundled collection. |
| `group_vars/vxlan_vteps.yml` | Connection settings + shared VXLAN/EVPN model (underlay VLAN, L2/L3 VNI, VRF, ASN, access port). |
| `host_vars/vtep_a.yml` | Switch A per-host data (VTEP IP, access VLAN/SVI, peer VTEP). |
| `host_vars/vtep_b.yml` | Switch B per-host data (symmetric; peer VTEP swapped). |
| `templates/vxlan_config_lines.j2` | Renders the CLI from the variables. |
| `site.yml` | Playbook: pre-check → render → apply line by line → save. |

## Variable → CLI mapping

| Variable | Generated CLI |
|----------|---------------|
| `underlay_vlan`, `access_vlan` | `vlan database` / `vlan <underlay>` / `vlan <access>` / `exit` |
| `access_vlan`, `access_svi_ip` | `interface vlan <access>` / `ip address <access_svi_ip>` / `exit` |
| `underlay_vlan`, `vtep_ip` | `interface vlan <underlay>` / `ip address <vtep_ip> 255.255.255.0` / `exit` |
| `access_port`, `access_vlan` | `interface <access_port>` / `switchport allow vlan add <access> untagged` / `switchport native vlan <access>` / `exit` |
| `vrf`, `access_vlan` | `ip vrf <vrf>` / `ip vrf bind <vrf> <access>` |
| `underlay_vlan` | `vxlan source-interface vlan <underlay>` |
| `l2_vni`, `access_port`, `remote_vtep_ip` | `vxlan vni <l2_vni>` / `vxlan vni <l2_vni> access-port interface <access_port>` / `vxlan vni <l2_vni> flood r-vtep <remote_vtep_ip>` |
| `l3_vni`, `vrf` | `vxlan vni <l3_vni>` / `vxlan vni <l3_vni> vrf <vrf>` / `vxlan vni <l3_vni> flood protocol bgp-evpn` |
| `bgp_asn`, `remote_vtep_ip` | `router bgp <asn>` / `neighbor <remote_vtep_ip> remote-as <asn>` / `l2vpn evpn advertise-all-vni` / `l2vpn evpn neighbor <remote_vtep_ip> activate` |
| `bgp_asn`, `vrf` | `router bgp <asn> vrf <vrf>` / `redistribute connected` / `l2vpn evpn advertise ipv4 unicast` |
| `vxlan_save_config` | `copy running-config startup-config` (with auto `[y/n]` answer) |

> The source running-config contains lone `!` lines as stanza separators. Those
> are not real config commands, so `templates/vxlan_config_lines.j2` **omits all
> bare `!` lines**; the playbook sends only real configuration commands.

## Limitations

This example covers the **2-VTEP** case shown in the topology: each switch has
exactly one remote peer, so a single `remote_vtep_ip` doubles as the L2 VNI
`flood r-vtep` target and the single BGP-EVPN neighbor.

For **more than two VTEPs** this 1:1 model does not scale as-is:

- The L2 VNI `flood r-vtep <peer>` needs **one entry per remote VTEP** (a full
  mesh of head-end replication targets).
- BGP-EVPN needs a **neighbor per peer** (full mesh) or, more practically, a
  **route-reflector** so each VTEP peers only with the RR.

To extend the example, turn `remote_vtep_ip` into a *list* of peers and loop the
`flood r-vtep` / `neighbor` lines in the template, or point all VTEPs at a route
reflector. That is left as an exercise — this example intentionally keeps the
two-VTEP shape it was derived from.

## What you must change to use this

1. **`inventory.yml`** — set `ansible_host` for each switch to its real
   **management** IP.
2. **`group_vars/vxlan_vteps.yml`** — set `ansible_user` / `ansible_password` /
   `ansible_become_password` (prefer **Ansible Vault**, see the main README
   Security section), and adjust the shared model (`underlay_vlan`, `l2_vni`,
   `l3_vni`, `vrf`, `bgp_asn`, `access_port`) as needed.
3. **`host_vars/vtep_a.yml` / `host_vars/vtep_b.yml`** — set each switch's
   `vtep_ip`, `access_vlan`, `access_svi_ip`, and `remote_vtep_ip` (the peer's
   VTEP). Confirm the two `remote_vtep_ip` values point at each other.

## Prerequisites and collection setup

See the main project [README](../../README.md) for prerequisites (Python venv,
`ansible-core`, `ansible.netcommon`) and for how Ansible finds the
`edgecore.edgecos` collection and `ansible_network_os`. This example's
`ansible.cfg` already points `collections_paths` at the bundled `collection/`
directory, so running from this folder works out of the box within the repo.

## How to run

From this directory (`examples/vxlan-evpn/`):

```bash
# 1) Syntax check (no device needed)
ansible-playbook site.yml --syntax-check

# 2) Preview the rendered CLI without changing anything
#    (reads run; connection to placeholder IPs will fail until you set real ones)
ansible-playbook site.yml --check --diff -vvv

# 3) Apply for real once inventory IPs and credentials are set
#    (DISRUPTIVE -- maintenance window)
ansible-playbook site.yml
```

The playbook applies in order: VLAN database → access SVI + underlay (VTEP)
SVI → access port → VRF create/bind → VXLAN source + L2 VNI + L3 VNI → BGP-EVPN
peering → `router bgp ... vrf` route handling → save.
