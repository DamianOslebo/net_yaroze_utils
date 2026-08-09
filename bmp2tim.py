#!/usr/bin/env python3
import argparse
import struct
from pathlib import Path


TIM_MAGIC = 0x00000010
TIM_16BIT = 0x00000002

VRAM_WIDTH = 1024
VRAM_HEIGHT = 512

TPAGE_WIDTH = 64
TPAGE_HEIGHT = 256

MAX_TPAGE = 31


def tpage_to_vram(tpage):
    """
    Convert a PS1 16-bit texture page number to its VRAM origin.

    TPage layout:

        0  1  2  3  ... 15
       16 17 18 19  ... 31

    Each page is 64 x 256 pixels for 16-bit textures.
    """

    if tpage < 0 or tpage > MAX_TPAGE:
        raise ValueError(
            f"TPage must be between 0 and {MAX_TPAGE}"
        )

    page_x = (tpage % 16) * TPAGE_WIDTH
    page_y = (tpage // 16) * TPAGE_HEIGHT

    return page_x, page_y


def read_bmp(filename):
    """
    Read an uncompressed 24-bit or 32-bit BMP.

    Returns:

        width
        height
        pixels[y][x] = (r, g, b, a)
    """

    with open(filename, "rb") as f:
        data = f.read()

    if len(data) < 54:
        raise ValueError("File is too small to be a valid BMP")

    if data[0:2] != b"BM":
        raise ValueError("Not a BMP file")

    # BMP file header
    pixel_offset = struct.unpack_from("<I", data, 10)[0]

    # DIB header
    dib_size = struct.unpack_from("<I", data, 14)[0]

    if dib_size < 40:
        raise ValueError("Unsupported BMP DIB header")

    width = struct.unpack_from("<i", data, 18)[0]
    height = struct.unpack_from("<i", data, 22)[0]
    planes = struct.unpack_from("<H", data, 26)[0]
    bpp = struct.unpack_from("<H", data, 28)[0]
    compression = struct.unpack_from("<I", data, 30)[0]

    if width <= 0:
        raise ValueError("Invalid BMP width")

    if height == 0:
        raise ValueError("Invalid BMP height")

    if planes != 1:
        raise ValueError("Unsupported BMP: planes must be 1")

    if compression != 0:
        raise ValueError(
            "Compressed BMPs are not supported. "
            "Please save as an uncompressed BMP."
        )

    if bpp not in (24, 32):
        raise ValueError(
            f"Unsupported BMP depth: {bpp} bits. "
            "Only 24-bit and 32-bit BMPs are supported."
        )

    # Negative height means top-down BMP.
    top_down = height < 0
    height = abs(height)

    bytes_per_pixel = bpp // 8

    # BMP rows are aligned to 4-byte boundaries.
    row_size = ((width * bytes_per_pixel + 3) // 4) * 4

    pixels = []

    for y in range(height):

        if top_down:
            src_y = y
        else:
            src_y = height - 1 - y

        row_start = pixel_offset + src_y * row_size

        row = []

        for x in range(width):

            offset = row_start + x * bytes_per_pixel

            # BMP stores BGR(A).
            b = data[offset + 0]
            g = data[offset + 1]
            r = data[offset + 2]

            if bpp == 32:
                a = data[offset + 3]
            else:
                a = 255

            row.append((r, g, b, a))

        pixels.append(row)

    return width, height, pixels


def rgb_to_ps1(r, g, b, a=255):
    """
    Convert RGB888 to PS1 16-bit BGR555/STP.

    PS1 16-bit color:

        bit 15      STP
        bits 14-10  B
        bits 9-5    G
        bits 4-0    R

    STP is currently always zero.
    """

    r5 = r >> 3
    g5 = g >> 3
    b5 = b >> 3

    stp = 0

    return (
        (stp << 15) |
        (b5 << 10) |
        (g5 << 5) |
        r5
    )


def write_tim_16bit(
    filename,
    width,
    height,
    pixels,
    vram_x,
    vram_y
):
    """
    Write a 16-bit TIM file.

    vram_x/vram_y are the actual pixel coordinates in PS1 VRAM.
    """

    # For 16-bit TIM:
    #
    # one pixel = one 16-bit VRAM word
    #
    tim_width = width
    tim_height = height

    # Image block:
    #
    #   4 bytes  block size
    #   2 bytes  px
    #   2 bytes  py
    #   2 bytes  pw
    #   2 bytes  ph
    #   pixel data
    #
    image_data_size = (
        12 +
        width * height * 2
    )

    with open(filename, "wb") as f:

        # TIM magic
        f.write(struct.pack("<I", TIM_MAGIC))

        # TIM flags
        #
        # 0x2 = 16-bit direct color
        #
        f.write(struct.pack("<I", TIM_16BIT))

        # Image block size
        f.write(struct.pack("<I", image_data_size))

        # VRAM position
        f.write(
            struct.pack(
                "<HH",
                vram_x,
                vram_y
            )
        )

        # Image dimensions
        f.write(
            struct.pack(
                "<HH",
                tim_width,
                tim_height
            )
        )

        # Pixel data
        for y in range(height):

            for x in range(width):

                r, g, b, a = pixels[y][x]

                color = rgb_to_ps1(
                    r,
                    g,
                    b,
                    a
                )

                f.write(
                    struct.pack(
                        "<H",
                        color
                    )
                )


def convert_bmp_to_tim(
    input_file,
    output_file,
    tpage,
    x_offset,
    y_offset
):
    """
    Convert BMP to a 16-bit TIM.

    TPage determines the 64x256 page.
    Offsets determine the position within that page.
    """

    width, height, pixels = read_bmp(input_file)

    page_x, page_y = tpage_to_vram(tpage)

    vram_x = page_x + x_offset
    vram_y = page_y + y_offset

    print(f"Input BMP : {input_file}")
    print(f"Output TIM: {output_file}")
    print(f"Image     : {width} x {height}")
    print(f"TPage     : {tpage}")
    print(f"Page base : ({page_x}, {page_y})")
    print(f"Offset    : ({x_offset}, {y_offset})")
    print(f"VRAM      : ({vram_x}, {vram_y})")
    print("Format    : 16-bit TIM")

    # Validate offsets.

    if x_offset < 0 or x_offset >= TPAGE_WIDTH:
        raise ValueError(
            f"x-offset must be between "
            f"0 and {TPAGE_WIDTH - 1}"
        )

    if y_offset < 0 or y_offset >= TPAGE_HEIGHT:
        raise ValueError(
            f"y-offset must be between "
            f"0 and {TPAGE_HEIGHT - 1}"
        )

    # Validate final VRAM placement.

    if vram_x < 0 or vram_x + width > VRAM_WIDTH:
        raise ValueError(
            f"Texture exceeds VRAM width: "
            f"x={vram_x}, width={width}"
        )

    if vram_y < 0 or vram_y + height > VRAM_HEIGHT:
        raise ValueError(
            f"Texture exceeds VRAM height: "
            f"y={vram_y}, height={height}"
        )

    write_tim_16bit(
        output_file,
        width,
        height,
        pixels,
        vram_x,
        vram_y
    )

    print("Conversion complete.")


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Convert a BMP to a PS1 16-bit TIM "
            "using a texture page and offsets."
        )
    )

    parser.add_argument(
        "input",
        help="Input BMP file"
    )

    parser.add_argument(
        "output",
        help="Output TIM file"
    )

    parser.add_argument(
        "--tpage",
        type=int,
        required=True,
        help="PS1 texture page (0-31)"
    )

    parser.add_argument(
        "--x-offset",
        type=int,
        default=0,
        help="X offset within the texture page (default: 0)"
    )

    parser.add_argument(
        "--y-offset",
        type=int,
        default=0,
        help="Y offset within the texture page (default: 0)"
    )

    args = parser.parse_args()

    input_file = Path(args.input)
    output_file = Path(args.output)

    if not input_file.exists():
        parser.error(
            f"Input file does not exist: {input_file}"
        )

    try:

        convert_bmp_to_tim(
            input_file,
            output_file,
            args.tpage,
            args.x_offset,
            args.y_offset
        )

    except Exception as e:

        print(f"Error: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()