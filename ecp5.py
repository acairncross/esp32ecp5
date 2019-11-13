# micropython ESP32
# ECP5 JTAG programmer

# AUTHOR=EMARD
# LICENSE=BSD

import time
from machine import SPI, Pin

class ecp5:

  def init_pinout_jtag(self):
    self.gpio_tms = 21
    self.gpio_tck = 18
    self.gpio_tdi = 23
    self.gpio_tdo = 19

  # if JTAG is directed to SD card pins
  # then bus traffic can be monitored using
  # JTAG slave OLED HEX decoder:
  # https://github.com/emard/ulx3s-misc/tree/master/examples/jtag_slave/proj/ulx3s_jtag_hex_passthru_v
  #def init_pinout_sd(self):
  #  self.gpio_tms = 15
  #  self.gpio_tck = 14
  #  self.gpio_tdi = 13
  #  self.gpio_tdo = 12


  def bitbang_jtag_on(self):
    self.led=Pin(self.gpio_led,Pin.OUT)
    self.tms=Pin(self.gpio_tms,Pin.OUT)
    self.tck=Pin(self.gpio_tck,Pin.OUT)
    self.tdi=Pin(self.gpio_tdi,Pin.OUT)
    self.tdo=Pin(self.gpio_tdo,Pin.IN)

  def bitbang_jtag_off(self):
    self.led=Pin(self.gpio_led,Pin.IN)
    self.tms=Pin(self.gpio_tms,Pin.IN)
    self.tck=Pin(self.gpio_tck,Pin.IN)
    self.tdi=Pin(self.gpio_tdi,Pin.IN)
    self.tdo=Pin(self.gpio_tdo,Pin.IN)
    a = self.led.value()
    a = self.tms.value()
    a = self.tck.value()
    a = self.tdo.value()
    a = self.tdi.value()
    del self.led
    del self.tms
    del self.tck
    del self.tdi
    del self.tdo

  # initialize both hardware accelerated SPI
  # software SPI on the same pins
  def spi_jtag_on(self):
    self.hwspi=SPI(self.spi_channel, baudrate=self.spi_freq, polarity=1, phase=1, bits=8, firstbit=SPI.MSB, sck=Pin(self.gpio_tck), mosi=Pin(self.gpio_tdi), miso=Pin(self.gpio_tdo))
    self.swspi=SPI(-1, baudrate=self.spi_freq, polarity=1, phase=1, bits=8, firstbit=SPI.MSB, sck=Pin(self.gpio_tck), mosi=Pin(self.gpio_tdi), miso=Pin(self.gpio_tdo))

  def spi_jtag_off(self):
    del self.hwspi
    del self.swspi

  def __init__(self):
    self.spi_freq = 30000000 # Hz JTAG clk frequency
    # -1 for JTAG over SOFT SPI slow, compatibility
    #  1 or 2 for JTAG over HARD SPI fast
    #  2 is preferred as it has default pinout wired
    self.flash_write_size = 256
    self.flash_erase_size = 4096 # no ESP32 memory for more at flash_loop_clever()
    flash_erase_cmd = { 4096:0x20, 32768:0x52, 65536:0xD8 } # erase commands from FLASH PDF
    self.flash_erase_cmd = flash_erase_cmd[self.flash_erase_size]
    self.spi_channel = 2 # -1 soft, 1:sd, 2:jtag
    self.gpio_led = 5
    self.progress = False
    self.init_pinout_jtag()
    #self.init_pinout_sd()

#  def __call__(self):
#    some_variable = 0
    
  # print bytes reverse - appears the same as in SVF file
  def print_hex_reverse(self, block, head="", tail="\n"):
    print(head, end="")
    for n in range(len(block)):
      print("%02X" % block[len(block)-n-1], end="")
    print(tail, end="")
  
  # convert unsigned integer to n-bytes
  def uint(self, n, u):
    r = b""
    for i in range(n//8):
      r += bytes([u & 0xFF])
      u >>= 8
    return r
  
  def bitreverse(self,x):
    y = 0
    for i in range(8):
        if (x >> (7 - i)) & 1 == 1:
            y |= (1 << i)
    return y
  
  def send_tms(self, tms):
    if tms:
      self.tms.on()
    else:
      self.tms.off()
    self.tck.off()
    self.tck.on()

  def send_bit(self, tdi, tms):
    if tdi:
      self.tdi.on()
    else:
      self.tdi.off()
    if tms:
      self.tms.on()
    else:
      self.tms.off()
    self.tck.off()
    self.tck.on()

  def send_read_data_byte(self, val, last):
    byte = 0
    for nf in range(8):
      self.send_bit((val >> nf) & 1, (last & int((nf == 7) == True)))
      byte |= self.tdo.value() << nf
    return byte

  def send_read_data_byte_reverse(self, val, last):
    byte = 0
    for nf in range(8):
      self.send_bit((val >> (7-nf)) & 1, (last & int((nf == 7) == True)))
      byte |= self.tdo.value() << nf
    return byte
    
  # TAP to "reset" state
  def reset_tap(self):
    for n in range(6):
      self.send_tms(1) # -> Test Logic Reset

  # TAP should be in "idle" state
  # TAP returns to "select DR scan" state
  def runtest_idle(self, count, duration):
    leave=time.ticks_ms() + int(duration*1000)
    for n in range(count):
      self.send_tms(0) # -> idle
    while time.ticks_ms() < leave:
      self.send_tms(0) # -> idle
    self.send_tms(1) # -> select DR scan
  
  # send SIR command (bytes)
  # TAP should be in "select DR scan" state
  # TAP returns to "select DR scan" state
  def sir(self, sir, idle=False):
    self.send_tms(1) # -> select IR scan
    self.send_tms(0) # -> capture IR
    self.send_tms(0) # -> shift IR
    for byte in sir[:-1]:
      self.send_read_data_byte(byte,0) # not last
    self.send_read_data_byte(sir[-1],1) # last, exit 1 DR
    self.send_tms(0) # -> pause IR
    self.send_tms(1) # -> exit 2 IR
    self.send_tms(1) # -> update IR
    if idle:
      #self.send_tms(0) # -> idle, disabled here as runtest_idle does the same
      self.runtest_idle(idle[0]+1, idle[1])
    else:
      self.send_tms(1) # -> select DR scan

  # send SDR data (bytes) and print result
  # if (response & mask)!=expected then report TDO mismatch
  # TAP should be in "select DR scan" state
  # TAP returns to "select DR scan" state
  # return value "True" if error, "False" if no error
  def sdr(self, sdr, mask=False, expected=False, message="", drpause=False, idle=False):
    self.send_tms(0) # -> capture DR
    self.send_tms(0) # -> shift DR
    tdo_mismatch = False
    response = b""
    if expected:
      for byte in sdr[:-1]:
        response += bytes([self.send_read_data_byte(byte,0)]) # not last
      response += bytes([self.send_read_data_byte(sdr[-1],1)]) # last, exit 1 DR
      if mask:
        for i in range(len(expected)):
          if (response[i] & mask[i]) != expected[i]:
            tdo_mismatch = True
      else:
        for i in range(len(expected)):
          if response[i] != expected[i]:
            tdo_mismatch = True
      if tdo_mismatch:
        if mask:
          self.print_hex_reverse(response, head="0x", tail=" & ")
          self.print_hex_reverse(mask, head="0x", tail=" != ")
        else:
          self.print_hex_reverse(response, head="0x", tail=" != ")
        self.print_hex_reverse(expected, head="0x", tail="")
        print(" ("+message+")")
    else: # no print, faster
      for byte in sdr[:-1]:
        response += bytes([self.send_read_data_byte(byte,0)]) # not last
      response += bytes([self.send_read_data_byte(sdr[-1],1)]) # last, exit 1 DR
    self.send_tms(0) # -> pause DR
    if drpause:
      time.sleep(drpause)
    self.send_tms(1) # -> exit 2 DR
    self.send_tms(1) # -> update DR
    if idle:
      #self.send_tms(0) # -> idle, disabled here as runtest_idle does the same
      self.runtest_idle(idle[0]+1, idle[1])
    else:
      self.send_tms(1) # -> select DR scan
    return response

  def idcode(self):
    import struct
    self.bitbang_jtag_on()
    self.led.on()
    self.reset_tap()
    self.runtest_idle(1,0)
    self.sir(b"\xE0")
    id_bytes = self.sdr(self.uint(32,0))
    self.led.off()
    self.bitbang_jtag_off()
    return struct.unpack("<I", id_bytes)
  
  # call this before sending the bitstram
  # FPGA will enter programming mode
  # after this TAP will be in "shift DR" state
  def prog_open(self):
    self.spi_jtag_on()
    self.hwspi.init(baudrate=self.spi_freq//2) # workarounds ESP32 micropython SPI bugs
    self.bitbang_jtag_on()
    self.led.on()
    self.reset_tap()
    self.runtest_idle(1,0)
    #self.sir(b"\xE0") # read IDCODE
    #self.sdr(self.uint(32,0), expected=self.uint(32,0), message="IDCODE")
    self.sir(b"\x1C") # LSC_PRELOAD: program Bscan register
    self.sdr([0xFF for i in range(64)])
    self.sir(b"\xC6") # ISC ENABLE: Enable SRAM programming mode
    self.sdr(b"\x00", idle=(2,1.0E-2))
    self.sir(b"\x3C", idle=(2,1.0E-3)) # LSC_READ_STATUS
    self.sdr(self.uint(32,0), mask=self.uint(32,0x00024040), expected=self.uint(32,0), message="FAIL status")
    self.sir(b"\x0E") # ISC_ERASE: Erase the SRAM
    self.sdr(b"\x01", idle=(2,1.0E-2))
    self.sir(b"\x3C", idle=(2,1.0E-3)) # LSC_READ_STATUS
    self.sdr(self.uint(32,0), mask=self.uint(32,0x0000B000), expected=self.uint(32,0), message="FAIL status")
    self.sir(b"\x46") # LSC_INIT_ADDRESS
    self.sdr(b"\x01", idle=(2,1.0E-2))
    self.sir(b"\x7A") # LSC_BITSTREAM_BURST
    # ---------- bitstream begin -----------
    # manually walk the TAP
    # we will be sending one long DR command
    self.send_tms(0) # -> capture DR
    self.send_tms(0) # -> shift DR
    # switch from bitbanging to SPI mode
    self.hwspi.init(baudrate=self.spi_freq) # 1 TCK-glitch
    # we are lucky that format of the bitstream tolerates
    # any leading and trailing junk bits. If it weren't so,
    # HW SPI JTAG acceleration wouldn't work.
    # to upload the bitstream:
    # FAST SPI mode
    #self.hwspi.write(block)
    # SLOW bitbanging mode
    #for byte in block:
    #  self.send_read_data_byte_reverse(byte,0)

  # call this after uploading all of the bitstream blocks,
  # this will exit FPGA programming mode and start the bitstream
  def prog_close(self):
    # switch from hardware SPI to bitbanging
    self.bitbang_jtag_on() # 1 TCK-glitch
    self.send_tms(1) # -> exit 1 DR
    self.send_tms(0) # -> pause DR
    self.send_tms(1) # -> exit 2 DR
    self.send_tms(1) # -> update DR
    #self.send_tms(0) # -> idle, disabled here as runtest_idle does the same
    self.runtest_idle(100, 1.0E-2)
    # ---------- bitstream end -----------
    self.sir(b"\xC0", idle=(2,1.0E-3)) # read usercode
    self.sdr(self.uint(32,0), expected=self.uint(32,0), message="FAIL usercode")
    self.sir(b"\x26", idle=(2,2.0E-1)) # ISC DISABLE
    self.sir(b"\xFF", idle=(2,1.0E-3)) # BYPASS
    self.sir(b"\x3C") # LSC_READ_STATUS
    self.sdr(self.uint(32,0), mask=self.uint(32,0x00002100), expected=self.uint(32,0x00000100), message="FAIL bitstream")
    self.spi_jtag_off()
    self.reset_tap()
    self.led.off()
    self.bitbang_jtag_off()

  # call this before sending the flash image
  # FPGA will enter flashing mode
  # TAP should be in "select DR scan" state
  def flash_open(self):
    self.spi_jtag_on()
    self.hwspi.init(baudrate=self.spi_freq//2) # workarounds ESP32 micropython SPI bugs
    self.bitbang_jtag_on()
    self.led.on()
    self.reset_tap()
    self.runtest_idle(1,0)
    #self.sir(b"\xE0") # read IDCODE
    #self.sdr(self.uint(32,0), expected=self.uint(32,0), message="IDCODE")
    self.sir(b"\x1C") # LSC_PRELOAD: program Bscan register
    self.sdr([0xFF for i in range(64)])
    self.sir(b"\xC6") # ISC ENABLE: Enable SRAM programming mode
    self.sdr(b"\x00", idle=(2,1.0E-2))
    self.sir(b"\x3C", idle=(2,1.0E-3)) # LSC_READ_STATUS
    self.sdr(self.uint(32,0), mask=self.uint(32,0x00024040), expected=self.uint(32,0), message="FAIL status")
    self.sir(b"\x0E") # ISC_ERASE: Erase the SRAM
    self.sdr(b"\x01", idle=(2,1.0E-2))
    self.sir(b"\x3C", idle=(2,1.0E-3)) # LSC_READ_STATUS
    self.sdr(self.uint(32,0), mask=self.uint(32,0x0000B000), expected=self.uint(32,0), message="FAIL status")
    self.reset_tap()
    self.runtest_idle(1,0)
    self.sir(b"\xFF", idle=(32,0)) # BYPASS
    self.sir(b"\x3A") # LSC_PROG_SPI
    self.sdr(self.uint(16,0x68FE), idle=(32,0))
    # ---------- flashing begin -----------
    # 0x60 and other SPI flash commands here are bitreverse() values
    # of flash commands found in SPI FLASH datasheet.
    # e.g. 0x1B here is actually 0xD8 in datasheet, 0x60 is is 0x06 etc.

  def flash_wait_status(self):
    retry=10
    while retry > 0:
      status = self.sdr(self.uint(16, 0x00A0)) # READ STATUS REGISTER
      if (status[1] & 0xC1) == 0:
        break
      time.sleep(0.1)
      retry -= 1
    if retry <= 0:
      self.sdr(self.uint(16, 0x00A0), mask=self.uint(16, 0xC100), expected=self.uint(16,0x0000)) # READ STATUS REGISTER

  def flash_erase_block(self, addr=0):
    import struct
    print("from 0x%06X erase %d bytes" % (addr, self.flash_erase_size))
    self.sdr(b"\x60") # SPI WRITE ENABLE
    # some chips won't clear WIP without this:
    self.sdr(self.uint(16, 0x00A0), mask=self.uint(16, 0xC100), expected=self.uint(16,0x4000)) # READ STATUS REGISTER
    sdr = struct.pack(">I", (self.flash_erase_cmd << 24) | (addr & 0xFFFFFF))
    self.send_tms(0) # -> capture DR
    self.send_tms(0) # -> shift DR
    self.swspi.write(sdr[:-1])
    self.send_read_data_byte_reverse(sdr[-1],1) # last byte -> exit 1 DR
    self.send_tms(0) # -> pause DR
    self.send_tms(1) # -> exit 2 DR
    self.send_tms(1) # -> update DR
    self.send_tms(1) # -> select DR scan
    #self.sdr(self.uint(32, (self.bitreverse(addr//self.flash_erase_size)<<8) | self.bitreverse(self.flash_erase_cmd)))
    self.flash_wait_status()

  def flash_write_block(self, block, addr=0):
    import struct
    self.sdr(b"\x60") # SPI WRITE ENABLE
    # self.bitreverse(0x40) = 0x02 -> 0x02000000
    sdr = struct.pack(">I", 0x02000000 | (addr & 0xFFFFFF)) + block
    self.send_tms(0) # -> capture DR
    self.send_tms(0) # -> shift DR
    self.swspi.write(sdr[:-1]) # whole block except last byte
    self.send_read_data_byte_reverse(sdr[-1],1) # last byte -> exit 1 DR
    self.send_tms(0) # -> pause DR
    self.send_tms(1) # -> exit 2 DR
    self.send_tms(1) # -> update DR
    self.send_tms(1) # -> select DR scan
    self.flash_wait_status()

  def flash_read_block(self, addr=0, length=0):
    import struct
    # 0x03 is SPI flash read command
    sdr = struct.pack(">I", 0x03000000 | (addr & 0xFFFFFF))
    self.send_tms(0) # -> capture DR
    self.send_tms(0) # -> shift DR
    self.swspi.write(sdr) # send SPI FLASH read command and address
    block = self.swspi.read(length) # read whole block
    self.send_read_data_byte_reverse(0,1) # dummy read byte -> exit 1 DR
    self.send_tms(0) # -> pause DR
    self.send_tms(1) # -> exit 2 DR
    self.send_tms(1) # -> update DR
    self.send_tms(1) # -> select DR scan
    return block

  def flash_fast_read_block(self, addr=0, length=0):
    import struct
    # 0x0B is SPI flash fast read command
    sdr = struct.pack(">I", 0x0B000000 | (addr & 0xFFFFFF))
    self.send_tms(0) # -> capture DR
    self.send_tms(0) # -> shift DR
    self.swspi.write(sdr) # send SPI FLASH read command and address
    # fast read after address, should read 8 dummy cycles
    # this is a chance for TCK glitch workaround:
    # first 7 cycles will be done in bitbang mode
    # then switch to hardware SPI mode
    # will add 1 more TCK-glitch cycle
    for i in range(7):
      self.tck.off()
      self.tck.on()
    # switch from bitbanging to SPI mode
    self.hwspi.init(baudrate=self.spi_freq) # 1 TCK-glitch
    block = self.hwspi.read(length) # retrieve whole block
    # switch from SPI to bitbanging mode
    self.hwspi.init(baudrate=self.spi_freq//2) # TCK-glitch
    self.bitbang_jtag_on()
    self.send_read_data_byte_reverse(0,1) # dummy read byte -> exit 1 DR
    self.send_tms(0) # -> pause DR
    self.send_tms(1) # -> exit 2 DR
    self.send_tms(1) # -> update DR
    self.send_tms(1) # -> select DR scan
    return block

  # call this after uploading all of the flash blocks,
  # this will exit FPGA flashing mode and start the bitstream
  def flash_close(self):
    # switch from SPI to bitbanging
    # ---------- flashing end -----------
    self.sdr(b"\x20") # SPI WRITE DISABLE
    self.sir(b"\xFF", idle=(100,1.0E-3)) # BYPASS
    self.sir(b"\x26", idle=(2,2.0E-1)) # ISC DISABLE
    self.sir(b"\xFF", idle=(2,1.0E-3)) # BYPASS
    self.sir(b"\x79") # LSC_REFRESH reload the bitstream from flash
    self.sdr(b"\x00\x00\x00", idle=(2,1.0E-1))
    self.spi_jtag_off()
    self.reset_tap()
    self.led.off()
    self.bitbang_jtag_off()
      
  def stopwatch_start(self):
    self.stopwatch_ms = time.ticks_ms()
  
  def stopwatch_stop(self, bytes_uploaded):
    elapsed_ms = time.ticks_ms() - self.stopwatch_ms
    transfer_rate_MBps = 0
    if elapsed_ms > 0:
      transfer_rate_MBps = bytes_uploaded / (elapsed_ms * 1024 * 1.024)
    print("%d bytes uploaded in %.3f s (%.3f MB/s)" % (bytes_uploaded, elapsed_ms/1000, transfer_rate_MBps))

  def program_loop(self, filedata, blocksize=16384):
    self.prog_open()
    bytes_uploaded = 0
    self.stopwatch_start()
    while True:
      block = filedata.read(blocksize)
      if block:
        self.hwspi.write(block)
        if self.progress:
          print(".",end="")
        bytes_uploaded += len(block)
      else:
        if self.progress:
          print("*")
        break
    self.stopwatch_stop(bytes_uploaded)
    self.prog_close()

  def program_file(self, filename, gz=False):
    with open(filename, "rb") as filedata:
      if gz:
        import uzlib
        self.program_loop(uzlib.DecompIO(filedata,31),blocksize=4096)
      else:
        self.program_loop(filedata,blocksize=16384)

  def program_web(self, url):
    import socket
    _, _, host, path = url.split('/', 3)
    addr = socket.getaddrinfo(host, 80)[0][-1]
    s = socket.socket()
    s.connect(addr)
    s.send(bytes('GET /%s HTTP/1.0\r\nHost: %s\r\n\r\n' % (path, host), 'utf8'))
    self.program_loop(s)
    s.close()

  def flash_read(self, addr=0, length=0):
    self.flash_open()
    data = self.flash_fast_read_block(addr=addr, length=length)
    self.flash_close()
    return data

  # force erase and write
  # wears flash even if overwriting the same data
  # needs less buffering, can use 64K erase block
  def flash_loop_force(self, filedata, addr=0):
    addr_mask = self.flash_erase_size-1
    if addr & addr_mask:
      print("addr must be rounded to flash_erase_size = %d bytes (& 0x%06X)" % (self.flash_erase_size, 0xFFFFFF & ~addr_mask))
      return
    addr = addr & 0xFFFFFF & ~addr_mask # rounded to even 64K (erase block)
    self.flash_open()
    bytes_uploaded = 0
    self.stopwatch_start()
    while True:
      block = filedata.read(self.flash_write_size)
      if block:
        if (bytes_uploaded % self.flash_erase_size) == 0:
          self.flash_erase_block(addr=addr+bytes_uploaded)
        self.flash_write_block(block, addr=addr+bytes_uploaded)
        if self.progress:
          print(".",end="")
        bytes_uploaded += len(block)
      else:
        if self.progress:
          print("*")
        break
    self.stopwatch_stop(bytes_uploaded)
    self.flash_close()

  # clever = read-compare-erase-write
  # prevents flash wear when overwriting the same data
  # needs more buffers: 4K erase block is max that fits on ESP32
  # TODO reduce buffer usage
  def flash_loop_clever(self, filedata, addr=0):
    addr_mask = self.flash_erase_size-1
    if addr & addr_mask:
      print("addr must be rounded to flash_erase_size = %d bytes (& 0x%06X)" % (self.flash_erase_size, 0xFFFFFF & ~addr_mask))
      return
    addr = addr & 0xFFFFFF & ~addr_mask # rounded to even 64K (erase block)
    self.flash_open()
    bytes_uploaded = 0
    self.stopwatch_start()
    while True:
      file_block = filedata.read(self.flash_erase_size)
      if file_block:
        flash_block = self.flash_fast_read_block(addr=addr+bytes_uploaded, length=len(file_block))
        must_erase = False
        must_write = False # TODO must_write[i] for each 256 byte block
        for i in range(len(file_block)):
          if (flash_block[i] & file_block[i]) != file_block[i]:
            must_erase = True
        if must_erase: # erase will reset all bytes to 0xFF
          for i in range(len(file_block)):
            if file_block[i] != 0xFF:
              must_write = True
        else: # no erase
          for i in range(len(file_block)):
            if flash_block[i] != file_block[i]:
              must_write = True
        if must_erase:
          self.flash_erase_block(addr=addr+bytes_uploaded)
        if must_write:
          write_addr = addr+bytes_uploaded
          block_addr = 0
          next_block_addr = 0
          while next_block_addr < len(file_block):
            next_block_addr = block_addr+self.flash_write_size
            self.flash_write_block(file_block[block_addr:next_block_addr], addr=write_addr)
            write_addr += self.flash_write_size
            block_addr = next_block_addr
        if self.progress:
          print(".",end="")
        bytes_uploaded += len(file_block)
      else:
        if self.progress:
          print("*")
        break
    self.stopwatch_stop(bytes_uploaded)
    self.flash_close()

  def flash_file(self, filename, addr=0, gz=False):
    with open(filename, "rb") as filedata:
      if gz:
        import uzlib
        self.flash_loop_clever(uzlib.DecompIO(filedata,31),addr=addr)
      else:
        self.flash_loop_clever(filedata,addr=addr)

  def flash_web(self, url, addr=0):
    import socket
    _, _, host, path = url.split('/', 3)
    iaddr = socket.getaddrinfo(host, 80)[0][-1]
    s = socket.socket()
    s.connect(iaddr)
    s.send(bytes('GET /%s HTTP/1.0\r\nHost: %s\r\n\r\n' % (path, host), 'utf8'))
    # FIXME this simple GET request won't trasparently download binary file
    self.flash_loop_clever(s, addr=addr)
    s.close()

# easier command typing
def idcode():
  return ecp5().idcode()

def program(filepath):
  gz=filepath.endswith(".gz")
  if filepath.startswith("http://"):
    ecp5().program_web(filepath)
  else:
    ecp5().program_file(filepath, gz=gz)

def flash(filepath, addr=0):
  gz=filepath.endswith(".gz")
  if filepath.startswith("http://"):
    ecp5().flash_web(filepath, addr=addr)
  else:
    ecp5().flash_file(filepath, addr=addr, gz=gz)

def flash_read(addr=0, length=1):
  return ecp5().flash_read(addr=addr, length=length)

def passthru():
  idcode = ecp5().idcode()
  if idcode != 0 and idcode != 0xFFFFFFFF:
    filename = "passthru%08X.bit.gz" % idcode
    print("program \"%s\"" % filename)
    ecp5().program_file(filename, gz=True)

print("usage:")
print("ecp5.flash(\"blink.bit\", addr=0x000000)")
print("ecp5.flash_read(addr=0x000000, length=1)")
print("ecp5.program(\"blink.bit\")")
print("ecp5.program(\"blink.bit.gz\") # gzip blink.bit")
print("ecp5.program(\"http://192.168.4.2/blink.bit\")")
print("ecp5.passthru()")
print("\"0x%08X\" % ecp5.idcode()")
print("0x%08X" % idcode())
#flash("blink.bit")
#program("blink.bit")
#program("http://192.168.4.2/blink.bit")
