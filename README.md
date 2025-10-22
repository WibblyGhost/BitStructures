# BitStructures

## Intro

This package was inspired by many byte level decoders and structure packing that were made for python, many of them didn't really handle bit streams directly.
Many packages I came across had a large list of outstanding issues and weren't updated in years.
So I decided to make a package that does exactly this, making it easy to define structural patterns to define network payloads on the bit level.

Running in **Python-3.12.xx** and greater with new type support for the structures and classes that help classify the built and parsed data. Makin it easy to see what data is getting processed, the size of the data and what we are trying to write. There are also methods to present the structure in a human readable form.

```bash
PrettyPrint:
        'version'            | size=4  | 4
        ----------------------------------------
        'header_length'      | size=4  | 20
        'precedence'         | size=3  | 0
        'minimize_delay'     | size=1  | 0
        'high_throuput'      | size=1  | 0
        'high_reliability'   | size=1  | 0
        'minimize_cost'      | size=1  | 0
        ----------------------------------------
        '__padding'          | size=1  | None
        ----------------------------------------
        'total_length'       | size=16 | 28
        ----------------------------------------
        'identification'     | size=16 | 1
        '__padding'          | size=1  | None
        'dont_fragment'      | size=1  | 0
        'more_fragments'     | size=1  | 0
        ----------------------------------------
        'fragment_offset'    | size=13 | 0
        ----------------------------------------
        'ttl'                | size=8  | 64
        ----------------------------------------
        'protocol'           | size=8  | enum.UDP
        ----------------------------------------
        'checksum'           | size=16 | 60351
        ----------------------------------------
        'source_ip'          | size=32 | 127.0.0.1
        ----------------------------------------
        'destination_ip'     | size=32 | 8.8.8.8
        ----------------------------------------
        'source_port'        | size=16 | 53
        ----------------------------------------
        'destination_port'   | size=16 | 53
        ----------------------------------------
        'payload_length'     | size=16 | 16
        ----------------------------------------
        'checksum'           | size=16 | 28771
```

## Examples

[Simple IPv4 Codecs](src/examples/ip_codec.py)
```python
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
```