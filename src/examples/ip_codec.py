"""
Internet Protocol version 4 (TCP/IP protocol stack)
See RFC791

Transmission Control Protocol (TCP/IP protocol stack)
See RFC9293

User Datagram Protocol (TCP/IP protocol stack)
See RFC768
"""

from math import ceil

from bitstructures import (
    BitsInt,
    Const,
    Enum,
    ExprAdapter,
    Flag,
    GreedyBits,
    IpAddress,
    Optional,
    Padding,
    Struct,
    Switch,
)

IPV4_HEADER = Struct(
    "version" / Const(BitsInt(4), const=4),
    "header_length"
    / ExprAdapter(
        BitsInt(4),
        encoder=lambda obj: obj * 4,
        decoder=lambda obj: ceil(obj / 4),
    ),
    "tos" /
    Struct(
        "precedence" / BitsInt(3),
        "minimize_delay" / Flag(),
        "high_throuput" / Flag(),
        "high_reliability" / Flag(),
        "minimize_cost" / Flag(),
        Padding(1),
        embedded=False
    ),
    "total_length" / BitsInt(16),
    "identification" / BitsInt(16),
    "flags" / Struct(
        Padding(1),
        "dont_fragment" / Flag(),
        "more_fragments" / Flag(),
        embedded=False
    ),
    "fragment_offset" / BitsInt(13),
    "ttl" / BitsInt(8),
    "protocol"
    / Enum(
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
    "header_length"
    / ExprAdapter(
        BitsInt(4),
        encoder=lambda obj: obj * 4,
        decoder=lambda obj: ceil(obj / 4),
    ),
    Padding(3),
    "flags" / Struct(
        "ns" / Flag(),
        "cwr" / Flag(),
        "ece" / Flag(),
        "urg" / Flag(),
        "ack" / Flag(),
        "psh" / Flag(),
        "rst" / Flag(),
        "syn" / Flag(),
        "fin" / Flag(),
        embedded=False
    ),
    "window" / BitsInt(16),
    "checksum" / BitsInt(16),
    "urgent" / BitsInt(16),
    "options" / Optional(BitsInt(lambda packet: packet.header_length - 20)),
    embedded=False,
)

UDP_HEADER = Struct(
    "source_port" / BitsInt(16),
    "destination_port" / BitsInt(16),
    "payload_length"
    / ExprAdapter(
        BitsInt(16),
        encoder=lambda obj: obj + 8,
        decoder=lambda obj: obj - 8,
    ),
    "checksum" / BitsInt(16),
    embedded=False,
)


# IP/UDP packet used for basic packet data tests, not in spec
IP_PACKET = Struct(
    IPV4_HEADER,
    "header" / Switch(lambda packet: packet.protocol, {"UDP": UDP_HEADER, "TCP": TCP_HEADER}),
    # "payload" / GreedyBits(),
)
