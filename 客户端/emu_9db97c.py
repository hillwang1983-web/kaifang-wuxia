"""Straight-line emulator for loginp.exe FUN_009db97c (seed -> Real48 R) and the key step of FUN_009db8b4.

Only the instruction forms present in the function are implemented; anything else raises.
Numbers: every FPU constant / operand in this function is an integer, so Python ints are exact.
"""
import json, re, struct, sys, bisect

ASM = sys.argv[1] if len(sys.argv) > 1 else None

MASK = 0xFFFFFFFF
HEAP_BASE = 0x30000000


class Emu:
    def __init__(self, items):
        self.ins = []
        for r in items:
            m = re.match(r'0x([0-9a-f]+): (\S+)\s*(.*)$', r)
            self.ins.append((int(m.group(1), 16), m.group(2), m.group(3).strip()))
        self.idx = {a: i for i, (a, _, _) in enumerate(self.ins)}
        self.mem = {}                 # sparse byte memory
        self.reg = dict(EAX=0, EBX=0, ECX=0, EDX=0, ESI=0, EDI=0, EBP=0, ESP=0x00200000)
        self.fpu = []                 # list, top = last
        self.real48 = {}              # address -> exact number
        self.heap_next = HEAP_BASE
        self.strs = []                # sorted list of (handle, length)
        self.oob = []                 # out-of-bounds string reads
        self.steps = 0

    # ---------- memory ----------
    def rb(self, a):
        a &= MASK
        if a >= HEAP_BASE:
            i = bisect.bisect_right(self.strs, (a, 1 << 40)) - 1
            ok = False
            if i >= 0:
                h, l = self.strs[i]
                ok = h <= a <= h + l   # byte at h+l is the NUL terminator
            if not ok:
                self.oob.append(hex(a))
        return self.mem.get(a, 0)

    def wb(self, a, v):
        self.mem[a & MASK] = v & 0xFF

    def rd(self, a, n):
        return int.from_bytes(bytes(self.mem.get((a + i) & MASK, 0) for i in range(n)), 'little')

    def wr(self, a, v, n):
        for i, b in enumerate((v & ((1 << (8 * n)) - 1)).to_bytes(n, 'little')):
            self.mem[(a + i) & MASK] = b

    def new_str(self, data: bytes):
        h = self.heap_next
        self.heap_next += (len(data) + 8 + 15) & ~15
        self.wr(h - 4, len(data), 4)
        for i, b in enumerate(data):
            self.mem[h + i] = b
        self.mem[h + len(data)] = 0
        bisect.insort(self.strs, (h, len(data)))
        return h

    def str_bytes(self, h):
        if h == 0:
            return b''
        n = self.rd(h - 4, 4)
        return bytes(self.mem.get(h + i, 0) for i in range(n))

    # ---------- operands ----------
    REG32 = ('EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI', 'EBP', 'ESP')

    def ea(self, text):
        # [REG + REG*K + disp] with hex disp possibly written as 0xfffff8ec or -0x4
        t = text.strip()
        t = re.sub(r'^.*ptr\s*', '', t)
        m = re.match(r'(?:FS:)?\[(.*)\]$', t)
        inner = m.group(1).replace(' ', '')
        total = 0
        for sign, term in re.findall(r'([+-]?)([^+-]+)', inner):
            sgn = -1 if sign == '-' else 1
            if '*' in term:
                r, k = term.split('*')
                total += sgn * self.reg[r] * int(k, 0)
            elif term in self.reg:
                total += sgn * self.reg[term]
            else:
                total += sgn * int(term, 0)
        return total & MASK

    def get(self, op, size=32):
        op = op.strip()
        if op in self.reg:
            return self.reg[op]
        if op in ('AL', 'CL', 'DL', 'BL'):
            return self.reg['E' + op[0] + 'X'] & 0xFF
        if op in ('AX', 'CX', 'DX'):
            return self.reg['E' + op[0] + 'X'] & 0xFFFF
        if '[' in op:
            n = 4 if op.startswith('dword') else 2 if op.startswith('word') else 1 if op.startswith('byte') else 4
            return self.rd(self.ea(op), n)
        return int(op, 0) & MASK

    def put(self, op, v):
        op = op.strip()
        if op in self.reg:
            self.reg[op] = v & MASK
        elif op in ('AL', 'CL', 'DL', 'BL'):
            r = 'E' + op[0] + 'X'
            self.reg[r] = (self.reg[r] & ~0xFF) | (v & 0xFF)
        elif op in ('AX', 'CX', 'DX'):
            r = 'E' + op[0] + 'X'
            self.reg[r] = (self.reg[r] & ~0xFFFF) | (v & 0xFFFF)
        else:
            n = 4 if op.startswith('dword') else 2 if op.startswith('word') else 1 if op.startswith('byte') else 4
            self.wr(self.ea(op), v, n)

    @staticmethod
    def s32(v):
        v &= MASK
        return v - (1 << 32) if v & 0x80000000 else v

    def push(self, v):
        self.reg['ESP'] = (self.reg['ESP'] - 4) & MASK
        self.wr(self.reg['ESP'], v, 4)

    def pop(self):
        v = self.rd(self.reg['ESP'], 4)
        self.reg['ESP'] = (self.reg['ESP'] + 4) & MASK
        return v

    # ---------- FPU memory operand ----------
    def fload(self, op):
        a = self.ea(op)
        if op.startswith('float'):
            return struct.unpack('<f', self.rd(a, 4).to_bytes(4, 'little'))[0]
        if op.startswith('double'):
            return struct.unpack('<d', self.rd(a, 8).to_bytes(8, 'little'))[0]
        raise RuntimeError(op)

    def fstore(self, op, v):
        a = self.ea(op)
        if op.startswith('float'):
            self.wr(a, int.from_bytes(struct.pack('<f', float(v)), 'little'), 4)
        elif op.startswith('double'):
            self.wr(a, int.from_bytes(struct.pack('<d', float(v)), 'little'), 8)
        else:
            raise RuntimeError(op)

    @staticmethod
    def rnd(v):
        # FISTP in default round-to-nearest-even
        return int(round(v))

    # ---------- calls ----------
    def call(self, target):
        r = self.reg
        if target == 0x403fdc:                      # FLD Real48 [EAX]
            self.fpu.append(self.real48.get(r['EAX'], 0))
        elif target == 0x40400c:                    # FSTP Real48 [EAX]
            v = self.fpu.pop()
            if v != int(v) or abs(v) >= 1 << 39:
                raise RuntimeError('Real48 store not exact: %r' % v)
            self.real48[r['EAX']] = int(v)
        elif target == 0x40520c:                    # LStrFromChar(EAX=&dst, DL=char)
            self.wr(r['EAX'], self.new_str(bytes([r['EDX'] & 0xFF])), 4)
        elif target == 0x4052fc:                    # LStrCat(EAX=&dst, EDX=src)
            if r['EDX'] == 0:
                return
            dst = self.rd(r['EAX'], 4)
            self.wr(r['EAX'], self.new_str(self.str_bytes(dst) + self.str_bytes(r['EDX'])), 4)
        elif target == 0x40502c:                    # LStrClr(EAX=&var)
            self.wr(r['EAX'], 0, 4)
        elif target in (0x4054dc, 0x405050):        # AddRef / array clr -> no-op
            pass
        else:
            raise RuntimeError('unknown call %x' % target)

    # ---------- main loop ----------
    def run(self, start=0x9db97c, stop_at=0x9efd44):
        pc = self.idx[start]
        r = self.reg
        while True:
            addr, mn, op = self.ins[pc]
            self.steps += 1
            pc += 1
            if mn == 'RET' or addr == stop_at:
                return
            a = [x.strip() for x in re.split(r',(?![^\[]*\])', op)] if op else []
            if mn == 'PUSH':
                if op.startswith('dword ptr FS'):
                    self.push(0)
                else:
                    self.push(self.get(a[0]))
            elif mn == 'POP':
                self.put(a[0], self.pop())
            elif mn == 'MOV':
                if a[0].startswith('dword ptr FS') or a[0].startswith('FS'):
                    continue
                self.put(a[0], self.get(a[1]))
            elif mn == 'MOVZX':
                self.put(a[0], self.get(a[1]) & 0xFF)
            elif mn == 'LEA':
                self.put(a[0], self.ea(a[1]))
            elif mn == 'XOR':
                self.put(a[0], self.get(a[0]) ^ self.get(a[1]))
            elif mn == 'ADD':
                self.put(a[0], self.get(a[0]) + self.get(a[1]))
            elif mn == 'SUB':
                self.put(a[0], self.get(a[0]) - self.get(a[1]))
            elif mn == 'INC':
                self.put(a[0], self.get(a[0]) + 1)
            elif mn == 'DEC':
                self.put(a[0], self.get(a[0]) - 1)
            elif mn == 'NEG':
                self.put(a[0], -self.get(a[0]))
            elif mn == 'SHL':
                self.put(a[0], self.get(a[0]) << int(a[1], 0))
            elif mn == 'IMUL':
                self.put(a[0], self.s32(self.get(a[1])) * self.s32(self.get(a[2])))
            elif mn == 'DIV':
                d = self.get(a[0])
                n = (r['EDX'] << 32) | r['EAX']
                r['EAX'], r['EDX'] = (n // d) & MASK, (n % d) & MASK
            elif mn == 'JNZ':
                if r['ECX'] != 0:
                    pc = self.idx[int(a[0], 0)]
            elif mn == 'CALL':
                self.call(int(a[0], 0))
            elif mn == 'WAIT':
                pass
            elif mn == 'FILD':
                n = 8 if a[0].startswith('qword') else 4
                v = self.rd(self.ea(a[0]), n)
                if v >> (8 * n - 1):
                    v -= 1 << (8 * n)
                self.fpu.append(v)
            elif mn == 'FLD':
                self.fpu.append(self.fload(a[0]))
            elif mn == 'FADD':
                self.fpu[-1] = self.fpu[-1] + self.fload(a[0])
            elif mn == 'FSUB':
                self.fpu[-1] = self.fpu[-1] - self.fload(a[0])
            elif mn == 'FSUBR':
                self.fpu[-1] = self.fload(a[0]) - self.fpu[-1]
            elif mn == 'FMUL':
                self.fpu[-1] = self.fpu[-1] * self.fload(a[0])
            elif mn == 'FADDP':
                s0 = self.fpu.pop(); self.fpu[-1] = self.fpu[-1] + s0
            elif mn == 'FSUBP':                     # ST1 = ST1 - ST0
                s0 = self.fpu.pop(); self.fpu[-1] = self.fpu[-1] - s0
            elif mn == 'FSUBRP':                    # ST1 = ST0 - ST1
                s0 = self.fpu.pop(); self.fpu[-1] = s0 - self.fpu[-1]
            elif mn == 'FSTP':
                self.fstore(a[0], self.fpu.pop())
            elif mn == 'FISTP':
                self.wr(self.ea(a[0]), self.rnd(self.fpu.pop()), 8)
            else:
                raise RuntimeError('unhandled %x %s %s' % (addr, mn, op))


def derive(items, seed: bytes, trace=False):
    e = Emu(items)
    e.reg['EBP'] = 0x00400000
    e.reg['ESP'] = 0x003FF000
    h = e.new_str(seed)
    e.reg['EAX'] = h
    e.run()
    R = e.real48.get(0x205250c, 0)
    return e, R


def key_from_R(R):
    # FUN_009db8b4: (Trunc(R) + 0xa3) llmod 0xd9, low byte stored at obj+7
    t = int(R)  # truncation toward zero, like FISTP with RC=chop
    x = t + 0xA3
    q = abs(x) % 0xD9
    rem = q if x >= 0 else -q            # llmod keeps the sign of the dividend
    return rem & 0xFF, x, rem


if __name__ == '__main__':
    items = json.load(open(ASM, encoding='utf8'))
    seeds = [bytes.fromhex(s) for s in sys.argv[2:]] or [bytes([1, 2, 3, 4])]
    for s in seeds:
        e, R = derive(items, s)
        k, x, rem = key_from_R(R)
        lens = {hex(a): len(e.str_bytes(e.rd(a, 4))) for a in (0x2052508, 0x20524dc, 0x2052514)}
        print('seed', s.hex(), '-> R =', R, ' Trunc+0xa3 =', x, ' rem =', rem, ' key byte = 0x%02x' % k,
              '| steps', e.steps, '| str lens', lens, '| OOB reads', len(e.oob), e.oob[:3])
