from PIL import Image, ImageDraw, ImageFont, JpegImagePlugin
Image.init()
F='/usr/share/fonts/truetype/dejavu/'
NAVY=(20,40,70); GOLD=(190,145,50); GREY=(90,90,90)
S=2; W,H=1275*S,1650*S
f=lambda n,s: ImageFont.truetype(F+n,s*S); B,R='DejaVuSans-Bold.ttf','DejaVuSans.ttf'
# sign-in
pg=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(pg)
def c(y,t,fo,col):
    w=d.textlength(t,font=fo); d.text(((W-w)/2,y),t,font=fo,fill=col)
d.rectangle([0,0,W,230*S],fill=NAVY)
c(30*S,"OPEN HOUSE SIGN-IN",f(B,40),'white')
c(95*S,"5759 W Sea Grape Ln, Tampa, FL 33611",f(B,30),(240,200,90))
c(150*S,"Sunday, November 1, 2026  |  1:00 - 3:00 PM",f(B,26),'white')
c(252*S,"Welcome! Please sign in, and kindly remove your shoes at the door:",f(R,19),(40,40,40))
c(280*S,"the wood floors were just refinished. Thank you!",f(R,19),(40,40,40))
cols=[("Name",300),("Phone",190),("Email",300),("Your agent (if any)",210),("How did you hear?",155)]
x0=40*S; y=325*S; rh=56*S; tw=sum(w for _,w in cols)*S
d.rectangle([x0,y,x0+tw,y+rh],fill=(243,240,233))
x=x0
for n,w in cols:
    d.text((x+10*S,y+17*S),n,font=f(B,17),fill=NAVY); x+=w*S
rows=19
for i in range(rows+1):
    yy=y+rh+i*rh; d.line([x0,yy,x0+tw,yy],fill=(170,170,170),width=S)
d.rectangle([x0,y,x0+tw,y+rh*(rows+1)],outline=NAVY,width=2*S)
x=x0
for n,w in cols[:-1]:
    x+=w*S; d.line([x,y,x,y+rh*(rows+1)],fill=(170,170,170),width=S)
fy=H-130*S; d.rectangle([0,fy,W,H],fill=NAVY)
c(fy+25*S,"Brittany Morales  |  (813) 555-0119",f(B,28),'white')
c(fy+75*S,"SunCoast Realty Group  |  (813) 555-0100",f(B,26),(240,200,90))
pg.save('open_house_signin_5759.pdf',resolution=150*S)
pg.resize((W//3,H//3)).save('sg/signin_prev.png')
# feature sheet
pg=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(pg)
ph=Image.open('sg/front.jpg').convert('RGB'); ph=ph.resize((W,int(ph.height*W/ph.width)),Image.LANCZOS)
ch=640*S; t=(ph.height-ch)//2; pg.paste(ph.crop((0,t,W,t+ch)),(0,0))
y=ch; d.rectangle([0,y,W,y+150*S],fill=NAVY)
d.text((60*S,y+22*S),"5759 W Sea Grape Ln",font=f(B,44),fill='white')
d.text((60*S,y+86*S),"South Tampa, FL 33611  |  Open House Sunday, Nov 1, 1-3 PM",font=f(R,22),fill='white')
pr="$679,000"; pw=d.textlength(pr,font=f(B,52)); d.text((W-60*S-pw,y+40*S),pr,font=f(B,52),fill=(240,200,90))
y+=190*S
facts=[("Bedrooms","4"),("Bathrooms","2.5"),("Garage","3-car"),("Heated Sq Ft","2,040"),("Year Built","2004"),("Roof","2016 shingle"),("Windows","Original 2004"),("List Price","$679,000")]
cw=(W-120*S)//4; bh=120*S
for i,(k,v) in enumerate(facts):
    cx=60*S+(i%4)*cw; cy=y+(i//4)*(bh+20*S)
    d.rounded_rectangle([cx+8*S,cy,cx+cw-8*S,cy+bh],radius=10*S,fill=(243,240,233))
    for txt,fo,col,dy in ((v,f(B,32),NAVY,22),(k.upper(),f(R,17),GREY,76)):
        w=d.textlength(txt,font=fo); d.text((cx+(cw-w)/2,cy+dy*S),txt,font=fo,fill=col)
y+=2*bh+70*S
d.text((60*S,y),"Highlights",font=f(B,30),fill=NAVY); y+=55*S
d.line([60*S,y,W-60*S,y],fill=GOLD,width=3*S); y+=25*S
for b in ["Open living and dining room (22x20) flowing into a 17x17 kitchen","Separate family room, plus a powder room and indoor laundry downstairs","Upstairs primary suite with a walk-in closet and private bath","Three more bedrooms upstairs sharing a full hall bath off the landing","Lanai out back and a 3-car garage (single + double door); roof replaced 2016"]:
    d.ellipse([70*S,y+12*S,82*S,y+24*S],fill=GOLD); d.text((100*S,y),b,font=f(R,24),fill=(40,40,40)); y+=50*S
fy=H-150*S; d.rectangle([0,fy,W,H],fill=NAVY)
c(fy+30*S,"Brittany Morales  |  (813) 555-0119",f(B,28),'white')
c(fy+82*S,"SunCoast Realty Group  |  (813) 555-0100",f(B,26),(240,200,90))
d.text((60*S,fy-34*S),"Heated square footage per as-built plan. Information deemed reliable but not guaranteed; buyer to verify.",font=f(R,15),fill=GREY)
pg.save('5759_sea_grape_feature_sheet.pdf',resolution=150*S)
# card
bg=Image.open('sg/palms_bg.png').convert('RGB'); bg=bg.resize((1080,int(bg.height*1080/bg.width)),Image.LANCZOS)
t=(bg.height-1350)//2+40; bg=bg.crop((0,t,1080,t+1350)); W2,H2=1080,1350
ov=Image.new('RGBA',(W2,H2),(0,0,0,0)); od=ImageDraw.Draw(ov)
for yy in range(520): od.line([0,yy,W2,yy],fill=(15,30,55,int(170*(1-yy/520))))
od.rectangle([0,1005,W2,H2],fill=(20,40,70,225))
im=Image.alpha_composite(bg.convert('RGBA'),ov).convert('RGB'); d=ImageDraw.Draw(im)
Bf=lambda s: ImageFont.truetype(F+B,s); Rf=lambda s: ImageFont.truetype(F+R,s); G=(240,200,90)
def c2(y,t,fo,col,sh=True):
    w=d.textlength(t,font=fo); x=(W2-w)/2
    if sh: d.text((x+2,y+2),t,font=fo,fill=(0,0,0))
    d.text((x,y),t,font=fo,fill=col)
c2(70,"OPEN HOUSE",Bf(104),'white'); c2(205,"SUNDAY, NOVEMBER 1",Bf(50),G); c2(272,"1:00 - 3:00 PM",Bf(50),'white')
c2(1035,"5759 W Sea Grape Ln, Tampa, FL 33611",Bf(38),'white',False)
c2(1095,"$679,000  |  4 Beds  |  2.5 Baths",Bf(42),G,False)
d.line([140,1170,W2-140,1170],fill=G,width=2)
c2(1195,"Brittany Morales  |  (813) 555-0119",Bf(38),'white',False)
c2(1255,"SunCoast Realty Group  |  (813) 555-0100",Bf(36),G,False)
d.text((W2-330,980),"Background image is illustrative",font=Rf(16),fill=(235,235,235))
im.save('open_house_5759_sunday.png')
