"""
Internet Protocol version 4 (TCP/IP protocol stack)
See RFC791

Transmission Control Protocol (TCP/IP protocol stack)
See RFC9293

User Datagram Protocol (TCP/IP protocol stack)
See RFC768
"""  # noqa: D400, D415

from math import ceil

from bitstructures import (
    BitsInt,
    Const,
    Enumerate,
    ExprAdapter,
    Flag,
    IpAddress,
    Optional,
    Padding,
    Struct,
    Switch,
)
from bitstructures.base.codec import Codec, GreedyBits

IPV4_HEADER = Struct(
    "version" / Const(BitsInt(4), const=4),
    "header_length"
    / ExprAdapter(
        # Indicates the length of the header in 32-bit words (minimum is 5, which equals 20 bytes).
        BitsInt(4),
        encoder=lambda obj: obj * 4,
        decoder=lambda obj: ceil(obj / 4),
    ),
    "tos"
    / Struct(
        "precedence" / BitsInt(3),
        "minimize_delay" / Flag(),
        "high_throuput" / Flag(),
        "high_reliability" / Flag(),
        "minimize_cost" / Flag(),
        Padding(1),
        embedded=False,
    ),
    "total_length" / BitsInt(16),
    "identification" / BitsInt(16),
    "flags"
    / Struct(Padding(1), "dont_fragment" / Flag(), "more_fragments" / Flag(), embedded=False),
    "fragment_offset" / BitsInt(13),
    "ttl" / BitsInt(8),
    "protocol"
    / Enumerate(
        8,
        ICMP=1,
        TCP=6,
        UDP=17,
    ),
    "checksum" / BitsInt(16),
    "source_ip" / IpAddress(BitsInt(32)),
    "destination_ip" / IpAddress(BitsInt(32)),
    "options" / Optional(BitsInt(lambda packet: packet.header_length - 20)),
)

TCP_HEADER = Struct(
    "source_port" / BitsInt(16),
    "destination_port" / BitsInt(16),
    "seq" / BitsInt(32),
    "ack" / BitsInt(32),
    "length"
    / ExprAdapter(
        BitsInt(4),
        encoder=lambda obj: obj * 4,
        decoder=lambda obj: ceil(obj / 4),
    ),
    Padding(3),
    "flags"
    / Struct(
        "ns" / Flag(),
        "cwr" / Flag(),
        "ece" / Flag(),
        "urg" / Flag(),
        "ack" / Flag(),
        "psh" / Flag(),
        "rst" / Flag(),
        "syn" / Flag(),
        "fin" / Flag(),
        embedded=False,
    ),
    "window" / BitsInt(16),
    "checksum" / BitsInt(16),
    "urgent" / BitsInt(16),
    "options" / Optional(BitsInt(lambda packet: packet.length - 20)),
)

UDP_HEADER = Struct(
    "source_port" / BitsInt(16),
    "destination_port" / BitsInt(16),
    # Indicates the total length of the UDP header plus the payload.
    # The minimum value for this field is 8 (the header size), as there is always a header present.
    "length" / BitsInt(16),
    "checksum" / BitsInt(16),
)


# IP/UDP packet used for basic packet data tests, not in spec
IP_PACKET = Struct(
    IPV4_HEADER,
    "header"
    / Switch[str, Codec](
        lambda packet: packet.protocol, {"UDP": UDP_HEADER, "TCP": TCP_HEADER}, embedded=False
    ),
    "payload" / GreedyBits(),
)


if __name__ == "__main__":
    from scapy.layers.inet import IP, UDP

    ip = IP(src="127.0.0.1", dst="8.8.8.8") / UDP(dport=53) / b"test_packet"
    ip_data = ip.build()
    print(f"IP: {ip_data!r}")
    stack = IP_PACKET.parse(ip_data)
    print(f"DECODED:\n{stack.pprint()}")
    container = stack.to_container()
    print(f"Container:\n{container!s}")
    raw = IP_PACKET.build(container)
    print(f"RAW:\n{raw!r}")
    print(f"{raw == ip_data=}")

    print(IP_PACKET.pprint())
