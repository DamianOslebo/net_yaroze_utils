#!/usr/bin/env python3
import socket
from urllib import response
import serial
import time
import argparse
from datetime import datetime
from serial_write import binary_write
from yaroze_executable import parse_ecoff

PROMPT = b">>"

def timestamp():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def hexdump(data):
    return " ".join(f"{b:02x}" for b in data)

COMMAND_DELAYS = {
    "dir": 4.0,
    "di": 0.5,
    "ld": 2.0,
    "go": 3.0,
}

def get_idle_timeout(cmd):
    if isinstance(cmd, bytes):
        cmd = cmd.decode(errors="ignore")

    parts = cmd.strip().split()[0]

    if not parts:
        return 0.25

    return COMMAND_DELAYS.get(parts[0].lower(),0.25)

class PSXMonitor:

    def __init__(self, port, baud=9600):
        self.ser = serial.Serial(
            port,
            baudrate=baud,
            timeout=5
        )

    def send(self, cmd):
        if isinstance(cmd, str):
            cmd = cmd.encode()

        packet = cmd + b"\r\n"

        print(f"\n[{timestamp()}] SEND")
        print(cmd.decode(errors="ignore"))

        self.ser.write(packet)
        
        response = self.read_response(cmd, idle_timeout=get_idle_timeout(cmd))

        self.decode(response)
        
        return response

    def read_response(self, command, timeout=5.0, idle_timeout=0.5):

        start = time.time()
        last_rx = time.time()

        buffer = bytearray()

        command_seen = False
        prompt_seen = False

        while True:
            waiting = self.ser.in_waiting

            if waiting:
                data = self.ser.read(waiting)
                buffer.extend(data)
                last_rx = time.time()

            # Wait until command echo appears
            if command in buffer:
                command_seen = True

            # Only accept prompt after command was echoed
            if command_seen and buffer.rstrip().endswith(b">>"):
                prompt_seen = True

            if prompt_seen:
                # allow remaining bytes to arrive
                if time.time() - last_rx > idle_timeout:
                    break

            if time.time() - start > timeout:
                break

            time.sleep(0.01)

        return bytes(buffer)

    def decode(self, data):
        print("\nRAW:")
        print(hexdump(data))

        print("\nTEXT:")

        if isinstance(data, bytearray):
            data = bytes(data)

        if not isinstance(data, bytes):
            print("BAD TYPE:", type(data))
            print(repr(data))
            return

        print(data.decode("ascii", errors="replace"))

    def upload_program(self, filename):
        try:
            exe = parse_ecoff(filename)
        except Exception as e:
            print(f"Error parsing {filename}: {e}")
            return
        for section in exe.sections:
            print(f"Uploading section {section.name} to 0x{section.address:08X} ({section.size} bytes)")
            binary_write(self.ser, section.address, section.data)
        print(f"Upload of {filename} complete.")
        
        self.execute_program(exe.entry)

        return exe

    def upload_file(self, filename, address):
        with open(filename, "rb") as f:
            data = f.read()

        print(f"Uploading binary {filename} to 0x{address:08X} ({len(data)} bytes)")
        binary_write(self.ser, address, data)
        print(f"Upload of {filename} complete.")

    def execute_program(self, entry_point):
        """
        Start uploaded Yaroze program.

        Equivalent to SIOCONS:
            sr epc <entry>
            go
        """

        print(f"Setting EPC = {entry_point:08X}")

        cmd = f"sr epc {entry_point:08x}\r"
        self.ser.write(cmd.encode())
        self.ser.flush()

        print("Starting program")

        self.ser.write(b"go\r")
        self.ser.flush()

        time.sleep(0.5)  # brief pause for program to start

        print("\n=== PROGRAM RUNNING - Listening on serial ===\n"
              "Press Ctrl+C to return to monitor prompt\n")
        self.listen_to_program()


    def listen_to_program(self):
        """Continuously listen to serial output from the running program."""
        try:
            while True:
                if self.ser.in_waiting:
                    data = self.ser.read(self.ser.in_waiting)
                    print(data.decode("ascii", errors="replace"), end="", flush=True)
                time.sleep(0.01)
        except KeyboardInterrupt:
            print("\n\n=== Stopped listening - back to monitor ===")
        except Exception as e:
            print(f"\nListening error: {e}")

    def test_bwr(self):

        self.ser.write(b"bwr\r")

        rx = self.ser.read_until(b"binary\r")

        header = bytes.fromhex(
            "01 "
            "80 0f 00 00 "
            "00 00 08 00"
        )

        self.ser.write(header)
        self.ser.flush()

        time.sleep(0.5)

        data = (b"\xde\xad\xbe\xef" * 512)

        checksum = sum(data) & 0xff

        packet = bytes([0x02]) + data + bytes([checksum])

        print(len(packet))
        print(hex(checksum))

        time.sleep(0.15)

        self.ser.write(packet)
        self.ser.flush()

        print("waiting")

        ack = self.ser.read(1)
        print("ACK", ack)

        self.ser.write(b"\r")
        self.ser.flush()

        response = self.ser.read_until(b">>")
        print(response)

    def test_bwr_write(self, address, filename):
        payload = (bytes.fromhex("DEADBEEF")* (4096 // 4))
        binary_write(self.ser,0x800F0000,payload)

    # ------------------------------------------------------------------ 
    # Command interpreter 
    # ------------------------------------------------------------------ 
    def execute_command(self, command): 
        command = command.strip() 
        if not command: 
            return True 

        # Comments are allowed in auto files. 
        if command.startswith("#"): 
            return True 
        parts = command.split() 
        name = parts[0].lower() 

        # -------------------------------------------------------------- 
        # Local commands 
        # -------------------------------------------------------------- 
        if name == "upload": 
            if len(parts) < 2: 
                print( "Usage: upload <file> <address>" ) 
                return True
            if len(parts) == 2:
                address = 0x800F0000
            else:
                address = int(parts[2], 16) 
            filename = parts[1] 
            self.upload_file(filename, address) 
            return True 
        if name == "run": 
            if len(parts) != 2: 
                print( "Usage: run <file>" ) 
                return True 
            self.upload_program(parts[1]) 
            return True 
        if name == "auto": 
            if len(parts) != 2: 
                print( "Usage: auto <file>" ) 
                return True 
            self.run_auto(parts[1]) 
            return True 
        if name in ("quit", "exit"): 
            return False 
        # -------------------------------------------------------------- 
        # Anything else goes directly to the Yaroze monitor. 
        # -------------------------------------------------------------- 
        self.send(command) 
        return True 

    # ------------------------------------------------------------------ 
    # Auto command files 
    # ------------------------------------------------------------------ 
    def run_auto(self, filename): 
        print(f"\n=== AUTO: {filename} ===") 
        try: 
            with open( filename, "r", encoding="utf-8" ) as f: 
                for line_number, line in enumerate( f, 1 ): 
                    command = line.strip() 
                    # Ignore blank lines and comments. 
                    if not command: 
                        continue 
                    if command.startswith("#"): 
                        continue 
                    print( f"\n[AUTO {line_number}] " f"{command}" ) 
                    try: 
                        if not self.execute_command( command ): 
                            print( "\n=== AUTO STOPPED ===" ) 
                            return 
                    except Exception as e: 
                        print( f"\nERROR on auto line " f"{line_number}: {e}" ) 
                        return 
        except Exception as e: 
            print( f"Error opening auto file " f"{filename}: {e}" ) 

        return print("\n=== AUTO COMPLETE ===")

def main():

    ap=argparse.ArgumentParser()

    ap.add_argument(
        "--serial",
        required=True
    )

    ap.add_argument(
        "--baud",
        default=9600,
        type=int
    )

    args=ap.parse_args()

    mon=PSXMonitor(
        args.serial,
        args.baud
    )

    while True:
        try:
            command = input("psx>> ")

            if not mon.execute_command(command):
                break

        except KeyboardInterrupt:
            print("\nExiting.")
            break

        except EOFError:
            print()
            break

        except Exception as e:
            print(f"ERROR: {e}")

if __name__=="__main__":
    main()