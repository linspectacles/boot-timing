# Resource Monitor

**Expose. Explore. Explain.**

Resource Monitor is a read-only live CPU, memory, disk and network monitor with Linux-native detail views, optional helper-backed visibility, a configurable Overview and a parallel TUI.

Current release: **1.0.7**

Repository: <https://github.com/linspectacles/linux-resmon>

<p align="center">
  <a href="https://github.com/brunonlinespace/brunonlinespace/blob/main/linspectacles/linux-resmon.png">
    <img
      src="https://raw.githubusercontent.com/brunonlinespace/brunonlinespace/main/linspectacles/linux-resmon.png"
      alt="Resource Monitor screenshot"
      width="900"
    >
  </a>
</p>

## What Resource Monitor is

Resource Monitor answers a focused question: **what resources are active right now, which processes/services/sockets are involved, and what does Linux report between refresh samples?**

Resource Monitor is inspired in part by the **Windows Resource Monitor (`resmon.exe`)**, especially its clear CPU / Memory / Disk / Network organisation. It is not intended as a clone: LinSpectacles keeps the implementation Linux-native, using Linux data sources and terminology rather than translating Linux behaviour into Windows concepts.

Its design was also informed by several **Microsoft Sysinternals** utilities: **Process Explorer** for process/service context, **Handle / ListDLLs** for associated handles and mapped modules, **TCPView** for socket-oriented network inspection, and **RAMMap / VMMap** for deeper memory views. Those ideas are adapted to Linux-native interfaces and semantics rather than reproduced one-for-one.

The applet reports information available from its documented Linux sources. Data that is unavailable, restricted, or not reported by those sources remains explicitly unavailable rather than being inferred.

## Highlights

- Movable/persisted resource tabs for **CPU, Memory, Disk and Network** plus a configurable Overview.
- CPU views for processes, systemd services, associated file handles and mapped modules/files.
- Memory views for process inventory, lazy selected-process `smaps_rollup` / `smaps` detail, and Linux-native physical-memory / VM activity information.
- Disk views based on process I/O, per-device counters, mounted usage and sysfs in-flight I/O where reported.
- Network views for process-owned sockets, per-interface activity, TCP connections, UDP endpoints and listening/bound ports.
- Whole-service CPU deltas use reported systemd cgroups where available, with MainPID process information as a fallback.
- Optional helper adds narrow read-only visibility for process descriptors/maps, selected-process memory maps and system socket data; the GUI/TUI itself is never elevated.
- A parallel TUI uses the same broad resource model without the GUI Overview page.

## Data sources and acquisition

- `psutil` for process, disk and network counters/inventories used by the applet.
- `/proc/<pid>/fd`, `/proc/<pid>/smaps_rollup`, `/proc/<pid>/smaps`, `/proc/meminfo` and `/proc/vmstat`.
- `systemctl` plus `/sys/fs/cgroup/<ControlGroup>/cpu.stat` for the services view.
- `/sys/class/block/<device>/stat` where current in-flight I/O is exposed.
- Optional helper data from `/proc/net/{tcp,tcp6,udp,udp6}` and fixed per-process procfs operations.

The applet uses those sources according to the acquisition paths implemented in this release. Optional tools or privileged helpers only affect the views/actions that explicitly use them; they are not treated as silent substitutes for unrelated sources.

## Interface

Resource Monitor follows the LinSpectacles inventory + **Metadata Details** pattern where applicable: an acquired inventory remains separate from the details for the selected record, and search/filter controls operate on the data the applet has actually collected.

The applet's **Options** surface provides the presentation/source/about controls implemented by this release, together with export controls where present in the source. Applet-specific actions remain explicit rather than being folded into background collection.

## Read-only and scope boundaries

Rate values are interval measurements derived from successive counters. Privileged network visibility is additive rather than a replacement for ordinary-visible sockets. Memory classes are Linux-native counters and are not presented as a partition that must sum to total RAM. Resource Monitor does not write to the inspected procfs/sysfs/systemd interfaces.

## Useful keyboard shortcuts

| Command | Shortcut |
| --- | --- |
| Options | `Ctrl+/` |
| Toggle Overview Quadrants / Strips while unlocked | `Ctrl+L` |
| Toggle Lock Layout | `Ctrl+Shift+L` |

## Running from source

The supplied source is directly runnable on Linux. The Python-side requirements are:

- Python 3.
- PyQt6 for the graphical interface.
- `psutil` for the live resource collectors.

Create a local virtual environment if you do not already have the required Python packages in the environment you want to use:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install PyQt6 psutil
python3 linspectacles_linux_resmon/standalone.py
```

Linux commands, procfs/sysfs interfaces, system services, or optional helpers mentioned in **Data sources and acquisition** are applet-specific runtime inputs. Data that is unavailable, restricted, or not reported by those sources remains explicitly unavailable rather than being inferred.

No RPM installation instructions are included in this README.

## LinSpectacles Hub

This applet can run independently, but it can also be installed and used inside **[LinSpectacles Hub](https://github.com/linspectacles/linspectacles-hub)**.

LinSpectacles Hub is the optional workbench for the LinSpectacles applet family. It provides shared applet discovery, navigation and management while each inspector remains independently runnable.

To install a portable or user applet through the Hub, open **Configuration... → Applets** and add the applet ZIP. Once discovered, the applet can be enabled and opened from the Hub navigation.

System-installed applets are discovered by the Hub from its system applet store and remain managed by the system package manager.

## Source layout and LinSpectacles integration

The applet source is contained in:

```text
linspectacles_linux_resmon/
├── README.md
├── LICENSE
├── __init__.py
├── applet.json
├── standalone.py
├── standalone_tui.py
└── linux_resmon/
    ├── applet.py
    ├── tui_applet.py
    ├── privilege.py
    ├── privileged/
    ├── icon.png
    ├── README.md
    ├── CHANGELOG.md
    └── ... applet-specific modules where present
```

`applet.json` defines the applet's LinSpectacles identity and integration metadata. `standalone.py` provides direct standalone launching, while the applet entrypoint allows the same inspector to run inside LinSpectacles Hub.

## Configuration

Presentation and inspection preferences are persisted only through the settings mechanisms already implemented by the applet. Persisted UI state does not grant the applet permission to modify the inspected Linux subsystem.

## Scope

Resource Monitor is intentionally specialist. Related Linux information that belongs to another LinSpectacles subsystem remains outside this applet rather than being inferred or duplicated here.

## License

GNU General Public License v3.0 or later. See [`LICENSE`](LICENSE).

## Links

- LinSpectacles organisation: <https://github.com/linspectacles/>
- LinSpectacles Hub: <https://github.com/linspectacles/linspectacles-hub>
- Repository: <https://github.com/linspectacles/linux-resmon>
- Issues: <https://github.com/linspectacles/linux-resmon/issues>

<p align="center">
  <a href="https://github.com/linspectacles/linux-resmon">
    <img
      src="linux_resmon/icon.png"
      alt="Resource Monitor"
      width="256"
    >
  </a>
</p>
