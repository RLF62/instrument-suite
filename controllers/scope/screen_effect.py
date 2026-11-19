"""Channel trace/text dashboard recoloring of verified 640x480 TDS3000 indexed captures."""
import struct
import zlib
from scope_io import ScopeError

def chunks(data):
    pos=8
    while pos+12<=len(data):
        n=struct.unpack('>I',data[pos:pos+4])[0]
        kind=data[pos+4:pos+8]
        yield kind,data[pos+8:pos+8+n]
        pos+=n+12

def paeth(a,b,c):
    p=a+b-c
    ds=(abs(p-a),abs(p-b),abs(p-c))
    return (a,b,c)[ds.index(min(ds))]

def indexed_pixels(data):
    parts=list(chunks(data))
    header=dict(parts).get(b'IHDR',b'')
    if len(header)!=13:
        raise ScopeError('Unsupported screen image header.')
    width,height,depth,color,compression,flt,interlace=struct.unpack('>IIBBBBB',header)
    if (width,height,depth,color,compression,flt,interlace)!=(640,480,8,3,0,0,0):
        raise ScopeError('Custom trace colors require a 640x480 8-bit indexed TDS capture.')
    palette=dict(parts).get(b'PLTE',b'')
    if len(palette)<67*3:
        raise ScopeError('Unrecognized scope color palette.')
    colors=[tuple(palette[i:i+3]) for i in range(0,len(palette),3)]
    packed=zlib.decompress(b''.join(p for k,p in parts if k==b'IDAT'))
    if len(packed)!=(width+1)*height:
        raise ScopeError('Invalid indexed capture length.')
    rows=[]
    prior=bytearray(width)
    pos=0
    for _ in range(height):
        filter_type=packed[pos];pos+=1
        row=bytearray(packed[pos:pos+width]);pos+=width
        if filter_type not in range(5):
            raise ScopeError('Unknown PNG filter.')
        for x in range(width):
            left=row[x-1] if x else 0
            above=prior[x]
            upper_left=prior[x-1] if x else 0
            add=(0,left,above,(left+above)//2,paeth(left,above,upper_left))[filter_type]
            row[x]=(row[x]+add)&255
        rows.append(row)
        prior=row
    return width,height,colors,rows

def png_chunk(kind,payload):
    return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)

def recolor(data,colors):
    width,height,palette,rows=indexed_pixels(data)
    # Each channel has its own 15-level DPO ramp; text/markers use distinct indices.
    # Ink-saver changes CH1 from yellow to blue. Both verified normal palettes are supported.
    mapped={}
    for start,key in ((1,'ch1'),(17,'ch2')):
        bg=palette[start]
        full=palette[start+14]
        if all(palette[i]==bg for i in range(start,start+15)):
            continue  # An inactive channel has a flat background-only palette.
        expected_colors=((0,0,255),(255,255,0)) if key=='ch1' else ((0,255,255),)
        if full not in expected_colors:
            raise ScopeError('This capture uses an unrecognized or monochrome trace palette; original shown.')
        axis=max(range(3),key=lambda j:abs(full[j]-bg[j]))
        span=full[axis]-bg[axis]
        if not span:
            raise ScopeError('Trace intensity ramp is unavailable; original shown.')
        rgb=tuple(int(colors[key][i:i+2],16) for i in (1,3,5))
        last=-1
        for idx in range(start,start+15):
            alpha=(palette[idx][axis]-bg[axis])/span
            if not 0<=alpha<=1 or alpha<last:
                raise ScopeError('Unrecognized trace intensity order; original shown.')
            expected=tuple(round(bg[j]+alpha*(full[j]-bg[j])) for j in range(3))
            if any(abs(expected[j]-palette[idx][j])>1 for j in range(3)):
                raise ScopeError('Unrecognized trace palette ramp; original shown.')
            last=alpha
            mapped[idx]=bytes(round(bg[j]+alpha*(rgb[j]-bg[j])) for j in range(3))
    text_colors={65:bytes(int(colors['ch1'][i:i+2],16) for i in (1,3,5)),
                 66:bytes(int(colors['ch2'][i:i+2],16) for i in (1,3,5))}
    original=[bytes(p) for p in palette]
    scanlines=bytearray()
    changed=0
    for y,row in enumerate(rows):
        scanlines.append(0)
        for x,idx in enumerate(row):
            # Plot interior only. Frame, readouts, labels and controls outside it are untouched.
            if idx in text_colors:
                rgb=text_colors[idx]
                changed+=rgb!=original[idx]
            elif 21<=x<522 and 21<=y<420 and idx in mapped:
                rgb=mapped[idx]
                changed+=rgb!=original[idx]
            else:
                rgb=original[idx]
            scanlines.extend(rgb)
    header=struct.pack('>IIBBBBB',width,height,8,2,0,0,0)
    result=(b'\x89PNG\r\n\x1a\n'+png_chunk(b'IHDR',header)+
            png_chunk(b'tEXt',b'Description\x00Dashboard trace color effect; original scope capture retained separately')+
            png_chunk(b'IDAT',zlib.compress(bytes(scanlines),6))+png_chunk(b'IEND',b''))
    return result,changed
