"""
Week 6 — Nmap scanning and result parsing.

Wraps the nmap binary and turns its XML output into a flat structure the rest
of the pipeline can reason about, so the LLM analyst never has to parse XML.

Scanning hosts you do not own or have permission to test is illegal in most
jurisdictions. This module therefore refuses to scan anything outside
ALLOWED_TARGETS unless the caller explicitly asserts authorisation.
"""

from __future__ import annotations

import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime

# scanme.nmap.org is published by the Nmap project expressly for scan testing;
# the loopback entries are the user's own machine.
ALLOWED_TARGETS = {
    "scanme.nmap.org",
    "localhost",
    "127.0.0.1",
    "::1",
}

PROFILES = {
    # -sT (TCP connect) and -sV (version detection) both work unprivileged.
    # -O / -sS are deliberately absent: they need root, and a deliverable that
    # demands sudo is a deliverable nobody runs.
    "quick":    ["-sT", "-sV", "-F"],
    "standard": ["-sT", "-sV", "--top-ports", "200"],
    "deep":     ["-sT", "-sV", "-sC", "-p-"],
}


class ScanError(RuntimeError):
    pass


def check_authorised(target: str, asserted: bool) -> None:
    """Blocks scans of third-party hosts unless the caller vouches for them."""
    if target in ALLOWED_TARGETS or asserted:
        return
    raise ScanError(
        f"Refusing to scan '{target}'.\n"
        f"Built-in safe targets: {', '.join(sorted(ALLOWED_TARGETS))}.\n"
        "To scan a host you own or are authorised to test, re-run with "
        "--authorised."
    )


def run_nmap(target: str, profile: str = "quick", out_xml: str = "scan.xml",
             timeout: int = 600) -> str:
    """Runs nmap against `target` and returns the XML it produced."""
    if shutil.which("nmap") is None:
        raise ScanError("nmap is not installed — `brew install nmap`")
    if profile not in PROFILES:
        raise ScanError(f"unknown profile '{profile}' (have: {', '.join(PROFILES)})")

    cmd = ["nmap", *PROFILES[profile], "-oX", out_xml, target]
    print(f"  $ {' '.join(cmd)}")

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ScanError(f"nmap timed out after {timeout}s") from exc

    if proc.returncode != 0:
        raise ScanError(f"nmap exited {proc.returncode}: {proc.stderr.strip()}")

    with open(out_xml, encoding="utf-8") as f:
        return f.read()


def _service_of(port_el: ET.Element) -> dict:
    svc = port_el.find("service")
    if svc is None:
        return {"name": "unknown", "product": "", "version": "", "extra": ""}
    return {
        "name": svc.get("name", "unknown"),
        "product": svc.get("product", ""),
        "version": svc.get("version", ""),
        "extra": svc.get("extrainfo", ""),
    }


def parse_scan(xml_text: str) -> dict:
    """Flattens nmap XML into {scan metadata, hosts[{addresses, ports[...]}]}."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ScanError(f"could not parse nmap XML: {exc}") from exc

    hosts = []
    for host_el in root.findall("host"):
        status = host_el.find("status")
        if status is not None and status.get("state") != "up":
            continue

        addresses = [
            a.get("addr", "") for a in host_el.findall("address")
            if a.get("addrtype") in ("ipv4", "ipv6")
        ]
        hostnames = [h.get("name", "") for h in host_el.findall("hostnames/hostname")]

        ports = []
        for port_el in host_el.findall("ports/port"):
            state_el = port_el.find("state")
            state = state_el.get("state", "unknown") if state_el is not None else "unknown"
            if state != "open":
                continue
            ports.append({
                "port": int(port_el.get("portid", 0)),
                "protocol": port_el.get("protocol", "tcp"),
                "state": state,
                **_service_of(port_el),
                "scripts": [
                    {"id": s.get("id", ""), "output": (s.get("output") or "").strip()}
                    for s in port_el.findall("script")
                ],
            })

        ports.sort(key=lambda p: p["port"])
        hosts.append({
            "addresses": addresses,
            "hostnames": [h for h in hostnames if h],
            "label": (hostnames[0] if hostnames else (addresses[0] if addresses else "unknown")),
            "open_ports": ports,
        })

    run = root.find("runstats/finished")
    return {
        "scanned_at": datetime.now().isoformat(timespec="seconds"),
        "nmap_args": root.get("args", ""),
        "elapsed": float(run.get("elapsed", 0)) if run is not None else 0.0,
        "host_count": len(hosts),
        "hosts": hosts,
    }


def summarise(scan: dict) -> str:
    """A short human-readable digest of a parsed scan."""
    lines = [f"{scan['host_count']} host(s) up · {scan['elapsed']:.1f}s"]
    for host in scan["hosts"]:
        lines.append(f"  {host['label']} ({', '.join(host['addresses'])}) — "
                     f"{len(host['open_ports'])} open port(s)")
        for p in host["open_ports"]:
            version = " ".join(x for x in (p["product"], p["version"]) if x)
            lines.append(f"    {p['port']:>6}/{p['protocol']:<4} {p['name']:<14}"
                         f"{version}")
    return "\n".join(lines)
