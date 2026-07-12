from bitarray import bitarray
from pytest import raises

from bitstructures.base.bitstream import BitStream
from bitstructures.exceptions import ReadError, SizeError, WriteError


class TestConstruction:
    def test_construct_from_binary_string(self) -> None:
        bs = BitStream("1010")
        assert bs.bin == "1010"

    def test_construct_from_prefixed_binary_string(self) -> None:
        bs = BitStream("0b1010")
        assert bs.bin == "1010"

    def test_construct_from_bytes(self) -> None:
        bs = BitStream(b"\x0f")
        assert len(bs) == 8  # noqa: PLR2004
        assert bytes(bs) == b"\x0f"

    def test_construct_from_bitarray(self) -> None:
        ba = bitarray("1010")
        bs = BitStream(ba)
        assert bs.bin == "1010"
        assert bs.stream is ba

    def test_invalid_string_raises(self) -> None:
        with raises(TypeError, match="Buffer can only contain binary integers: 0's/1's"):
            BitStream("10201")


class TestConversions:
    def test_bin_property(self) -> None:
        assert BitStream("1100").bin == "1100"

    def test_int_conversion(self) -> None:
        assert int(BitStream("1010")) == 10  # noqa: PLR2004

    def test_bytes_conversion(self) -> None:
        bs = BitStream("00001111")
        assert bytes(bs) == b"\x0f"

    def test_bytes_conversion_invalid_size(self) -> None:
        stream = "101"
        with raises(
            SizeError,
            match=(
                f"Cannot convert a BitStream of length {len(stream)} to bytes, "
                f"must be divisable by 8"
            ),
        ):
            bytes(BitStream(stream))


class TestRepresentations:
    def test_str_for_bit_aligned_stream(self) -> None:
        assert str(BitStream("101")) == "0b101"

    def test_str_for_byte_aligned_stream(self) -> None:
        assert str(BitStream("00001111")) == "b'\\x0f'"

    def test_repr_for_bit_aligned_stream(self) -> None:
        assert repr(BitStream("101")) == "BitStream(0b101)"

    def test_repr_for_byte_aligned_stream(self) -> None:
        assert repr(BitStream("00001111")) == "BitStream(b'\\x0f')"


class TestComparison:
    def test_equal_bitstreams(self) -> None:
        assert BitStream("1010") == BitStream("1010")

    def test_equal_to_string(self) -> None:
        assert BitStream("1010") == "1010"

    def test_equal_to_bitarray(self) -> None:
        assert BitStream("1010") == bitarray("1010")

    def test_not_equal(self) -> None:
        assert BitStream("1010") != BitStream("0101")

    def test_invalid_type_returns_false(self) -> None:
        assert BitStream("1010") != object()


class TestBitwiseOperators:
    def test_and(self) -> None:
        result = BitStream("1100") & BitStream("1010")
        assert result.bin == "1000"

    def test_or(self) -> None:
        result = BitStream("1100") | BitStream("1010")
        assert result.bin == "1110"

    def test_xor(self) -> None:
        result = BitStream("1100") ^ BitStream("1010")
        assert result.bin == "0110"

    def test_invert(self) -> None:
        result = ~BitStream("1010")
        assert result.bin == "0101"

    def test_left_shift(self) -> None:
        result = BitStream("1010") << 1
        assert result.bin == "0100"

    def test_right_shift(self) -> None:
        result = BitStream("1010") >> 1
        assert result.bin == "0101"


class TestConcatenation:
    def test_add(self) -> None:
        result = BitStream("1010") + BitStream("1111")
        assert result.bin == "10101111"

    def test_add_string(self) -> None:
        result = BitStream("1010") + "1111"
        assert result.bin == "10101111"

    def test_iadd(self) -> None:
        bs = BitStream("1010")
        bs += BitStream("1111")
        assert bs.bin == "10101111"


class TestIterationAndIndexing:
    def test_iteration(self) -> None:
        bs = BitStream("101")
        assert list(bs) == [1, 0, 1]

    def test_index(self) -> None:
        bs = BitStream("101")
        assert bs[0] == 1
        assert bs[1] == 0

    def test_slice(self) -> None:
        bs = BitStream("101100")
        sliced = bs[1:4]
        assert isinstance(sliced, BitStream)
        assert sliced.bin == "011"


class TestReadPeek:
    def test_peek_does_not_modify_stream(self) -> None:
        bs = BitStream("101100")
        out = bs.peek(3)
        assert out.bin == "101"
        assert bs.bin == "101100"

    def test_read_modifies_stream(self) -> None:
        bs = BitStream("101100")
        out = bs.read(3)
        assert out.bin == "101"
        assert bs.bin == "100"

    def test_read_all_when_negative(self) -> None:
        bs = BitStream("101100")
        out = bs.read(-1)
        assert out is bs

    def test_read_none_returns_self(self) -> None:
        bs = BitStream("101100")
        out = bs.read(None)
        assert out is bs

    def test_read_too_many_bits(self) -> None:
        read_len = 4
        bs = BitStream("101")
        with raises(
            ReadError,
            match=(
                f"Cannot read {read_len} bits, reached the EOS or the current stream is shorter "
                f"than specified size. stream={len(bs)}"
            ),
        ):
            bs.read(read_len)


class TestWrite:
    def test_write_integer(self) -> None:
        bs = BitStream()
        bs.write(5, 4)
        assert bs.bin == "0101"

    def test_write_bitstream_exact_size(self) -> None:
        bs = BitStream()
        bs.write(BitStream("101"), 3)
        assert bs.bin == "101"

    def test_write_bitstream_padded(self) -> None:
        bs = BitStream()
        bs.write(BitStream("101"), 5)
        assert bs.bin == "10100"

    def test_write_integer_too_large(self) -> None:
        bs = BitStream()
        value = 16
        size = 4
        with raises(
            WriteError,
            match=(
                f"Cannot write value {value} of size {value.bit_length()} "
                f"into a stream of size {size}"
            ),
        ):
            bs.write(value, size)

    def test_write_bitstream_too_large(self) -> None:
        bs = BitStream()
        stream = "10101"
        stream_size = 4
        with raises(
            WriteError,
            match=(
                f"Cannot write value 0b{stream} of size {len(stream)} "
                f"into a stream of size {stream_size}"
            ),
        ):
            bs.write(BitStream(stream), stream_size)


class TestCopy:
    def test_copy(self) -> None:
        original = BitStream("1010")
        copied = original.copy()
        assert copied == original
        assert copied is not original


class TestPadding:
    def test_ljust_default_fill(self) -> None:
        result = BitStream("101").ljust(5)
        assert result.bin == "10100"

    def test_ljust_fill_one(self) -> None:
        result = BitStream("101").ljust(5, 1)
        assert result.bin == "10111"

    def test_rjust_default_fill(self) -> None:
        result = BitStream("101").rjust(5)
        assert result.bin == "00101"

    def test_rjust_fill_one(self) -> None:
        result = BitStream("101").rjust(5, 1)
        assert result.bin == "11101"

    def test_ljust_invalid_fill(self) -> None:
        with raises(ValueError, match="fillbit must be '0' or '1'"):
            BitStream("101").ljust(5, 2)

    def test_rjust_invalid_fill(self) -> None:
        with raises(ValueError, match="fillbit must be '0' or '1'"):
            BitStream("101").rjust(5, 2)

    def test_ljust_no_padding_required(self) -> None:
        bs = BitStream("1010")
        result = bs.ljust(4)
        assert result == bs
        assert result is not bs

    def test_rjust_no_padding_required(self) -> None:
        bs = BitStream("1010")
        result = bs.rjust(4)
        assert result == bs
        assert result is not bs


class TestMisc:
    def test_bit_length(self) -> None:
        assert BitStream("10101").bit_length() == 5  # noqa: PLR2004

    def test_len(self) -> None:
        assert len(BitStream("10101")) == 5  # noqa: PLR2004

    def test_hash_matches_underlying_stream(self) -> None:
        bs = BitStream("1010")
        assert hash(bs) == hash(bs.stream.to01())
