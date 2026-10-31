"""Synthesized soundtrack for DELIVERY IN 0.8 SECONDS (15 s). numpy/scipy only, no samples."""
import numpy as np
from scipy import signal
from scipy.io import wavfile

SR = 44100
DUR = 15.0
N = int(SR * DUR)
FPS = 24
rng = np.random.default_rng(11)
t = np.arange(N) / SR
L = np.zeros(N); Rr = np.zeros(N)

def fr(f): return (f - 1) / FPS

def add(sig, t0, pan=0.0, gain=1.0):
    i0 = int(t0 * SR)
    if i0 >= N or i0 < 0: return
    n = min(len(sig), N - i0)
    L[i0:i0 + n] += sig[:n] * gain * np.cos((pan + 1) * np.pi / 4)
    Rr[i0:i0 + n] += sig[:n] * gain * np.sin((pan + 1) * np.pi / 4)

def lp(x, fc, o=2):
    b, a = signal.butter(o, min(fc, SR / 2 - 100) / (SR / 2), "low"); return signal.lfilter(b, a, x)
def hp(x, fc, o=2):
    b, a = signal.butter(o, fc / (SR / 2), "high"); return signal.lfilter(b, a, x)
def bp(x, f1, f2, o=2):
    b, a = signal.butter(o, [f1 / (SR / 2), min(f2, SR / 2 - 100) / (SR / 2)], "band"); return signal.lfilter(b, a, x)

def saw(f, n, det=0.006, voices=3):
    x = np.arange(n) / SR; out = np.zeros(n)
    for v in range(voices):
        d = 1 + det * (v - (voices - 1) / 2)
        out += signal.sawtooth(2 * np.pi * f * d * x + rng.uniform(0, 6))
    return out / voices

def kick(dur=0.3, f0=130, f1=45):
    n = int(SR * dur); x = np.arange(n) / SR
    ph = 2 * np.pi * np.cumsum(f1 + (f0 - f1) * np.exp(-x * 28)) / SR
    return np.sin(ph) * np.exp(-x * 10)

def hat(dur=0.05):
    n = int(SR * dur); x = np.arange(n) / SR
    return hp(rng.standard_normal(n), 7000) * np.exp(-x * 80)

def snare(dur=0.15):
    n = int(SR * dur); x = np.arange(n) / SR
    return (bp(rng.standard_normal(n), 1500, 7000) * np.exp(-x * 28) + 0.4 * np.sin(2 * np.pi * 190 * x) * np.exp(-x * 30))

def bell(f, dur=1.2, bright=1.0):
    n = int(SR * dur); x = np.arange(n) / SR
    s = np.sin(2 * np.pi * f * x) + 0.45 * bright * np.sin(2 * np.pi * f * 2.76 * x) * np.exp(-x * 6) + 0.2 * np.sin(2 * np.pi * f * 5.4 * x) * np.exp(-x * 12)
    return s * np.exp(-x * 4.5) * np.minimum(1, x / 0.003)

def whoosh(dur=0.5, f0=500, f1=6000):
    n = int(SR * dur); x = np.arange(n) / SR
    nz = rng.standard_normal(n); out = np.zeros(n)
    k = 24
    for i in range(k):
        a, b = int(i * n / k), int((i + 1) * n / k)
        fc = f0 * (f1 / f0) ** (i / k)
        seg = bp(nz, fc * 0.7, fc * 1.4, 2)
        out[a:b] = seg[a:b]
    e = np.sin(np.pi * np.clip(x / dur, 0, 1)) ** 1.5
    return out * e * 3

# ---------------------------------------------------------------- music bed (150 bpm, flight f1..f215)
bpm = 150; beat = 60 / bpm
t_start, t_end = fr(1), fr(216)
bass_notes = [55.0, 55.0, 65.41, 49.0]  # A1 A1 C2 G1 per bar
arp = [220, 261.63, 329.63, 440, 329.63, 261.63, 220, 196]
b = 0
tt = t_start
step = 0
while tt < t_end:
    bar = (step // 8) % 4
    # kick on every beat (8th grid: steps even)
    if step % 2 == 0:
        add(kick(), tt, 0, 0.55)
    if step % 4 == 2:
        add(snare(), tt, 0, 0.28)
    add(hat(), tt, 0.3 if step % 2 else -0.3, 0.12 + 0.05 * (step % 2))
    # bass
    nn = int(SR * beat / 2 * 0.9)
    bs = lp(saw(bass_notes[bar], nn, 0.004, 2), 500) * np.exp(-np.arange(nn) / SR * 6)
    add(bs, tt, 0, 0.30)
    # arp
    f = arp[step % 8] * (2 if (step // 16) % 2 else 1)
    na = int(SR * beat / 2 * 0.8)
    xs = np.arange(na) / SR
    a = lp(saw(f, na, 0.008, 3), 3500 + 3000 * (tt - t_start) / (t_end - t_start)) * np.exp(-xs * 9)
    add(a, tt, 0.4 if step % 2 else -0.4, 0.14)
    tt += beat / 2
    step += 1
# riser into the reveal (warehouse -> city intro already covered); small fade of bed at f216 handled by end time

# ---------------------------------------------------------------- drone rotor hum (whole flight + arrival)
def rotor(t0, t1, f_a, f_b, gain):
    n = int(SR * (t1 - t0)); x = np.arange(n) / SR
    f = f_a + (f_b - f_a) * (x / max(x[-1], 1e-3))
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = (signal.sawtooth(ph) * 0.5 + np.sin(ph * 2) * 0.3)
    s *= (0.7 + 0.3 * np.sin(2 * np.pi * 34 * x))  # blade flutter
    e = np.minimum(1, x / 0.15) * np.minimum(1, (x[-1] - x) / 0.2)
    add(lp(s, 2500) * e, t0, 0, gain)
rotor(fr(1), fr(216), 150, 260, 0.10)
rotor(fr(216), fr(250), 200, 150, 0.12)
rotor(fr(250), fr(263), 150, 520, 0.12)   # zoom off, pitching up

# ---------------------------------------------------------------- whooshes at cuts
for c, p in zip([41, 86, 131, 176], [-0.6, 0.6, -0.6, 0.6]):
    add(whoosh(0.45, 400, 7000), fr(c) - 0.22, p, 0.55)
add(whoosh(0.7, 300, 9000), fr(216) - 0.4, 0, 0.5)   # arrival / brake
add(whoosh(0.55, 2500, 300), fr(216) - 0.05, 0, 0.35)
# launch boom at warehouse exit
add(whoosh(0.6, 200, 5000), fr(10), 0, 0.5)
add(kick(0.6, 90, 35), fr(34), 0, 0.9)

# ---------------------------------------------------------------- box drop + doorbell
n = int(SR * 0.25); x = np.arange(n) / SR
thump = (np.sin(2 * np.pi * 80 * x * np.exp(-x * 6)) * np.exp(-x * 18) + 0.3 * lp(rng.standard_normal(n), 600) * np.exp(-x * 40))
add(thump, fr(238), 0, 0.9)
add(bell(659.25, 1.3), fr(243), -0.1, 0.55)     # ding
add(bell(523.25, 1.8), fr(246), -0.1, 0.55)     # dong
# door creak/open
n = int(SR * 0.5); x = np.arange(n) / SR
cr = bp(signal.sawtooth(2 * np.pi * np.cumsum(180 + 80 * np.sin(2 * np.pi * 3 * x)) / SR), 300, 1400) * np.exp(-x * 4)
add(cr, fr(268), 0.2, 0.18)
# pickup rustle
add(lp(rng.standard_normal(int(SR * 0.3)), 2500) * np.exp(-np.arange(int(SR * 0.3)) / SR * 9), fr(300), 0.1, 0.25)

# ---------------------------------------------------------------- sad wah-wah on empty box (trombone-ish)
def wah(f0, f1, dur, vib=0.0):
    n = int(SR * dur); x = np.arange(n) / SR
    f = f0 + (f1 - f0) * (x / dur)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = signal.sawtooth(ph)
    cut = 500 + 900 * np.sin(np.pi * x / dur)
    out = np.zeros(n); k = 20
    for i in range(k):
        a, bb = int(i * n / k), int((i + 1) * n / k)
        out[a:bb] = lp(s, cut[a], 2)[a:bb]
    return out * np.minimum(1, x / 0.02) * np.minimum(1, (dur - x) / 0.04)
base = fr(308)
for i, (a, bb, d) in enumerate([(233, 220, 0.38), (220, 208, 0.38), (208, 196, 0.38), (196, 156, 0.9)]):
    add(wah(a, bb, d), base + i * 0.42, 0, 0.35)

# review UI ding + star taps
add(bell(1318.5, 0.5, 0.6), fr(314), 0.3, 0.35)
for i in range(5):
    add(bell(880 + 40 * i, 0.15, 0.2), fr(314) + 0.05 + i * 0.07, 0.3, 0.12)

# end card: soft chime
add(bell(783.99, 1.8), fr(330), 0, 0.30)
add(bell(1174.66, 2.2), fr(336), 0.1, 0.25)

# ---------------------------------------------------------------- master
Rr_ = Rr.copy(); L_ = L.copy()
for ch in (L_, Rr_):
    pass
# light reverb-ish via short feedback delays
def delay(x, d, g):
    k = int(SR * d); y = x.copy(); y[k:] += x[:-k] * g; return y
L_ = delay(L_, 0.083, 0.18); Rr_ = delay(Rr_, 0.101, 0.18)
fade = np.minimum(1, (DUR - t) / 0.5)
L_ *= fade; Rr_ *= fade
m = max(np.abs(L_).max(), np.abs(Rr_).max())
out = np.stack([L_, Rr_], 1) / m * 0.85
wavfile.write("/home/claude/speed/delivery_soundtrack.wav", SR, (out * 32767).astype(np.int16))
print("audio ok", out.shape, round(m, 3))
