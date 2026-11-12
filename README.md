<p align="center">
  <a href="https://github.com/brunonlinespace/brunonlinespace/blob/main/linspectacles/boot-timing.png">
    <img
      src="https://raw.githubusercontent.com/brunonlinespace/brunonlinespace/main/linspectacles/boot-timing.png"
      alt="Boot Timing screenshot"
      width="900"
    >
  </a>
</p>

# Boot Timing

**Expose. Explore. Explain.**

Boot Timing is a read-only systemd boot-timing inspector for boot-wide timing, per-unit durations and explicit critical-path analysis.

Current release: **0.0.10**

Repository: <https://github.com/linspectacles/boot-timing>

## What Boot Timing is

Boot Timing answers a focused question: **how long did the current systemd boot take, which units consumed time, and what timing path does systemd report?**

It keeps acquisition and interpretation close to the Linux interfaces actually used by the applet. When a source is unavailable, restricted, or does not report a field, the README does not imply that the applet can manufacture the missing information.

## Highlights

- Boot summary from `systemd-analyze time`.
- Per-unit durations from `systemd-analyze blame`, categorized mechanically by unit-name suffix.
- Global critical chain in **Overall Timing...**.
- Selected-unit **Unit Critical Path...** acquired only when requested.
- Boot phases and milestones derived from systemd-reported monotonic timing properties.
- **Boot Log** supporting view for `/var/log/boot.log`, with explicit privileged read access only when the exact file exists but ordinary access is denied.

## Data sources and acquisition

- `systemd-analyze --no-pager time`.
- `systemd-analyze --no-pager blame`.
- `systemd-analyze --no-pager critical-chain` and selected-unit critical-chain queries.
- `systemctl show <target-or-unit>` for reported timing properties.
- `/var/log/boot.log` as a separate supporting view.

The applet uses those sources according to the acquisition paths implemented in this release. Optional tools or privileged helpers only affect the views/actions that explicitly use them; they are not treated as silent substitutes for unrelated sources.

## Interface

Boot Timing follows the LinSpectacles inventory + **Metadata Details** pattern where applicable: an acquired inventory remains separate from the details for the selected record, and search/filter controls operate on the data the applet has actually collected.

The applet's **Options** surface provides the presentation/source/about controls implemented by this release, together with export controls where present in the source. Applet-specific actions remain explicit rather than being folded into background collection.

## Read-only and scope boundaries

Boot Timing does not start, stop, enable, disable or restart units and does not modify boot configuration. The Boot Log is supporting evidence, not another timing data source, and privileged access is limited to reading that exact file.

## Useful keyboard shortcuts

| Command | Shortcut |
| --- | --- |
| Show / hide Metadata Details | `F3` |
| Toggle Horizontal / Vertical details | `Ctrl+L` |
| Repeat current scan | `Shift+F5` |
| Boot-log privileged access where offered | `F4` |
| Options | `Ctrl+/` |

## Running from source

The supplied source is directly runnable on Linux. The Python-side requirements are:

- Python 3.
- PyQt6 for the graphical interface.

Create a local virtual environment if you do not already have the required Python packages in the environment you want to use:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install PyQt6
python3 linspectacles_boot_timing/standalone.py
```

Linux commands, procfs/sysfs interfaces, system services, or optional helpers mentioned in **Data sources and acquisition** are applet-specific runtime inputs. A missing optional source is handled by the applet's existing availability/error path; it is not replaced here with an invented dependency or capability.

No RPM installation instructions are included in this README.

## Source layout and LinSpectacles integration

The applet source is contained in:

```text
linspectacles_boot_timing/
├── __init__.py
├── applet.json
├── standalone.py
├── README.md
├── LICENSE
└── boot_timing/
    ├── __init__.py
    ├── applet.py
    ├── _support.py
    └── icon.png
```

`applet.json` supplies the LinSpectacles applet identity and entrypoint metadata. `standalone.py` launches the applet directly, while the package's applet factory provides the host-loadable LinSpectacles integration used by the source.

## Configuration

Presentation and inspection preferences are persisted only through the settings mechanisms already implemented by the applet. Persisted UI state does not grant the applet permission to modify the inspected Linux subsystem.

## Scope

Boot Timing is intentionally specialist. Related Linux information that belongs to another LinSpectacles subsystem remains outside this applet rather than being inferred or duplicated here.

## License

GNU General Public License v3.0 or later. See [`LICENSE`](LICENSE).

## Links

- LinSpectacles organisation: <https://github.com/linspectacles/>
- Repository: <https://github.com/linspectacles/boot-timing>
- Issues: <https://github.com/linspectacles/boot-timing/issues>

<p align="center">
  <a href="https://github.com/linspectacles/boot-timing">
    <img
      src="boot_timing/icon.png"
      alt="Boot Timing"
      width="256"
    >
  </a>
</p>
