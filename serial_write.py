import time

BLOCK_SIZE = 2048

def checksum(data: bytes) -> int:
    return sum(data) & 0xFF


def make_upload_header(address: int, total_size: int) -> bytes:
    return (
        b"\x01" +
        address.to_bytes(4, "big") +
        total_size.to_bytes(4, "big")
    )


def make_data_packet(block: bytes) -> bytes:
    if len(block) < BLOCK_SIZE:
        block = block + bytes(BLOCK_SIZE - len(block))

    return (
        b"\x02" +
        block +
        bytes([checksum(block)])
    )

def binary_write(ser, address: int, data: bytes):
    hdr = make_upload_header(address, len(data))
    # Step 1
    ser.write(b"bwr\r")

    # Step 2
    rx = ser.read_until(b"binary\r")

    # Step 3
    ser.write(hdr)
    ser.flush()

    # Step 4
    time.sleep(1)

    # Step 5
    offset = 0

    while offset < len(data):
        block = data[offset:offset + BLOCK_SIZE]
        packet = make_data_packet(block)
        ser.write(packet)
        ser.flush()
        ack = ser.read(1)
        if ack != b'Y':
            raise RuntimeError(
                f"Packet {offset//BLOCK_SIZE} not acknowledged."
            )
        offset += BLOCK_SIZE
        time.sleep(0.5)

    # Step 6
    ser.write(b"\r")
    ser.flush()

    # Step 7
    rx = ser.read_until(b">>")

    print("Binary write complete.")