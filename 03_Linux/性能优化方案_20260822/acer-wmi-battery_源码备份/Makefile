obj-m += acer-wmi-battery.o
PWD := $(CURDIR)

# KDIR: 内核构建目录。可由外部传入，默认用当前运行内核。
# ------------------------------------------------------------------
# ⚠️ 2026-08-29 修复：原版硬编码 $(shell uname -r)，忽略 dkms.conf 传入的 KDIR，
# 导致 DKMS 在「内核升级但尚未重启」时自动构建，会按 uname -r（仍是旧内核）编译，
# 却安装到新内核目录 → vermagic 不匹配 → 模块加载失败。
# 这正是 acer-wmi-battery 在 0818/0821/0829 反复失效的深层原因之一。
# 修复后：DKMS 传 KDIR=${kernel_source_dir} 时被正确采用，自动重建才真正有效。
# ------------------------------------------------------------------
KDIR ?= /lib/modules/$(shell uname -r)/build

all:
	make -C $(KDIR) M=$(PWD) modules

clean:
	make -C $(KDIR) M=$(PWD) clean
