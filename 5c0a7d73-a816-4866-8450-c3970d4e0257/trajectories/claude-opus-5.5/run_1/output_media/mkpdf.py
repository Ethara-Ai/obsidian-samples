from PIL import Image, ImageDraw, ImageFont
W,H=1650,1275; M=90
F="/usr/share/fonts/truetype/dejavu/"
def f(s,b=False): return ImageFont.truetype(F+("DejaVuSans-Bold.ttf" if b else "DejaVuSans.ttf"),s)
def fserif(s,b=False): return ImageFont.truetype(F+("DejaVuSerif-Bold.ttf" if b else "DejaVuSerif.ttf"),s)
INK=(52,47,40); MUTE=(128,120,108); BG=(250,248,244); RULE=(205,198,186)
def page(title,sub,n):
    im=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(im)
    d.text((M,62),"WRIGHT INTERIORS",font=f(20,True),fill=MUTE)
    d.text((M,96),title,font=fserif(46),fill=INK)
    d.text((M,158),sub,font=f(22),fill=MUTE)
    d.line([(M,200),(W-M,200)],fill=RULE,width=2)
    d.text((M,H-60),"Pemberton Georgetown · Front living room · Concept presentation, October 29, 2026",font=f(17),fill=MUTE)
    d.text((W-M-30,H-60),str(n),font=f(17),fill=MUTE)
    return im,d
def place(im,path,box):
    x0,y0,x1,y1=box; p=Image.open(path).convert("RGB"); p.thumbnail((x1-x0,y1-y0),Image.LANCZOS)
    im.paste(p,(x0+(x1-x0-p.width)//2,y0)); return y0+p.height
def wrap(d,text,font,x,y,w,fill=INK,gap=10):
    words=text.split(); line=""
    for wd in words:
        t=(line+" "+wd).strip()
        if d.textlength(t,font=font)>w: d.text((x,y),line,font=font,fill=fill); y+=font.size+gap; line=wd
        else: line=t
    if line: d.text((x,y),line,font=font,fill=fill); y+=font.size+gap
    return y
def kv(d,x,y,k,v,w):
    d.text((x,y),k.upper(),font=f(17,True),fill=MUTE); return wrap(d,v,f(26),x,y+28,w)+18

pages=[]
# 1 rendering
im,d=page("Front living room","Concept rendering",1)
b=place(im,"pemberton_living_room_rendering.png",(M,230,W-M,H-130))
d.text((M,b+14),"Illustrative rendering. Colour and proportions are indicative; the fabric is chosen from the physical swatch.",font=f(18),fill=MUTE)
pages.append(im)
# 2 wall + sofa
im,d=page("The long wall and the sofa","Site measure, October 23, 2026",2)
iw=980; b=place(im,"sofa_wall_measured.jpg",(M,240,M+iw,H-130))
d.text((M,b+14),"Long wall, corner to corner, laser measure: 12′ 4″ (148 in). Shown before the shelves and crates were cleared.",font=f(17),fill=MUTE)
x=M+iw+60; w=W-M-x; y=250
d.text((x,y),"Hollis sofa",font=fserif(38,True),fill=INK); y+=62
d.text((x,y),"Maison Verde, COM",font=f(22),fill=MUTE); y+=56
y=kv(d,x,y,"Length","108 in",w)
y=kv(d,x,y,"Long wall","12′ 4″ (148 in), laser measure",w)
y=kv(d,x,y,"Clearance","About 20 in clear at each end, for the Arlo side tables",w)
y=kv(d,x,y,"COM yardage","18 yd, 54 in plain",w)
pages.append(im)
# 3 fabric + total
im,d=page("Upholstery and order summary","Fabric for the Hollis · living-room order list",3)
cw=(W-2*M-80)//2; x=M; y=250
d.text((x,y),"Halden performance linen",font=fserif(38,True),fill=INK); y+=62
d.text((x,y),"Loom and Field Textiles",font=f(22),fill=MUTE); y+=56
y=kv(d,x,y,"Colourway","Cashew 7214 (oatmeal)",cw)
y=kv(d,x,y,"Abrasion","38,000 double rubs, Wyzenbeek",cw)
y=kv(d,x,y,"Standard","Meets ACT high-traffic upholstery guideline for woven fabrics, indoor use: 30,000 double rubs Wyzenbeek",cw)
y=kv(d,x,y,"Content","58% linen, 42% cotton · 54 in wide",cw)
x2=M+cw+80; y=250
d.text((x2,y),"Order summary",font=fserif(38,True),fill=INK); y+=80
rows=[("Hollis sofa, COM, 108 in",4520),("Halden linen, Cashew 7214, 18 yd",1548),("Pike coffee table, white oak, 54 in",1180),("Arlo side tables, white oak (2)",730),("Flatweave wool rug, oatmeal, 8 x 10 ft",612),("Wren table lamps, satin brass (2)",372),("Linen sheers, ivory (2 panels)",304),("Boucle pillows, oatmeal, 22 in (4)",256)]
for k,v in rows:
    d.text((x2,y),k,font=f(22),fill=INK); s=f"${v:,}"; d.text((W-M-d.textlength(s,font=f(22)),y),s,font=f(22),fill=INK); y+=42
d.line([(x2,y+4),(W-M,y+4)],fill=INK,width=2); y+=20
d.text((x2,y),"Order total",font=f(28,True),fill=INK); s=f"${sum(v for _,v in rows):,}"
d.text((W-M-d.textlength(s,font=f(28,True)),y),s,font=f(28,True),fill=INK)
pages.append(im)
pages[0].save("pemberton_living_room_concept.pdf",save_all=True,append_images=pages[1:],resolution=150)
for i,p in enumerate(pages): p.resize((825,637)).save(f"pem/prev{i+1}.png")
