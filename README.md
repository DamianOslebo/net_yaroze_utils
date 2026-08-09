# net_yaroze_utils

## yaroze_monitor.py
Mimics SIOCONS functionality

### Dependencies
Depends on socat, and "Comm Tunnel (Serial Port Tool)"
- In Windows: Comm Tunnel
    1. Endpoint 1: COMX, Baud Rate
    2. Endpoint 2: TCP Server: Port: 2101
- In Linux: sudo socat PTY,link=/dev/ttyV0,raw,echo=0 TCP:\<address\>:2101,reuseaddr

### Usage
sudo python3 yaroze_monitor.py --serial /dev/ttyV0

- "auto"- Run 
- "load <filename> <filename> [addr]"-  
- "run"- loads, starts execution, begins serial monitor of printf. CTRL-C to exit on return
- Other __Net Yaroze serial__ commands like "dr", "dir"

## blend2tmd.py
Blender to TMD 3d model writer. 

## Dependency
Blender 5.2.0+

### Usage
Open Scripting with Blender and run script. Under File->Export, a new option is added to export TMD files. 

Options: 
* Face Color - color attributes can be exported with 3d vertices
* Texture UVs - Select Texture Page (Default 10), texture dimensions, and CLUT table location if not 15-bit texture.

Limitations:
Only one texture and one mesh supported right now.

## bmp2tim.py
Converts BMP to TIM 16-bit format places at a specified texture page and offset

### Usage
bmp2tim \<input-file\> \<output-file\> [-tpage 10]

Limitations: 
Only 16 bit format right now.

## makefile_ex
Sample makefile for usage with net_yaroze builds

## Dependency
* mipsel-linux-gnu-gcc
* libps (ar repackaged from DOSBOX) and linker file MIPSPSX.X
* make

## Usage
make
