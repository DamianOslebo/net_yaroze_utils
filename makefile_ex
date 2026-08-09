CC      = mipsel-linux-gnu-gcc

INCLUDES = -I/home/devcontainers/net-yaroze/build-tools/INCLUDE -I/home/devcontainers/net-yaroze/elden_clone

CFLAGS  = \
    -O1 \
    -mips1 \
    -mabi=32 \
    -EL \
    -msoft-float \
    -ffreestanding \
    -fno-builtin \
	-mno-abicalls \
    -fno-pic \
    -G0 \
    -mno-gpopt \
    $(INCLUDES)

LDSCRIPT = /home/devcontainers/net-yaroze/build-tools/lib/LDSCRIPT/MIPSPSX.X

LDFLAGS = \
    -nostdlib \
    -L/home/devcontainers/net-yaroze/build-tools/lib \
    -Wl,-T,$(LDSCRIPT) \
    -Wl,-G,0

LIBS = -lps

PROG = main.elf

BUILD_DIR = build

SRCS = \
    main.c \
    ny_light.c \
    pad.c

OBJS = $(SRCS:%.c=$(BUILD_DIR)/%.o)

$(PROG): $(OBJS)
	$(CC) $(LDFLAGS) -o $@ $^ $(LIBS)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.o: %.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -rf $(BUILD_DIR) $(PROG)