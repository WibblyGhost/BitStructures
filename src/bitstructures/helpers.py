from bitstructures.base.codec import Container


def bitshift(packet: Container[int], field_name: str, msb: bool = False) -> int:
    """
    Works on LSB calculations by default
    Join two bitshifted ingeters by appending the second integer
    onto the end of the first integer.
    """
    # Left shift operation followed by a bitwise OR operation
    # This will append the part 2 to the end of part 1 and extend the packet
    part_1: int = getattr(packet, f"{field_name}_p1")
    part_2: int = getattr(packet, f"{field_name}_p2")
    if msb:
        return part_2 << part_1.bit_length() | part_1
    return part_1 << part_2.bit_length() | part_2


def reverse_bitshift(integer: int, bitshift: int, msb: bool = False) -> tuple[int, int]:
    """
    Works on LSB calculations by default
    Split a packet into two seperate binary integers using a specified
    integer to bitshift, and a bitshift amount.
    """
    # 1. Determine size of second packet
    # 2. Extract the second number
    # You can do this by using a bitwise AND operation
    # with a mask that has the same number of bits as the second number.
    part_2 = integer & ((1 << bitshift) - 1)
    # 3. Extract the first number
    # To get the first number, you can right shift the combined number
    # by the number of bits in the second number
    part_1 = integer >> bitshift
    if msb:
        return part_2, part_1
    return part_1, part_2
