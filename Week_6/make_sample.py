"""Builds a synthetic nmap XML fixture for demonstrating the rules engine.

scanme.nmap.org is a well-maintained host that exposes two ports, so a real
scan of it exercises almost none of the triage rules. This fixture models the
port layout of Metasploitable 2 — a deliberately vulnerable training VM — so
the cleartext, exposed-datastore, remote-admin and end-of-life rules can all
be seen firing.

Nothing here was scanned. The file this writes is fabricated test data and is
labelled as such in the report it produces.

Run:
  python make_sample.py            # writes sample_vulnerable_scan.xml
"""

from xml.etree.ElementTree import Element, SubElement, ElementTree, indent

OUT = "sample_vulnerable_scan.xml"

# (port, service, product, version)
PORTS = [
    (21,   "ftp",        "vsftpd",              "2.3.4"),
    (22,   "ssh",        "OpenSSH",             "4.7p1 Debian 8ubuntu1"),
    (23,   "telnet",     "Linux telnetd",       ""),
    (25,   "smtp",       "Postfix smtpd",       ""),
    (53,   "domain",     "ISC BIND",            "9.4.2"),
    (80,   "http",       "Apache httpd",        "2.2.8"),
    (111,  "rpcbind",    "",                    "2"),
    (139,  "netbios-ssn", "Samba smbd",         "3.X - 4.X"),
    (445,  "netbios-ssn", "Samba smbd",         "3.X - 4.X"),
    (512,  "exec",       "netkit-rsh rexecd",   ""),
    (513,  "login",      "",                    ""),
    (514,  "shell",      "Netkit rshd",         ""),
    (1099, "java-rmi",   "GNU Classpath grmiregistry", ""),
    (1524, "bindshell",  "Metasploitable root shell", ""),
    (2049, "nfs",        "",                    "2-4"),
    (2121, "ftp",        "ProFTPD",             "1.3.1"),
    (3306, "mysql",      "MySQL",               "5.0.51a-3ubuntu5"),
    (5432, "postgresql", "PostgreSQL DB",       "8.3.0 - 8.3.7"),
    (5900, "vnc",        "VNC",                 "protocol 3.3"),
    (6000, "X11",        "",                    ""),
    (6667, "irc",        "UnrealIRCd",          ""),
    (8180, "http",       "Apache Tomcat/Coyote JSP engine", "1.1"),
]


def main() -> None:
    root = Element("nmaprun", {
        "scanner": "nmap",
        "args": "nmap -sT -sV -p- -oX sample_vulnerable_scan.xml 192.168.56.101",
        "start": "0",
        "version": "7.95",
    })

    host = SubElement(root, "host")
    SubElement(host, "status", {"state": "up", "reason": "syn-ack"})
    SubElement(host, "address", {"addr": "192.168.56.101", "addrtype": "ipv4"})
    hostnames = SubElement(host, "hostnames")
    SubElement(hostnames, "hostname", {"name": "metasploitable.local", "type": "PTR"})

    ports_el = SubElement(host, "ports")
    for num, name, product, version in PORTS:
        port_el = SubElement(ports_el, "port", {"protocol": "tcp", "portid": str(num)})
        SubElement(port_el, "state", {"state": "open", "reason": "syn-ack"})
        service = {"name": name, "method": "probed", "conf": "10"}
        if product:
            service["product"] = product
        if version:
            service["version"] = version
        SubElement(port_el, "service", service)

    runstats = SubElement(root, "runstats")
    SubElement(runstats, "finished", {"time": "0", "elapsed": "42.17"})

    tree = ElementTree(root)
    indent(tree, space="  ")
    tree.write(OUT, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {OUT} — 1 host, {len(PORTS)} open ports (synthetic)")


if __name__ == "__main__":
    main()
