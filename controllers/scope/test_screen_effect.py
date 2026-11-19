import struct
import unittest
import zlib
from screen_effect import chunks, png_chunk, recolor
from scope_io import ScopeError

def synthetic(inactive_ch2=False,unknown=False):
    p=[(255,255,255)]*256
    for start,full in ((1,(0,0,255)),(17,(0,255,255))):
        for step in range(15):
            a=step/14
            p[start+step]=tuple(round(255+a*(v-255)) for v in full)
    p[64]=(0,0,0);p[65]=(0,0,153);p[71]=(255,119,0)
    if inactive_ch2:
        for i in range(17,32):p[i]=(255,255,255)
    if unknown:p[15]=(0,0,0)
    rows=[bytearray(640) for _ in range(480)]
    for x,idx in ((100,15),(101,31),(102,64),(103,65),(104,71),(105,8)):
        rows[100][x]=idx
    rows[5][100]=15  # Same channel index in text area must remain unchanged.
    raw=b''.join(b'\0'+row for row in rows)
    png=(b'\x89PNG\r\n\x1a\n'+png_chunk(b'IHDR',struct.pack('>IIBBBBB',640,480,8,3,0,0,0))+
         png_chunk(b'PLTE',b''.join(bytes(c) for c in p))+png_chunk(b'IDAT',zlib.compress(raw))+png_chunk(b'IEND',b''))
    return png,p,rows

class TraceEffectTests(unittest.TestCase):
    def test_only_trace_pixels_inside_plot_change(self):
        png,p,rows=synthetic()
        out,count=recolor(png,{'ch1':'#ff0000','ch2':'#00ff00'})
        packed=zlib.decompress(b''.join(v for k,v in chunks(out) if k==b'IDAT'))
        def rgb(x,y):return tuple(packed[y*1921+1+x*3:y*1921+4+x*3])
        self.assertEqual(rgb(100,100),(255,0,0))
        self.assertEqual(rgb(101,100),(0,255,0))
        self.assertEqual(rgb(105,100),(255,128,128))  # Half-intensity preserved on white.
        self.assertEqual(rgb(103,100),(255,0,0))  # CH1 text matches the trace.
        for x,idx in ((102,64),(104,71)):
            self.assertEqual(rgb(x,100),p[idx])
        self.assertEqual(rgb(100,5),p[15])  # Outside-plot alias retains original color.
        self.assertEqual(count,4)
    def test_inactive_channel_does_not_disable_other_channel_effect(self):
        png,_,_=synthetic(inactive_ch2=True)
        _,count=recolor(png,{'ch1':'#ff0000','ch2':'#00ff00'})
        self.assertEqual(count,3)
    def test_unknown_palette_is_rejected_for_original_fallback(self):
        png,_,_=synthetic(unknown=True)
        with self.assertRaises(ScopeError):
            recolor(png,{'ch1':'#ff0000','ch2':'#00ff00'})

if __name__=='__main__':
    unittest.main(verbosity=2)
