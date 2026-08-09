#!/usr/bin/env python3
import struct
from dataclasses import dataclass


@dataclass
class Section:
    name: str
    address: int
    size: int
    file_offset: int
    flags: int
    data: bytes = b""


@dataclass
class Executable:
    entry: int
    gp: int
    text_start: int
    data_start: int
    bss_start: int
    sections: list


FILEHDR_FMT = "<HHIIIHH"
AOUTHDR_FMT = "<HH13I"
SCNHDR_FMT  = "<8sIIIIIIHHI"

FILEHDR_SIZE = struct.calcsize(FILEHDR_FMT)
AOUTHDR_SIZE = struct.calcsize(AOUTHDR_FMT)
SCNHDR_SIZE = struct.calcsize(SCNHDR_FMT)


def parse_ecoff(filename):

    with open(filename, "rb") as f:

        #
        # FILEHDR
        #

        (
            f_magic,
            f_nscns,
            f_timdat,
            f_symptr,
            f_nsyms,
            f_opthdr,
            f_flags,
        ) = struct.unpack(FILEHDR_FMT, f.read(FILEHDR_SIZE))

        if f_magic != 0x0162:
            raise RuntimeError(
                f"Invalid ECOFF magic 0x{f_magic:04X}"
            )
        print(f"Number of sections: {f_nscns}")
        #
        # AOUTHDR
        #

        (
            magic,
            vstamp,
            tsize,
            dsize,
            bsize,
            entry,
            text_start,
            data_start,
            bss_start,
            gprmask,
            cpr0,
            cpr1,
            cpr2,
            cpr3,
            gp_value,
        ) = struct.unpack(
            AOUTHDR_FMT,
            f.read(AOUTHDR_SIZE),
        )

        #
        # Section table
        #

        sections = []

        for _ in range(f_nscns):

            (
                raw_name,
                paddr,
                vaddr,
                size,
                scnptr,
                relptr,
                lnnoptr,
                nreloc,
                nlnno,
                flags,
            ) = struct.unpack(
                SCNHDR_FMT,
                f.read(SCNHDR_SIZE),
            )

            name = raw_name.rstrip(b"\0").decode("ascii")

            section = Section(
                name=name,
                address=vaddr,
                size=size,
                file_offset=scnptr,
                flags=flags,
            )

            sections.append(section)

        #
        # Read section contents
        #

        for s in sections:

            #
            # .bss and .sbss have no file data
            #

            if s.file_offset == 0 or s.size == 0:
                continue

            pos = f.tell()

            f.seek(s.file_offset)

            s.data = f.read(s.size)

            f.seek(pos)

    #
    # Keep only initialized sections
    #

    upload = []

    for s in sections:

        if s.name in (
            ".text",
            ".rdata",
            ".data",
            ".sdata",
        ):
            upload.append(s)

    return Executable(
        entry=entry,
        gp=gp_value,
        text_start=text_start,
        data_start=data_start,
        bss_start=bss_start,
        sections=upload,
    )