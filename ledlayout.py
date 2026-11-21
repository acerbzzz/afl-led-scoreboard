"""Native integer-pixel typography shared by the compact scoreboards."""
import re
import textwrap
import unicodedata
from PIL import Image, ImageDraw

FONT = {'0': ('111', '101', '101', '101', '111'), '1': ('010', '110', '010', '010', '111'), '2': ('111', '001', '111', '100', '111'), '3': ('111', '001', '111', '001', '111'), '4': ('101', '101', '111', '001', '001'), '5': ('111', '100', '111', '001', '111'), '6': ('111', '100', '111', '101', '111'), '7': ('111', '001', '010', '010', '010'), '8': ('111', '101', '111', '101', '111'), '9': ('111', '101', '111', '001', '111'), 'A': ('010', '101', '111', '101', '101'), 'B': ('110', '101', '110', '101', '110'), 'C': ('011', '100', '100', '100', '011'), 'D': ('110', '101', '101', '101', '110'), 'E': ('111', '100', '110', '100', '111'), 'F': ('111', '100', '110', '100', '100'), 'G': ('011', '100', '101', '101', '011'), 'H': ('101', '101', '111', '101', '101'), 'I': ('111', '010', '010', '010', '111'), 'J': ('001', '001', '001', '101', '010'), 'K': ('101', '101', '110', '101', '101'), 'L': ('100', '100', '100', '100', '111'), 'M': ('101', '111', '111', '101', '101'), 'N': ('101', '111', '111', '111', '101'), 'O': ('010', '101', '101', '101', '010'), 'P': ('110', '101', '110', '100', '100'), 'Q': ('010', '101', '101', '111', '011'), 'R': ('110', '101', '110', '101', '101'), 'S': ('011', '100', '010', '001', '110'), 'T': ('111', '010', '010', '010', '010'), 'U': ('101', '101', '101', '101', '111'), 'V': ('101', '101', '101', '101', '010'), 'W': ('101', '101', '111', '111', '101'), 'X': ('101', '101', '010', '101', '101'), 'Y': ('101', '101', '010', '010', '010'), 'Z': ('111', '001', '010', '100', '111'), '.': ('000', '000', '000', '000', '010'), ':': ('000', '010', '000', '010', '000'), '-': ('000', '000', '111', '000', '000'), ' ': ('000', '000', '000', '000', '000'), '?': ('111', '001', '010', '000', '010'), '/': ('001', '001', '010', '100', '100'), '&': ('010', '101', '010', '101', '011'), "'": ('010', '010', '000', '000', '000'), '+': ('000', '010', '111', '010', '000')}


def clean(value):
    value = str(value).replace('–','-').replace('—','-').replace('•',' ').replace('×','X')
    return unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().upper()


def width(label, sx=1):
    return max(0, len(clean(label)) * 4 - 1) * sx


def text(image, label, box, color='white', sx=1, sy=1, align='center'):
    """Render in a bounded cell; never squeeze or distort horizontal spacing."""
    label = clean(label)
    x0,y0,x1,y1 = box
    if width(label,sx)>x1-x0 or 5*sy>y1-y0:
        raise ValueError('Text does not fit its cell: '+label)
    x = x0 if align=='left' else x1-width(label,sx) if align=='right' else x0+(x1-x0-width(label,sx))//2
    y = y0+(y1-y0-5*sy)//2
    pen=ImageDraw.Draw(image)
    for letter in label:
        for row,bits in enumerate(FONT.get(letter,FONT['?'])):
            for col,bit in enumerate(bits):
                if bit=='1':
                    pen.rectangle((x+col*sx,y+row*sy,x+(col+1)*sx-1,y+(row+1)*sy-1),fill=color)
        x+=4*sx


def pages(label, capacity=16):
    label=clean(label)
    return textwrap.wrap(label, width=capacity, break_long_words=True, break_on_hyphens=False) or ['']


def footer(image, labels, flag='', tick=0, right=64):
    flag=clean(flag)
    prefix=flag+' ' if flag else ''
    capacity=(right+1)//4-len(prefix)
    lines=[]
    for label in labels:
        for line in pages(label,capacity):
            if line and line not in lines: lines.append(line)
    label=prefix+(lines[int(tick)%len(lines)] if lines else '')
    text(image,label,(0,27,right,32),'#ffca62')


def large(image,label,box,color='white',tick=0):
    capacity=(box[2]-box[0]+1)//4
    label=pages(label,capacity)[int(tick)%len(pages(label,capacity))]
    sx=2 if width(label,2)<=box[2]-box[0] else 1
    sy=2 if box[3]-box[1]>=10 else 1
    text(image,label,box,color,sx,sy)
